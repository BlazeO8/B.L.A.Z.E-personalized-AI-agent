"""
B.L.A.Z.E — Voice Engine (Feature 4)
Microphone input with noise calibration, wake-word detection,
and confidence-scored speech recognition.
"""

import re
import threading

from blaze.deps import sr, voice_available
from blaze.core.logging_audit import log


class VoiceEngine:
    WAKE_WORDS = ["hey blaze", "blaze", "ok blaze", "yo blaze"]

    def __init__(self):
        self.recognizer          = sr.Recognizer() if voice_available else None
        self.microphone          = None
        self.confidence_threshold = 0.6

        if voice_available:
            try:
                self.microphone = sr.Microphone()
                # Calibrate in background so startup isn't blocked
                threading.Thread(target=self._calibrate, daemon=True).start()
            except Exception as e:
                log.warning(f"Voice init: {e}")

    def _calibrate(self):
        try:
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
            log.info("Voice engine calibrated.")
        except Exception as e:
            log.warning(f"Voice calibration: {e}")

    def listen(self, timeout=6):
        if not self.recognizer or not self.microphone:
            return None, "Voice unavailable — install PyAudio, sir."
        try:
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.3)
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=15)
            try:
                text = self.recognizer.recognize_google(audio)
                return text, None
            except sr.UnknownValueError:
                return None, "Could not understand audio, sir."
        except sr.WaitTimeoutError:
            return None, "No speech detected, sir."
        except Exception as e:
            return None, f"Voice error: {e}"

    def check_wake_word(self, text: str) -> bool:
        text_lower = text.lower()
        return any(w in text_lower for w in self.WAKE_WORDS)

    def strip_wake_word(self, text: str) -> str:
        for w in self.WAKE_WORDS:
            text = re.sub(re.escape(w), "", text, flags=re.I).strip()
        return text


# ── Singleton ─────────────────────────────────────────────────────────────────
voice_engine = VoiceEngine()
