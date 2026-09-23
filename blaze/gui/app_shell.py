"""
app_shell.py — BlazeController: the real integration point.

Owns both top-level windows (chat mode + floating talk mode) and wires
them to the actual BLAZE backend:

- blaze.intelligence.nlp.nlp classifies every input; mode_switch_talk /
  mode_switch_chat intents get routed to handle_voice_command() instead
  of being sent to the LLM.
- blaze.ai.engine.BlazeAI.chat() runs the actual Groq call. It's
  synchronous/blocking (network + up to ~7s of retry backoff), so it
  always runs on a background QThread — never on the Qt main thread —
  or the whole UI would freeze on every message.
- blaze.ai.voice.VoiceEngine drives the orb's state automatically:
  its set_state_callback already emits exactly "idle"/"listening"/
  "speaking", which are the same strings orb_widget.BlazeOrb uses, so
  no translation layer is needed. Its callback fires from a background
  hotword-listener thread, so it's marshaled onto the Qt thread via a
  signal rather than touching widgets directly from that thread.
- blaze.services.system_monitor.monitor.alert_check() previously had no
  caller anywhere in the codebase — nothing was polling it. This adds
  the polling (every 5s) and feeds it into report_system_alert(), which
  keeps the "only overrides idle" priority rule from your earlier call.

Honest gaps, so they don't surprise you later:
- voice_engine.set_ack_callback() (the "yes sir, how can I help" spoken
  reply when you say just the wake word with no command) isn't wired.
  Without it, saying only "hey blaze" does nothing visible — the hotword
  loop won't error, it just won't acknowledge you. Wire it the same way
  as _on_wake_word below if you want that back.
- I could not test the real Groq call, real TTS audio, or real
  microphone capture — this sandbox has no audio hardware and no network
  path to Groq's API. I tested the wiring itself (threading, signals,
  intent routing, alert priority) with BlazeAI.chat mocked out — see the
  test script alongside this delivery. The actual network/audio paths
  need to be verified on your machine.
- TTS playback timing has a pre-existing quirk carried over unchanged
  from blaze/gui/app.py: ai.speak() only queues text for a separate TTS
  thread and returns immediately, so "speaking" state can flip back to
  "idle" slightly before audio actually finishes playing. That's not
  something introduced here — your tkinter app has the same behavior —
  flagging it in case it's ever worth fixing for real.
"""

from __future__ import annotations
import re
import time
import platform
import datetime
import threading

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from blaze.gui.chat_mode_window import ChatModeWindow
from blaze.gui.talk_mode_window import TalkModeWindow
from blaze.services import hw_stats
from blaze.services.system_monitor import monitor as system_monitor
from blaze.services.system_monitor import weather, news_module, ReminderEngine
from blaze.proactive.monitor import ProactiveMonitor
from blaze.intelligence.nlp import nlp
from blaze.ai.engine import BlazeAI
from blaze.ai.voice import voice_engine
from blaze.ai.persona import persona
from blaze.deps import voice_available, crypto_available
from blaze.plugins.manager import plugins
from blaze.config import MODEL, GROQ_API_KEY, SESSION_TIMEOUT
from blaze.core.logging_audit import log
from blaze.core.database import db
from blaze.core.security import verify_pin

_SWITCH_TO_CHAT = re.compile(r"switch to (chatbot|chat) mode", re.I)
_SWITCH_TO_TALK = re.compile(r"switch to (talk|speak) mode", re.I)

MODE_SWITCH_INTENTS = {"mode_switch_talk", "mode_switch_chat"}


class _ChatWorker(QObject):
    """Runs BlazeAI.chat() + execute_system_commands() off the Qt thread.
    One of these per in-flight message — the controller only ever has one
    alive at a time since input is disabled while waiting (see
    BlazeController._handle_input).

    cancel_flag mirrors the original app.py's _cancel_flag exactly: it's
    a best-effort cancel, checked before and after the blocking chat()
    call, not a true mid-network-call abort (Groq's SDK call itself can't
    be interrupted once it's in flight). If cancelled, no reply_ready
    signal is emitted at all — the controller's own cancel handler is
    what updates the UI immediately when the button is clicked."""

    reply_ready = Signal(str, list)  # (cleaned_reply, system_command_results)

    def __init__(self, ai: BlazeAI, text: str, cancel_flag: threading.Event):
        super().__init__()
        self._ai = ai
        self._text = text
        self._cancel_flag = cancel_flag

    def run(self):
        if self._cancel_flag.is_set():
            return
        try:
            reply = self._ai.chat(self._text)
            results = self._ai.execute_system_commands(reply)
        except Exception as e:
            log.error(f"Chat worker error: {e}")
            reply, results = f"Neural core error, sir: {e}", []
        if self._cancel_flag.is_set():
            return
        clean = re.sub(r"\[SYSTEM:[^\]]+\]", "", reply).strip()
        self.reply_ready.emit(clean, results)


class BlazeController(QObject):
    # emitted from background threads (voice engine callbacks), marshaled
    # onto the Qt main thread via normal Qt signal/slot cross-thread rules
    _voice_state_signal = Signal(str)
    _wake_word_signal = Signal(str)
    _manual_listen_signal = Signal(str, str)  # (recognized_text_or_empty, error_or_empty)
    _boot_line_signal = Signal(str, str)  # (text, sender)
    _weather_ready_signal = Signal(str)
    _reminder_signal = Signal(str)
    _proactive_signal = Signal(str, str)  # (ptype, data_or_empty)
    _phone_mirror_resize_signal = Signal(bool)  # enlarged?

    def __init__(self):
        super().__init__()
        self.ai = BlazeAI()

        self.chat_window = ChatModeWindow()
        self.talk_window = TalkModeWindow()

        self.chat_window.chat.switch_to_talk_mode.connect(self.show_talk_mode)
        self.talk_window.orb.switch_to_chat_mode.connect(self.show_chat_mode)
        self.chat_window.chat.message_submitted.connect(self._handle_typed_input)
        self.chat_window.chat.cancel_requested.connect(self._on_cancel_clicked)
        self.chat_window.chat.mic_requested.connect(self._on_mic_requested)
        self.chat_window.chat.feedback_given.connect(self._on_feedback)
        self.chat_window.chat.settings_requested.connect(self._open_settings)
        self.chat_window.chat.unlock_attempted.connect(self._on_unlock_attempt)

        self._voice_state_signal.connect(self._on_voice_state)
        self._wake_word_signal.connect(self._handle_wake_word)
        self._manual_listen_signal.connect(self._on_manual_listen_result)
        self._boot_line_signal.connect(self._on_boot_line)
        self._weather_ready_signal.connect(self.chat_window.chat.set_weather)
        self._reminder_signal.connect(self._on_reminder)
        self._proactive_signal.connect(self._on_proactive)
        self._phone_mirror_resize_signal.connect(self._on_phone_mirror_resize)

        self._busy = False
        self._active_worker = None
        self._active_thread = None
        self._cancel_flag = threading.Event()
        self._is_listening = False
        self._last_action = time.time()

        self._hw_timer = QTimer(self)
        self._hw_timer.timeout.connect(self._poll_hardware)
        self._hw_timer.start(1000)

        self._alert_timer = QTimer(self)
        self._alert_timer.timeout.connect(self._poll_system_alerts)
        self._alert_timer.start(5000)

        self._weather_timer = QTimer(self)
        self._weather_timer.timeout.connect(self._refresh_weather)
        self._weather_timer.start(10 * 60 * 1000)  # every 10 minutes, same cadence as app.py

        self._session_timer = QTimer(self)
        self._session_timer.timeout.connect(self._check_session_timeout)
        self._session_timer.start(60 * 1000)  # same 60s check cadence as app.py

        self._wire_voice_engine()
        self.show_chat_mode()
        self._run_startup_sequence()

        # ReminderEngine's callback fires from its own background thread
        # (30s poll loop) — marshal via signal like everything else here.
        # BlazeAI needs the instance wired in directly too, so "remind me
        # to X in 10 minutes" parsed by nlp as a reminder intent actually
        # gets stored (was silently a no-op before this — ai._reminder_engine
        # defaults to None in engine.py's __init__).
        self.reminder_engine = ReminderEngine(lambda msg: self._reminder_signal.emit(msg))
        self.ai._reminder_engine = self.reminder_engine

        # PhoneHandler (handlers/phone_handler.py) resizes the mirror panel
        # deterministically — no LLM round trip needed for "open/enlarge my
        # phone screen" — but it runs on the AI worker thread (see
        # _AiWorker above), so it can't touch the QWidget directly. Same
        # signal-marshaling pattern as everything else in this file.
        self.ai.gui_phone_mirror_callback = lambda enlarged: self._phone_mirror_resize_signal.emit(enlarged)

        # ProactiveMonitor has its own alert_check() polling loop (60s,
        # deduped 5min per alert) — separate from BlazeController's own
        # 5s alert poll in _poll_system_alerts. They're not fighting: the
        # 5s poll drives the orb's visual danger state (needs to be fast),
        # this one pushes a one-time deduped notification into chat (can
        # be slow). Also handles the 8am briefing nudge and habit-based
        # suggestions from the pattern learner.
        self.proactive = ProactiveMonitor(
            lambda ptype, data: self._proactive_signal.emit(ptype, data or "")
        )

    # --- voice engine wiring ------------------------------------------

    def _wire_voice_engine(self):
        if not voice_available:
            log.warning(
                "Voice engine unavailable on this machine (no mic / PyAudio) "
                "— hotword listening and voice state won't be live. Talk mode "
                "still works for manual state testing via orb.set_state()."
            )
            return
        # These two callbacks fire on VoiceEngine's own background thread
        # (_hotword_loop), never on the Qt thread — that's why they only
        # emit signals here instead of touching widgets directly.
        voice_engine.set_state_callback(lambda state: self._voice_state_signal.emit(state))
        voice_engine.start_hotword_loop(lambda command: self._wake_word_signal.emit(command))

    @Slot(str)
    def _on_voice_state(self, state: str):
        # voice_engine already emits exactly "idle" / "listening" / "speaking",
        # which are the same names orb_widget.BlazeOrb uses — no mapping needed.
        if state in ("idle", "listening", "speaking"):
            # don't clobber an active danger state with a routine idle tick
            if self.talk_window.orb._state == "danger" and state == "idle":
                return
            self.talk_window.orb.set_state(state)

    # --- mode switching ---------------------------------------------------

    def show_chat_mode(self):
        self.talk_window.hide()
        self.chat_window.show()
        self.chat_window.raise_()
        self.chat_window.activateWindow()

    def show_talk_mode(self):
        self.chat_window.hide()
        self.talk_window.show()
        self.talk_window.raise_()

    def handle_voice_command(self, text: str) -> bool:
        if _SWITCH_TO_CHAT.search(text):
            self.show_chat_mode()
            return True
        if _SWITCH_TO_TALK.search(text):
            self.show_talk_mode()
            return True
        return False

    # --- danger-state wiring ------------------------------------------

    def report_system_alert(self, is_danger: bool):
        orb = self.talk_window.orb
        if is_danger and orb._state == "idle":
            orb.set_state("danger")
        elif not is_danger and orb._state == "danger":
            orb.clear_danger()

    # --- shared input pipeline (typed AND spoken funnel through here) -----

    @Slot(str)
    def _handle_typed_input(self, text: str):
        # ChatWindow._submit_text() already appended the user bubble before
        # emitting this signal, so we don't add one here.
        self._process_text(text)

    @Slot(str)
    def _handle_wake_word(self, text: str):
        # This path bypasses ChatWindow entirely (voice_engine calls it
        # directly from the hotword thread), so there's no bubble yet —
        # add one here to keep a visible transcript regardless of which
        # window is on screen when it happens.
        self.chat_window.chat.add_message(text, sender="user")
        self._process_text(text)

    def _process_text(self, text: str):
        if not text or not text.strip():
            return
        if self.chat_window.chat.is_locked():
            return
        self._last_action = time.time()

        # Morning brief uses real data directly, bypassing the LLM entirely
        # to avoid template-placeholder hallucination — same reasoning and
        # same check position (before nlp.analyze) as app.py's _send().
        if self._is_briefing_request(text):
            self._deliver_briefing()
            return

        # nlp classifies intent first; mode-switch phrases never reach the
        # LLM at all, matching how custom commands short-circuit ai.chat()
        # in the original engine.
        nlp_result = nlp.analyze(text)
        if nlp_result["intent"] in MODE_SWITCH_INTENTS:
            self.handle_voice_command(text)
            return

        if self._busy:
            log.info(f"Still processing previous message — dropping: '{text}'")
            return

        self._cancel_flag.clear()
        self._busy = True
        self._set_input_enabled(False)
        self.chat_window.chat.set_cancel_enabled(True)
        self.chat_window.chat.show_thinking()

        worker = _ChatWorker(self.ai, text, self._cancel_flag)
        thread = threading.Thread(target=worker.run, daemon=True)
        worker.reply_ready.connect(self._on_reply)
        self._active_worker = worker
        self._active_thread = thread
        thread.start()

    @Slot(str, list)
    def _on_reply(self, reply: str, results: list):
        # Kick off TTS generation FIRST, before touching the GUI at all —
        # this is the one real lever available: Edge TTS's actual audio
        # synthesis happens over the network and takes real time (roughly
        # a few hundred ms to a couple seconds depending on text length
        # and connection), while adding a chat bubble is near-instant.
        # Starting the network call a beat earlier closes as much of that
        # gap as code ordering can — but it can't eliminate it. If you
        # want them to feel truly simultaneous, the actual fix is a local
        # (non-network) TTS engine instead of cloud-based Edge TTS — see
        # the note in speak() in engine.py for that trade-off.
        def _speak():
            voice_engine.set_responding(True)
            self.ai.speak(reply)
            voice_engine.set_responding(False)
            voice_engine._resume_spotify()

        threading.Thread(target=_speak, daemon=True).start()

        self.chat_window.chat.add_message(reply, sender="assistant")
        for r in results:
            self.chat_window.chat.add_message(f"⟩ {r}", sender="assistant")

        self._restore_input_state()

    def _restore_input_state(self):
        self._busy = False
        self._set_input_enabled(True)
        self.chat_window.chat.set_cancel_enabled(False)
        self.chat_window.chat.hide_thinking()

    def _on_cancel_clicked(self):
        if not self._busy:
            return
        self._cancel_flag.set()
        self.chat_window.chat.add_message("Request cancelled.", sender="assistant")
        self._restore_input_state()

    def _on_feedback(self, score: int):
        msg = self.ai.save_feedback(score)
        self.chat_window.chat.add_message(msg, sender="assistant")

    def _on_mic_requested(self):
        if self._is_listening or self._busy or self.chat_window.chat.is_locked():
            return
        if not voice_available or not voice_engine.microphone:
            self.chat_window.chat.add_message(
                "Voice unavailable — install PyAudio for voice input.", sender="assistant"
            )
            return
        if not voice_engine._hotword_active:
            self.chat_window.chat.add_message(
                "Hotword loop not running. Restart BLAZE.", sender="assistant"
            )
            return

        self._is_listening = True
        self.chat_window.chat.set_mic_listening(True)
        self.chat_window.chat.add_message("🎙 Listening... speak now.", sender="assistant")

        def on_result(text, err):
            # fires on VoiceEngine's own thread — marshal via signal, same
            # pattern as the hotword/state callbacks
            self._manual_listen_signal.emit(text or "", err or "")

        voice_engine.trigger_manual_listen(on_result)

    @Slot(str, str)
    def _on_manual_listen_result(self, text: str, err: str):
        self._is_listening = False
        self.chat_window.chat.set_mic_listening(False)
        if text:
            stripped = voice_engine.strip_wake_word(text)
            self.chat_window.chat._input.setText(stripped)
            self.chat_window.chat._on_submit()
        else:
            self.chat_window.chat.add_message(err or "No input detected.", sender="assistant")

    def _set_input_enabled(self, enabled: bool):
        self.chat_window.chat._input.setEnabled(enabled)

    # --- startup sequence (ported from app.py's _startup_sequence) ------

    def _run_startup_sequence(self):
        threading.Thread(target=self._refresh_weather, daemon=True).start()
        threading.Thread(target=self._boot_worker, daemon=True).start()

    def _boot_worker(self):
        msgs = [
            "Initializing neural core...",
            f"Platform: {platform.system()} {platform.release()}",
            f"Model: {MODEL}",
            "NLP engine: active",
            "Emotional intelligence: active",
            "Pattern learner: active",
            f"Security vault: {'encrypted' if crypto_available else 'plaintext'}",
            f"Plugins: {len(plugins.plugins)} loaded",
            "All systems nominal.",
        ]
        for msg in msgs:
            time.sleep(0.25)
            self._boot_line_signal.emit(msg, "system")
        time.sleep(0.25)

        hour = datetime.datetime.now().hour
        og_mode = persona.tone == "og"

        if og_mode:
            greeting = "Yo, what's good" if hour < 17 else "Ay, evening vibes"
            name = (persona.name or "").strip()
            address = name if name and name.lower() not in ("sir", "homie", "fam") else "homie"
            intro = (
                f"{greeting}, {address}. BLAZE in the building — Brilliantly Linked Autonomous "
                f"Zone Engine, put together by Kartik. Neural core's live, everything's running "
                f"smooth. What we getting into today?"
            )
        else:
            greeting = "Good morning" if hour < 12 else ("Good afternoon" if hour < 17 else "Good evening")
            name = (persona.name or "").strip()
            address = name if name and name.lower() != "sir" else "sir"
            intro = (
                f"{greeting}, {address}. I am B.L.A.Z.E — Brilliantly Linked Autonomous Zone Engine, "
                f"created by Kartik. Neural core online. All intelligence systems active. "
                f"How may I assist you today?"
            )
        self._boot_line_signal.emit(intro, "assistant")

        if not GROQ_API_KEY:
            self._boot_line_signal.emit(
                "No API key detected. Add GROQ_API_KEY to your .env file. Free at console.groq.com",
                "system",
            )

        if not voice_available:
            self._boot_line_signal.emit(
                "Voice engine unavailable — no microphone detected or PyAudio not installed. "
                "Wake word listening is OFF. Mic button in chat will also fail until this is fixed.",
                "system",
            )
        elif not voice_engine._hotword_active:
            self._boot_line_signal.emit(
                "Hotword loop did not start. Check ~/.blaze/blaze.log for the actual error.",
                "system",
            )
        else:
            self._boot_line_signal.emit(
                "Hotword loop active — calibrating mic for ambient noise now "
                "(check ~/.blaze/blaze.log for 'Mic ready. Threshold=...' once done).",
                "system",
            )

        # Wait for TTS to actually be ready (not a blind sleep), up to 5s —
        # same as app.py's boot() rather than guessing a fixed delay.
        waited = 0.0
        while not self.ai.tts_engine and waited < 5.0:
            time.sleep(0.2)
            waited += 0.2
        if og_mode:
            self.ai.speak(
                f"{greeting}, {address}. BLAZE is live, your personal AI. "
                f"Everything's running smooth. What we getting into today?"
            )
        else:
            self.ai.speak(
                f"{greeting}, {address}. I am B.L.A.Z.E., your personal AI assistant. "
                f"All systems are online. How may I assist you today?"
            )

        # No automatic briefing at boot anymore — only the intro above.
        # The morning brief only ever runs when explicitly asked for (see
        # _is_briefing_request() in _process_text), which calls
        # _deliver_briefing(speak=True). This also fixes a real duplicate-
        # message bug: this call used to run alongside ProactiveMonitor's
        # own independent "briefing" check (_on_proactive below), and if
        # both fired near boot the brief would print twice.

    @Slot(str, str)
    def _on_boot_line(self, text: str, sender: str):
        self.chat_window.chat.add_message(text, sender=sender)

    # --- weather + morning briefing (ported from app.py) -----------------

    def _refresh_weather(self):
        weather._cache = None
        weather._cache_time = 0
        w = weather.get()
        if "error" not in w:
            text = f"{w.get('city', '?')}: {w.get('temp_c', '?')}°C\n{w.get('desc', '?')}\nHumidity: {w.get('humidity', '?')}%"
        else:
            text = f"Error: {w['error']}"
        self._weather_ready_signal.emit(text)

    def _is_briefing_request(self, text: str) -> bool:
        low = text.lower()
        return "morning brief" in low or "morning briefing" in low or "daily briefing" in low

    def _deliver_briefing(self, speak: bool = True):
        self.chat_window.chat.add_message("Generating morning briefing...", sender="system")

        def run():
            w = weather.summary_str()
            headlines = news_module.get_headlines(3)
            news_str = "; ".join(headlines[:3]) if headlines else "News unavailable."
            sys_str = system_monitor.summary()
            if persona.tone == "og":
                brief = (
                    f"Yo, here's the rundown, homie. "
                    f"Weather: {w}. Top news: {news_str}. System: {sys_str}."
                )
            else:
                brief = (
                    f"Good morning. Here is your daily briefing. "
                    f"Weather: {w}. Top news: {news_str}. System: {sys_str}."
                )
            self._boot_line_signal.emit(brief, "assistant")
            if speak:
                threading.Thread(target=self.ai.speak, args=(brief,), daemon=True).start()

        threading.Thread(target=run, daemon=True).start()

    # --- reminders + proactive alerts (ported from app.py) ---------------

    @Slot(str)
    def _on_reminder(self, message: str):
        self.chat_window.chat.add_message(message, sender="system")
        self._flash_orb_alert()
        threading.Thread(target=self.ai.speak, args=(f"Reminder: {message}",), daemon=True).start()

    @Slot(bool)
    def _on_phone_mirror_resize(self, enlarged: bool):
        panel = getattr(self.chat_window.chat, "_phone_mirror", None)
        if panel:
            panel.set_enlarged(enlarged)

    @Slot(str, str)
    def _on_proactive(self, ptype: str, data: str):
        if ptype == "alert":
            self.chat_window.chat.add_message(f"⚠ {data}", sender="system")
            self._flash_orb_alert()
            threading.Thread(target=self.ai.speak, args=(f"Alert. {data}",), daemon=True).start()
        elif ptype == "briefing":
            # Shows the briefing as text (same as boot), but never auto-speaks
            # it — only speaks when you explicitly ask, per your call.
            self._deliver_briefing(speak=False)
        elif ptype == "suggestion":
            self.chat_window.chat.add_message(f"💡 {data}", sender="system")

    def _flash_orb_alert(self):
        # Mirrors app.py's orb="alert" then auto-revert to idle after 4s.
        # orb_widget.py doesn't have a separate "alert" state (only idle/
        # listening/speaking/danger were the four you approved), so this
        # reuses "danger" as the closest visual equivalent for "something
        # needs your attention right now." Same inherited quirk as the
        # original: if a genuine system-danger state is already active
        # when this fires, the 4s auto-revert will incorrectly clear it
        # back to idle — app.py has the identical limitation, not
        # something introduced here.
        orb = self.talk_window.orb
        orb.set_state("danger")
        QTimer.singleShot(4000, orb.clear_danger)

    # --- session lock (ported from app.py's _start_session_timer) --------

    def _check_session_timeout(self):
        pin_hash = db.get_pref("pin_hash", "")
        if not pin_hash:
            return  # no PIN set — lock feature is opt-in, same as original
        if self.chat_window.chat.is_locked():
            return
        if time.time() - self._last_action > SESSION_TIMEOUT:
            self.chat_window.chat.lock_session()

    def _on_unlock_attempt(self, entered_pin: str):
        pin_hash = db.get_pref("pin_hash", "")
        if verify_pin(entered_pin, pin_hash):
            self._last_action = time.time()
            self.chat_window.chat.unlock()
        else:
            self.chat_window.chat.add_message("Incorrect PIN.", sender="system")

    # --- settings dialog ---------------------------------------------------

    def _open_settings(self):
        from blaze.gui.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self, parent=self.chat_window)
        dialog.exec()

    # --- internal --------------------------------------------------------

    def _poll_hardware(self):
        snap = hw_stats.snapshot()
        orb = self.talk_window.orb
        orb.push_cpu(snap["cpu_pct"], snap["cpu_temp_c"])
        if snap["gpu_pct"] is not None:
            orb.push_gpu(snap["gpu_pct"], snap["gpu_temp_c"])

    def _poll_system_alerts(self):
        if not system_monitor.available:
            return
        alerts = system_monitor.alert_check()
        self.report_system_alert(is_danger=bool(alerts))


def _demo():
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    ctrl = BlazeController()
    sys.exit(app.exec())


if __name__ == "__main__":
    _demo()
