"""
B.L.A.Z.E — Personalization Engine (Feature 9)
Stores and applies user preferences: name, tone, verbosity, theme, TTS speed.
"""

from blaze.core.database import db


class PersonalizationEngine:
    def __init__(self):
        self.name      = db.get_pref("user_name", "sir")
        self.tone      = db.get_pref("tone", "professional")
        self.verbosity = db.get_pref("verbosity", "normal")
        self.theme     = db.get_pref("theme", "cyber")
        self.voice_id  = db.get_pref("voice_id", "")   # TTS voice ID
        try:
            self.tts_speed = int(db.get_pref("tts_speed", "165"))
        except (ValueError, TypeError):
            self.tts_speed = 165

    def save(self):
        db.set_pref("user_name",  self.name)
        db.set_pref("tone",       self.tone)
        db.set_pref("verbosity",  self.verbosity)
        db.set_pref("theme",      self.theme)
        db.set_pref("tts_speed",  str(self.tts_speed))
        db.set_pref("voice_id",   self.voice_id)

    def get_all_voices(self):
        """Return list of (name, id) for available TTS voices."""
        try:
            import pyttsx3
            engine = pyttsx3.init()
            voices = engine.getProperty("voices")
            engine.stop()
            return [(v.name, v.id) for v in voices]
        except Exception:
            return []

    def tone_instruction(self):
        tones = {
            "professional": "Be formal, precise, and professional. Address user as 'sir'.",
            "casual":       "Be friendly, relaxed, and conversational. Use 'sir' occasionally.",
            "minimal":      "Be extremely concise. Max 1-2 sentences. No pleasantries.",
            "og": (
                "You're BLAZE with an old-school West Coast OG persona — think a sharp, "
                "street-smart concierge who's seen it all and doesn't sweat anything. "
                "Address the user as 'homie' or 'fam', never 'sir'. Open replies with "
                "casual acknowledgments like 'yo', 'ay', or 'aight' where it feels natural, "
                "not every single message. Lean on relaxed slang — 'no cap', 'we good', "
                "'say less', 'bet', 'that's fire', 'ain't even trippin' — but don't overdo "
                "it to the point the actual answer gets buried; the swagger is flavor, not "
                "a replacement for being useful. Stay confident and unbothered even when "
                "delivering bad news or errors — you handle problems, you don't panic about "
                "them. Still give complete, accurate, technically correct answers — a real "
                "OG is competent, not just loud. Keep sentences punchy and conversational "
                "rather than long and formal."
            ),
        }
        return tones.get(self.tone, tones["professional"])

    def verbosity_instruction(self):
        vmap = {
            "brief":    "Keep ALL responses under 2 sentences.",
            "normal":   "Keep responses concise, 2-4 sentences unless detail is needed.",
            "detailed": "Provide thorough, detailed responses with context and examples.",
        }
        return vmap.get(self.verbosity, vmap["normal"])


# ── Singleton ─────────────────────────────────────────────────────────────────
persona = PersonalizationEngine()
