"""
B.L.A.Z.E — Voice Engine
Simple, reliable always-on wake word listener.
Uses SpeechRecognition (not raw PyAudio) to avoid mic conflicts.
Single mic context opened once, never closed.
"""

import re
import time
import threading

from blaze.deps import sr, voice_available
from blaze.core.logging_audit import log


class VoiceEngine:
    WAKE_WORDS = [
        "hey blaze", "ok blaze", "yo blaze", "hi blaze", "hello blaze",
    ]
    MISHEARS = [
        "hey please", "hey plays", "hey place", "hey blase",
        "hey days",   "hey bless", "hey blade", "hey blaise",
        "hey prince", "hey price", "hey praise", "hey race",
        "ok please",  "yo please", "hey grace",  "hey trace",
        "hey bliss",  "hey blast", "hey glass",  "hey brass",
        "a blaze",    "the blaze", "hey graze",  "hey glaze",
        "hey daze",   "hey haze",  "hey maze",   "hey craze",
        "hey phrase", "hey faze",  "hey braise", "hey raze",
    ]

    def __init__(self):
        self.recognizer       = sr.Recognizer() if voice_available else None
        self.microphone       = sr.Microphone() if voice_available else None
        self._wake_callback   = None
        self._ack_callback    = None
        self._state_callback  = None
        self._hotword_active  = False
        self._hotword_thread  = None
        self._is_responding   = False
        self._manual_listen   = False
        self._manual_callback = None
        self._spotify_was_playing = False

        if voice_available and self.recognizer:
            self.recognizer.energy_threshold         = 800
            self.recognizer.dynamic_energy_threshold = False
            self.recognizer.pause_threshold          = 0.8
            self.recognizer.phrase_threshold         = 0.3

    # ── Callbacks ─────────────────────────────────────────────────────────────
    def set_ack_callback(self, fn):
        self._ack_callback = fn

    def set_state_callback(self, fn):
        self._state_callback = fn

    def _set_state(self, state: str):
        if self._state_callback:
            self._state_callback(state)

    def set_responding(self, flag: bool):
        self._is_responding = flag
        self._set_state("speaking" if flag else "idle")

    # ── Manual mic button ─────────────────────────────────────────────────────
    def trigger_manual_listen(self, callback):
        if not self._hotword_active:
            callback(None, "Hotword loop not running.")
            return
        self._manual_listen   = True
        self._manual_callback = callback
        self._set_state("listening")
        log.info("Manual listen triggered.")

        def _timeout():
            time.sleep(10)
            if self._manual_listen:
                self._manual_listen   = False
                cb = self._manual_callback
                self._manual_callback = None
                self._set_state("idle")
                if cb:
                    cb(None, "No speech detected. Try again.")
        threading.Thread(target=_timeout, daemon=True).start()

    # ── Always-on loop ────────────────────────────────────────────────────────
    def start_hotword_loop(self, callback):
        if not voice_available or not self.microphone:
            log.warning("Hotword loop unavailable — PyAudio not installed.")
            return
        if self._hotword_active:
            return
        self._hotword_active = True
        self._wake_callback  = callback
        self._hotword_thread = threading.Thread(
            target=self._hotword_loop, daemon=True, name="blaze-hotword"
        )
        self._hotword_thread.start()
        log.info("Hotword loop started.")

    def stop_hotword_loop(self):
        self._hotword_active = False

    def _hotword_loop(self):
        """
        Opens mic ONCE via SpeechRecognition context manager.
        Stays inside it forever. No PyAudio conflicts.
        """
        while self._hotword_active:
            try:
                with self.microphone as source:
                    log.info("Calibrating mic for ambient noise...")
                    self.recognizer.adjust_for_ambient_noise(source, duration=1.5)
                    self.recognizer.dynamic_energy_threshold = False
                    log.info(f"Mic ready. Threshold={self.recognizer.energy_threshold:.0f}. Listening...")
                    self._set_state("idle")

                    while self._hotword_active:
                        if self._is_responding:
                            time.sleep(0.1)
                            continue
                        try:
                            audio = self.recognizer.listen(
                                source, timeout=3, phrase_time_limit=8
                            )
                        except sr.WaitTimeoutError:
                            continue
                        except OSError as e:
                            log.warning(f"Mic stream error: {e} — reopening in 2s")
                            break
                        except Exception as e:
                            log.warning(f"Listen error: {e}")
                            time.sleep(0.3)
                            continue

                        # Process synchronously when it might be a wake word
                        # (we need the SAME open source for follow-up listening)
                        self._process_audio(audio, source)

            except Exception as e:
                log.error(f"Mic open failed: {e}")

            if self._hotword_active:
                log.info("Reopening mic in 2s...")
                time.sleep(2)

    def _process_audio(self, audio, source):
        """
        Runs on the hotword loop thread (synchronous by design).
        This blocks new wake-word detection while it runs, which is fine —
        we WANT to finish handling one interaction before listening again.
        `source` is the SAME open mic stream as the outer loop, so we can
        reuse it directly for follow-up listening with zero conflicts.
        """
        try:
            text = self.recognizer.recognize_google(audio).lower()
            log.info(f"Heard: '{text}'")
        except sr.UnknownValueError:
            if self._manual_listen:
                self._manual_listen = False
                cb = self._manual_callback
                self._manual_callback = None
                self._set_state("idle")
                if cb:
                    cb(None, "Could not understand. Please try again.")
            return
        except Exception as e:
            log.warning(f"Recognition error: {e}")
            return

        # ── Manual listen (mic button) ─────────────────────────────────────────
        if self._manual_listen:
            self._manual_listen = False
            cb = self._manual_callback
            self._manual_callback = None
            self._set_state("idle")
            if cb:
                cb(text, None)
            return

        # ── Wake word check ────────────────────────────────────────────────────
        if not self.check_wake_word(text):
            return

        log.info(f"Wake word confirmed: '{text}'")
        self._set_state("listening")
        self._pause_spotify()

        command = self.strip_wake_word(text).strip()
        log.info(f"Command after strip: '{command}'")

        if command and len(command) > 2:
            log.info(f"Inline command: '{command}'")
            if self._wake_callback:
                self._wake_callback(command)
        else:
            log.info("Wake word only — sending ack...")
            if self._ack_callback:
                self._ack_callback()
            # Wait only as long as needed for ack speech (short phrase ~1.2s)
            # then listen using the SAME source — no reopen, minimal delay
            time.sleep(1.3)
            command = self._listen_for_command(source)
            log.info(f"Follow-up command: '{command}'")
            if command:
                command = self.strip_wake_word(command).strip()
                if self._wake_callback:
                    self._wake_callback(command)

        self._set_state("idle")

    def _listen_for_command(self, source) -> str | None:
        """
        Listen for command after wake word, reusing the SAME open mic
        source from the hotword loop. No new context manager — avoids
        Windows PyAudio nested-open conflicts entirely.
        """
        try:
            audio = self.recognizer.listen(
                source, timeout=6, phrase_time_limit=15
            )
            text = self.recognizer.recognize_google(audio)
            log.info(f"Command heard: '{text}'")
            return text
        except sr.WaitTimeoutError:
            log.info("No command heard after wake word.")
            return None
        except sr.UnknownValueError:
            return None
        except Exception as e:
            log.warning(f"Command listen error: {e}")
            return None

    # ── Spotify pause/resume ──────────────────────────────────────────────────
    def _get_spotify(self):
        try:
            import spotipy
            from spotipy.oauth2 import SpotifyOAuth
            from blaze.config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI
            import os as _os
            if not SPOTIFY_CLIENT_ID:
                return None
            cache = _os.path.join(_os.path.expanduser("~"), ".blaze_spotify_cache")
            if not _os.path.exists(cache):
                return None
            auth = SpotifyOAuth(
                client_id=SPOTIFY_CLIENT_ID,
                client_secret=SPOTIFY_CLIENT_SECRET,
                redirect_uri=SPOTIFY_REDIRECT_URI,
                scope="user-modify-playback-state user-read-playback-state",
                cache_path=cache, open_browser=False
            )
            if not auth.get_cached_token():
                return None
            return spotipy.Spotify(auth_manager=auth)
        except Exception:
            return None

    def _pause_spotify(self):
        try:
            sp = self._get_spotify()
            if not sp:
                return
            pb = sp.current_playback()
            if pb and pb.get("is_playing"):
                sp.pause_playback()
                self._spotify_was_playing = True
                log.info("Spotify paused.")
        except Exception:
            pass

    def _resume_spotify(self):
        if not self._spotify_was_playing:
            return
        self._spotify_was_playing = False
        try:
            sp = self._get_spotify()
            if sp:
                sp.start_playback()
                log.info("Spotify resumed.")
        except Exception:
            pass

    # ── Helpers ───────────────────────────────────────────────────────────────
    def check_wake_word(self, text: str) -> bool:
        t = text.lower()
        return any(w in t for w in self.WAKE_WORDS + self.MISHEARS)

    def strip_wake_word(self, text: str) -> str:
        for w in self.WAKE_WORDS + self.MISHEARS:
            text = re.sub(re.escape(w), "", text, flags=re.I).strip()
        return text.strip()


voice_engine = VoiceEngine()
