"""
B.L.A.Z.E — AI Engine
Groq LLM integration, TTS, system command dispatch, and feedback logging.
"""

import os
import re
import time
import queue
import threading
import webbrowser
import datetime

from blaze.config import GROQ_API_KEY, MODEL, MAX_HISTORY
from blaze.deps import Groq, groq_available, pyttsx3, tts_available, psutil, psutil_available
from blaze.core.database import db
from blaze.core.security import vault
from blaze.core.logging_audit import log
from blaze.intelligence.nlp import nlp
from blaze.intelligence.emotional import ei
from blaze.intelligence.learner import learner
from blaze.intelligence.domain import build_system_prompt
from blaze.ai.persona import persona
from blaze.handlers.registry import HANDLERS
from blaze.services.system_monitor import (
    monitor, weather, news_module, filemanager, launcher,
)
from blaze.services.integrations import services
from blaze.intelligence.knowledge import knowledge
from blaze.intelligence.automations import automation
from blaze.ai.persona import persona
from blaze.services.calendar import calendar_manager
from blaze.services.gmail_service import gmail_manager
from blaze.services.tasks_service import tasks_manager
from blaze.services.drive_service import drive_manager
from blaze.services.sheets_service import sheets_manager
from blaze.services.youtube_service import youtube_manager
from blaze.services.contacts_service import contacts_manager
from blaze.services.calendar import calendar_manager
from blaze.services.gmail_service import gmail_manager
from blaze.services.tasks_service import tasks_manager
from blaze.services.drive_service import drive_manager
from blaze.services.sheets_service import sheets_manager
from blaze.services.contacts_service import contacts_manager


class BlazeAI:
    def __init__(self):
        try:
            self.client = Groq(api_key=GROQ_API_KEY) if (groq_available and GROQ_API_KEY) else None
        except Exception as e:
            log.error(f"Groq client init failed: {e}")
            self.client = None

        self.history          = db.load_history()
        self.tts_engine       = None
        self._tts_proc        = None  # tracks active Edge TTS playback subprocess
        self.tts_queue        = queue.Queue()
        self.voice_enabled    = db.get_pref("voice_enabled", "true") == "true"
        self._last_user_msg   = ""
        self._last_blaze_msg  = ""
        self._context_memory  = []   # last 3 (user, blaze) pairs for follow-up
        self._last_open_target  = None  # resolved target of the last successful open_app
        self._last_close_target = None  # resolved target of the last successful close_app
        self._reminder_engine = None  # set after GUI init
        # Set by app_shell.py to a function(enlarged: bool) that resizes the
        # PhoneMirrorPanel widget via a Qt signal (safe to call from this
        # engine's background worker thread — see handlers/phone_handler.py).
        # Stays None when running headless/via blaze_server.py, where
        # there's no such panel to resize.
        self.gui_phone_mirror_callback = None

        # TTS setup
        self.tts_available = tts_available
        self._tts_lock     = threading.Lock()
        self._tts_thread   = None
        self._tts_backend  = "sapi"
        if tts_available:
            self._start_tts_thread()

    def _start_tts_thread(self):
        t = threading.Thread(target=self._tts_worker, name="blaze-tts", daemon=True)
        t.start()
        self._tts_thread = t

    def _tts_worker(self):
        """
        TTS priority:
        1. Edge TTS (neural voices — most natural, free, no API key)
        2. win32com SAPI (built-in Windows voices)
        3. pyttsx3 (fallback)
        """
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass

        # Detect which backend to use
        self._tts_backend = "pyttsx3"
        speaker = None

        # Always reload persona to get latest saved voice
        from blaze.ai.persona import persona as _p
        saved_voice = _p.voice_id or ""
        log.info(f"TTS starting with voice: '{saved_voice or 'default'}'")

        # Try Edge TTS first if saved voice is neural
        try:
            import edge_tts
            if not saved_voice or saved_voice.endswith("Neural"):
                self._tts_backend = "edge"
                self.tts_engine   = "edge"
                log.info(f"TTS ready using Edge TTS. Voice: {saved_voice or 'en-IN-PrabhatNeural'}")
        except ImportError:
            # Try win32com SAPI
            try:
                import win32com.client
                speaker = win32com.client.Dispatch("SAPI.SpVoice")
                speaker.Volume = 100
                speaker.Rate   = 0
                self.tts_engine   = speaker
                self._tts_backend = "sapi"
                log.info("TTS ready using SAPI SpVoice.")
            except Exception:
                # pyttsx3 fallback
                try:
                    engine = pyttsx3.init()
                    voices = engine.getProperty("voices")
                    try:
                        saved = getattr(persona, "voice_id", "")
                        if saved:
                            engine.setProperty("voice", saved)
                        elif voices:
                            for v in voices:
                                if any(p in v.name.lower() for p in ["david","mark","james"]):
                                    engine.setProperty("voice", v.id)
                                    break
                    except Exception:
                        pass
                    engine.setProperty("rate", getattr(persona, "tts_speed", 175))
                    engine.setProperty("volume", 1.0)
                    speaker = engine
                    self.tts_engine   = engine
                    self._tts_backend = "pyttsx3"
                    log.info("TTS ready using pyttsx3.")
                except Exception as e:
                    log.error(f"TTS init failed: {e}")
                    return

        while True:
            try:
                text = self.tts_queue.get()
                if text is None:
                    break
                if not self.voice_enabled:
                    try: self.tts_queue.task_done()
                    except Exception: pass
                    continue
                try:
                    if self._tts_backend == "edge":
                        self._speak_edge(text)
                    elif self._tts_backend == "sapi":
                        speaker.Speak(text)
                    else:
                        speaker.say(text)
                        speaker.runAndWait()
                except Exception as e:
                    log.warning(f"TTS speak error: {e}")
                try: self.tts_queue.task_done()
                except Exception: pass
            except Exception as e:
                log.warning(f"TTS loop error: {e}")

    def _speak_edge(self, text: str):
        """Speak using Edge TTS neural voices. Uses Windows MediaPlayer — no pygame needed."""
        import asyncio, tempfile, os as _os, subprocess, time as _t
        try:
            import edge_tts
        except ImportError:
            try:
                engine = pyttsx3.init()
                engine.say(text)
                engine.runAndWait()
            except Exception:
                pass
            return

        from blaze.ai.persona import persona as _p
        voice = (_p.voice_id or "") if (_p.voice_id or "").endswith("Neural") else "en-IN-PrabhatNeural"
        speed = getattr(_p, "tts_speed", 175)
        # Convert pyttsx3 rate (175) to edge-tts rate (+0%)
        rate_pct = (speed - 175) // 2
        rate_str = f"+{rate_pct}%" if rate_pct >= 0 else f"{rate_pct}%"

        tmp = tempfile.mktemp(suffix=".mp3")
        try:
            async def _gen():
                comm = edge_tts.Communicate(text, voice, rate=rate_str)
                await comm.save(tmp)
            asyncio.run(_gen())

            # Play with Windows Media Player (built-in, no extra install)
            self._tts_proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-c",
                 f"Add-Type -AssemblyName presentationCore; "
                 f"$mp = New-Object system.windows.media.mediaplayer; "
                 f"$mp.open('{tmp}'); $mp.Play(); "
                 f"Start-Sleep -s 1; "
                 f"while ($mp.NaturalDuration.HasTimeSpan -eq $false) {{ Start-Sleep -m 100 }}; "
                 f"$dur = $mp.NaturalDuration.TimeSpan.TotalSeconds + 1; "
                 f"Start-Sleep -s $dur; $mp.Close()"],
                shell=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            self._tts_proc.wait()
            self._tts_proc = None
        except Exception as e:
            log.warning(f"Edge TTS error: {e}")
        finally:
            try: _os.remove(tmp)
            except Exception: pass

    def speak(self, text):
        if not self.voice_enabled or not self.tts_available:
            return
        clean = re.sub(r"\[SYSTEM:[^\]]+\]", "", text)
        clean = re.sub(r"[*_`#]", "", clean).strip()
        # Fix pronunciation: "B.L.A.Z.E" / "B . L . A . Z . E" → "Blaze"
        clean = re.sub(r"B[\s\.]*L[\s\.]*A[\s\.]*Z[\s\.]*E", "Blaze", clean, flags=re.I)
        if not clean:
            return
        # Deduplicate — don't speak the same text twice in a row
        if clean == getattr(self, "_last_spoken", ""):
            return
        self._last_spoken = clean
        if self._tts_thread and not self._tts_thread.is_alive():
            log.warning("TTS thread died — restarting...")
            self._start_tts_thread()
            import time; time.sleep(1.0)
        self.tts_queue.put(clean)

    def stop_speaking(self):
        if self.tts_engine:
            try:
                self.tts_engine.stop()
            except Exception:
                pass

    # ── Offline command handler ───────────────────────────────────────────────
    # These commands are handled 100% locally — no GROQ call needed.
    _OFFLINE_OPEN = [
        "open ", "launch ", "start ", "run ", "show me ",
        "can you open ", "please open ", "hey open ",
        "can you launch ", "please launch ",
        "could you open ", "would you open ",
        "i want to open ", "i want you to open ",
    ]
    _OFFLINE_CLOSE = [
        "close ", "quit ", "exit ", "kill ", "stop ", "shut down ",
        "can you close ", "please close ", "can you quit ",
        "could you close ", "would you close ",
    ]
    _OFFLINE_EXACT = {
        # greetings
        "hey blaze": "Hello sir, I am online and ready.",
        "hello blaze": "Hello sir, how may I assist you?",
        "hi blaze": "Hi sir, what can I do for you?",
        "yo blaze": "Yes sir, I am here.",
        "wake up": "I am awake, sir. Ready to assist.",
        # time / date
        "what time is it": None,   # handled dynamically
        "what is the time": None,
        "time":             None,
        "what is today":    None,
        "what is the date": None,
        "date":             None,
        "what day is it":   None,
        # system
        "how are you":        None,   # dynamic
        "system status":      None,
        "system stats":       None,
        "battery":            None,
        "battery status":     None,
        # misc
        "clear history":      None,
        "list reminders":     None,
        "my reminders":       None,
    }

    def _handle_offline(self, user_text: str):
        """
        Handle commands locally without GROQ.
        Returns reply string if handled, None if GROQ needed.
        NOTE: do NOT call self.speak() here — _on_reply handles speaking.

        This used to be one 300-line if/elif chain. It's now a thin loop
        over blaze/handlers/registry.py's HANDLERS list — each capability
        (Spotify, weather, reminders, system stats, etc.) lives in its own
        file and can be changed independently. Same fall-through behavior
        as before: first handler that returns non-None wins, in the exact
        same priority order the original code checked things in.
        """
        t = user_text.lower().strip()
        now = datetime.datetime.now()

        for handler in HANDLERS:
            result = handler.handle(self, user_text, t, now)
            if result is not None:
                return result

        return None   # needs GROQ


    # ── Main chat method ──────────────────────────────────────────────────────
    def _addr(self) -> str:
        """Tone-aware form of address for the ~35 hardcoded direct-dispatch
        responses below (time, date, stats, reminders, vault, etc.) that
        bypass the LLM entirely and previously said ', sir' unconditionally
        regardless of the persona.tone setting."""
        return "homie" if persona.tone == "og" else "sir"

    def chat(self, user_text):
        # Try offline handler first — no GROQ call needed
        offline_reply = self._handle_offline(user_text)
        if offline_reply is not None:
            learner.record(user_text[:40])
            db.log_command(user_text[:60])
            self._last_user_msg  = user_text
            self._last_blaze_msg = offline_reply
            db.save_message("user",      user_text,     "neutral")
            db.save_message("assistant", offline_reply, "neutral")
            return offline_reply

        if not self.client:
            return (
                f"GROQ_API_KEY not configured, {self._addr()}. "
                "Add it to your .env file. Free key at console.groq.com"
            )

        nlp_result = nlp.analyze(user_text)
        intent     = nlp_result["intent"]
        emotion    = nlp_result["emotion"]

        # Custom command check
        for trigger, response, action in db.get_custom_commands():
            if trigger.lower() in user_text.lower():
                result = response
                if action:
                    result += f" [SYSTEM:open_app:{action}]"
                return result

        # Reminder shortcut
        if intent == "reminder" and self._reminder_engine is not None:
            result = self._reminder_engine.parse_and_add(user_text)
            if result:
                return result

        learner.record(user_text[:40])
        db.log_command(user_text[:60])

        self._last_user_msg = user_text
        self.history.append({"role": "user", "content": user_text})
        db.save_message("user", user_text, emotion)
        if len(self.history) > MAX_HISTORY:
            self.history = self.history[-MAX_HISTORY:]

        empathy = ""
        if emotion != "neutral":
            empathy = ei.get_empathetic_prefix(emotion)

        try:
            last_err = None
            for attempt in range(3):
                try:
                    response = self.client.chat.completions.create(
                        model=MODEL,
                        messages=[
                            {"role": "system", "content": build_system_prompt(nlp_result, self._last_open_target)}
                        ] + self.history,
                        max_tokens=1024,
                        temperature=0.72,
                    )
                    break
                except Exception as e:
                    last_err = e
                    err_str  = str(e).lower()
                    if "rate" in err_str or "429" in err_str or "500" in err_str or "503" in err_str:
                        wait = 2 ** attempt
                        log.warning(f"Groq transient error (attempt {attempt+1}/3), retrying in {wait}s: {e}")
                        time.sleep(wait)
                        continue
                    raise
            else:
                raise last_err

            reply = response.choices[0].message.content
            if empathy and emotion in ["sad", "stress", "angry"]:
                reply = empathy + "\n\n" + reply
            self.history.append({"role": "assistant", "content": reply})
            db.save_message("assistant", reply, "neutral")
            self._last_blaze_msg = reply
            return reply

        except Exception as e:
            err = str(e)
            log.error(f"Chat error: {err}")
            if "api_key" in err.lower() or "auth" in err.lower():
                return f"Invalid API key, {self._addr()}. Check console.groq.com"
            if "rate" in err.lower():
                return f"Rate limit hit, {self._addr()}. Groq free tier — try again shortly."
            return f"Neural core error, {self._addr()}: {err}"

    # ── Vague-reference resolution ("open it again") ────────────────────────
    # The system prompt (domain.py) deliberately tells the LLM to copy the
    # user's app name into [SYSTEM:open_app:...] verbatim rather than
    # paraphrasing it — that's needed so real app names ("vs code",
    # "github profile in chrome") survive intact. The side effect: a vague
    # follow-up like "open it again" gets the same verbatim treatment, so
    # "it again" is passed straight through as if it were literally an
    # app's name, and the launcher has nothing to open. That's the actual
    # bug behind "BLAZE forgets what we were just talking about" reports —
    # the conversation history *is* being sent to the LLM every turn (see
    # chat() below), the problem is specifically that nothing ever
    # translates a pronoun back into the real target before it reaches the
    # launcher. This catches that narrow case deterministically instead of
    # relying on the LLM to always resolve it correctly on its own.
    _VAGUE_REF_RE = re.compile(
        r"^(it|that|this|the\s+same(\s+(thing|one|app))?|same(\s+(thing|one|app))?)"
        r"(\s+(again|one\s+more\s+time|once\s+more))?$",
        re.IGNORECASE,
    )

    def _resolve_vague_target(self, arg: str, last_target: str | None) -> str:
        cleaned = (arg or "").strip().lower()
        if last_target and self._VAGUE_REF_RE.match(cleaned):
            return last_target
        return arg

    # ── System command dispatcher ─────────────────────────────────────────────
    def execute_system_commands(self, reply):
        results  = []
        seen_cmds = set()

        # Pre-scan: if reply has web_search or open_url, skip any open_app tags
        # (LLM often emits both, causing two browser tabs)
        all_tags = re.findall(r"\[SYSTEM:([^\]]+)\]", reply)
        has_browser_cmd = any(
            t.split(":", 1)[0] in ("web_search", "open_url")
            for t in all_tags
        )
        browser_opened = False

        for tag in all_tags:
            parts = tag.split(":", 1)
            cmd   = parts[0]
            arg   = parts[1] if len(parts) > 1 else ""

            # Skip exact duplicates
            key = f"{cmd}:{arg}"
            if key in seen_cmds:
                continue
            seen_cmds.add(key)

            # If we already have a web_search/open_url, skip open_app entirely
            if has_browser_cmd and cmd == "open_app":
                continue

            # Only ever open one browser tab per reply
            if cmd in ("web_search", "open_url"):
                if browser_opened:
                    continue
                browser_opened = True

            result = self._dispatch(cmd, arg)
            if result:
                results.append(result)
        return results

    def _dispatch(self, cmd, arg):
        if cmd == "open_app":
            resolved = self._resolve_vague_target(arg, self._last_open_target)
            result = launcher.open(resolved)
            self._last_open_target = resolved
            return result
        if cmd == "close_app":
            resolved = self._resolve_vague_target(arg, self._last_close_target or self._last_open_target)
            result = launcher.close(resolved)
            self._last_close_target = resolved
            return result
        if cmd == "web_search":
            # Answer directly via LLM instead of redirecting to browser
            return self._answer_directly(arg)
        if cmd == "open_url":
            webbrowser.open(arg if arg.startswith("http") else f"https://{arg}")
            return f"Opening {arg}"
        if cmd == "weather":
            return weather.summary_str()
        if cmd == "system_stats":
            return monitor.summary()
        if cmd == "news":
            h = news_module.get_headlines(5)
            return ("Top headlines:\n" + "\n".join(f"• {x}" for x in h)) if h else "News unavailable."
        if cmd == "organize_downloads":
            return filemanager.organize_downloads()
        if cmd == "find_file":
            r = filemanager.find_files(arg)
            return "\n".join(r) if r else f"No files matching '{arg}'"
        if cmd == "disk_summary":
            return filemanager.disk_summary()
        if cmd == "list_processes":
            if not psutil_available:
                return "psutil not installed."
            procs = sorted(
                psutil.process_iter(["name", "cpu_percent"]),
                key=lambda p: p.info["cpu_percent"] or 0,
                reverse=True
            )[:8]
            return "Top processes:\n" + "\n".join(
                f"• {p.info['name']}: {p.info['cpu_percent']:.1f}%" for p in procs
            )
        if cmd == "add_reminder":
            if "|" in arg:
                msg, ts = arg.split("|", 1)
                try:
                    h, mi = map(int, ts.strip().split(":"))
                    fire  = datetime.datetime.now().replace(hour=h, minute=mi, second=0)
                    if fire < datetime.datetime.now():
                        fire += datetime.timedelta(days=1)
                    db.add_reminder(msg.strip(), fire)
                    return f"Reminder set: {msg.strip()} at {fire.strftime('%I:%M %p')}"
                except Exception as e:
                    return f"Could not parse reminder time '{ts.strip()}', {self._addr()}. Use HH:MM format. ({e})"
            return f"Reminder format error, {self._addr()}. Expected: message|HH:MM"
        if cmd == "list_reminders":
            rows = db.get_all_reminders()
            return ("\n".join(f"• {m} @ {f[11:16]}" for _, m, f in rows)) if rows else f"No pending reminders, {self._addr()}."
        if cmd == "save_note":
            if "|" in arg:
                title, content = arg.split("|", 1)
                db.save_note(title.strip(), content.strip())
                return f"Note saved: {title.strip()}"
        if cmd == "search_notes":
            rows = db.search_notes(arg)
            return ("\n".join(f"• [{d}] {t}: {c[:60]}..." for t, c, d in rows)) if rows else f"No notes for '{arg}'"
        if cmd == "vault_set":
            if "|" in arg:
                k, v = arg.split("|", 1)
                vault.set(k.strip(), v.strip())
                return f"Stored '{k.strip()}' in secure vault, {self._addr()}."
        if cmd == "vault_get":
            v = vault.get(arg.strip())
            return f"{arg}: {v}" if v else f"No vault entry for '{arg}'"
        if cmd == "vault_list":
            keys = vault.list_keys()
            return ("Vault keys:\n" + "\n".join(f"• {k}" for k in keys)) if keys else f"Vault is empty, {self._addr()}."
        if cmd == "define":
            return services.define_word(arg)
        if cmd == "wiki":
            return services.wiki_summary(arg)
        if cmd == "currency":
            if "|" in arg:
                parts = arg.split("|")
                if len(parts) == 3:
                    try:
                        return services.convert_currency(float(parts[0].strip()), parts[1].strip(), parts[2].strip())
                    except ValueError:
                        return f"Currency format error, {self._addr()}. Use: amount|FROM|TO (e.g. 100|USD|INR)"
        if cmd == "github_repos":      return services.github_repos(arg)
        if cmd == "github_trending":   return services.github_trending()
        if cmd == "open_drive":        return services.open_drive()
        if cmd == "search_drive":      return services.search_drive(arg)
        if cmd == "open_spotify":      return services.open_spotify_search(arg)
        if cmd == "schedule_meeting":
            # format: title|YYYY-MM-DD HH:MM|duration_minutes
            parts = arg.split("|")
            if len(parts) >= 2:
                title = parts[0].strip()
                try:
                    import datetime as _dt
                    start = _dt.datetime.strptime(parts[1].strip(), "%Y-%m-%d %H:%M")
                    duration = int(parts[2].strip()) if len(parts) > 2 else 30
                    result = calendar_manager.create_meeting(title, start, duration)
                    return result["message"]
                except Exception as e:
                    return f"Could not parse meeting time, {self._addr()}. {e}"
            return f"Could not parse meeting details, {self._addr()}."
        if cmd == "list_meetings":
            return calendar_manager.upcoming_summary()
        if cmd == "check_email":
            return gmail_manager.get_unread_summary()
        if cmd == "search_email":
            return gmail_manager.search_emails(arg)
        if cmd == "send_email":
            # format: to|subject|body
            parts = arg.split("|")
            if len(parts) >= 3:
                return gmail_manager.send_email(parts[0].strip(), parts[1].strip(), parts[2].strip())
            return f"Could not parse email details, {self._addr()}."
        if cmd == "add_task":
            return tasks_manager.add_task(arg.strip())
        if cmd == "list_tasks":
            return tasks_manager.list_tasks()
        if cmd == "complete_task":
            return tasks_manager.complete_task(arg.strip())
        if cmd == "search_drive":
            return drive_manager.search_files(arg.strip())
        if cmd == "list_drive":
            return drive_manager.list_recent()
        if cmd == "log_expense":
            parts = arg.split("|")
            cat  = parts[0].strip() if len(parts) > 0 else "General"
            desc = parts[1].strip() if len(parts) > 1 else arg
            amt  = parts[2].strip() if len(parts) > 2 else ""
            return sheets_manager.log_entry(cat, desc, amt)
        if cmd == "youtube_search":
            return youtube_manager.search(arg.strip())
        if cmd == "find_contact":
            return contacts_manager.find_contact(arg.strip())
        if cmd == "schedule_meeting":
            # format: title|YYYY-MM-DD HH:MM|duration_minutes
            parts = arg.split("|")
            if len(parts) >= 2:
                title = parts[0].strip()
                try:
                    import datetime as _dt
                    start = _dt.datetime.strptime(parts[1].strip(), "%Y-%m-%d %H:%M")
                    duration = int(parts[2].strip()) if len(parts) > 2 else 30
                    result = calendar_manager.create_meeting(title, start, duration)
                    return result["message"]
                except Exception as e:
                    return f"Could not parse meeting time, {self._addr()}. {e}"
            return f"Could not parse meeting details, {self._addr()}."
        if cmd == "list_meetings":
            return calendar_manager.upcoming_summary()
        if cmd == "check_email":
            return gmail_manager.get_unread_summary()
        if cmd == "search_email":
            return gmail_manager.search_emails(arg)
        if cmd == "send_email":
            # format: to|subject|body
            parts = arg.split("|")
            if len(parts) >= 3:
                return gmail_manager.send_email(parts[0].strip(), parts[1].strip(), parts[2].strip())
            return f"Could not parse email details, {self._addr()}."
        if cmd == "add_task":
            return tasks_manager.add_task(arg.strip())
        if cmd == "list_tasks":
            return tasks_manager.list_tasks()
        if cmd == "complete_task":
            return tasks_manager.complete_task(arg.strip())
        if cmd == "search_drive":
            return drive_manager.search_files(arg.strip())
        if cmd == "list_drive":
            return drive_manager.list_recent()
        if cmd == "log_expense":
            parts = arg.split("|")
            cat  = parts[0].strip() if len(parts) > 0 else "General"
            desc = parts[1].strip() if len(parts) > 1 else arg
            amt  = parts[2].strip() if len(parts) > 2 else ""
            return sheets_manager.log_entry(cat, desc, amt)
        if cmd == "find_contact":
            return contacts_manager.find_contact(arg.strip())
        if cmd == "generate_image":
            # Detect aspect ratio hints in the prompt
            w, h = 1024, 1024
            low = arg.lower()
            if any(k in low for k in ["wide", "landscape", "panoramic", "widescreen"]):
                w, h = 1344, 768
            elif any(k in low for k in ["portrait", "tall", "vertical"]):
                w, h = 768, 1344
            return services.generate_image(arg, width=w, height=h)
        if cmd == "add_automation":
            # format: name|trigger|action1,action2|HH:MM
            parts = arg.split("|")
            if len(parts) >= 3:
                name    = parts[0].strip()
                trigger = parts[1].strip()
                actions = [a.strip() for a in parts[2].split(",")]
                time_s  = parts[3].strip() if len(parts) > 3 else None
                return automation.add_rule(name, trigger, actions, time_s)
            return f"Could not parse automation rule, {self._addr()}."
        if cmd == "list_automations":   return automation.list_rules()
        if cmd == "show_knowledge":     return knowledge.list_all()
        if cmd == "ip_info":           return services.ip_info()
        if cmd == "top_commands":
            rows = db.get_top_commands()
            return "Most used:\n" + "\n".join(f"• {c}: {n}x" for c, n in rows)
        if cmd == "clear_history":
            db.clear_history()
            self.history.clear()
            return f"History cleared, {self._addr()}."
        if cmd == "habit_summary":     return learner.weekly_summary()
        if cmd == "feedback_stats":    return learner.get_feedback_stats()

        # Fall through to plugin system
        from blaze.plugins.manager import plugins
        return plugins.dispatch(cmd, arg)

    def _answer_directly(self, query: str) -> str:
        """Answer a query using the LLM directly instead of opening a browser."""
        if not self.client:
            return "GROQ_API_KEY not configured. Cannot answer query."
        try:
            response = self.client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": (
                        "You are BLAZE, an advanced AI assistant. "
                        "Answer the user's question directly and thoroughly "
                        "using your own knowledge. Be concise but complete. "
                        "Do not say you cannot browse the internet — just answer from your training knowledge."
                    )},
                    {"role": "user", "content": query},
                ],
                max_tokens=600,
                temperature=0.6,
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Could not answer directly: {e}"

    def save_feedback(self, rating: int):
        db.save_feedback(self._last_user_msg, self._last_blaze_msg, rating)
        return f"Thank you, {self._addr()}. Rating of {rating}/5 recorded."