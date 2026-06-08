"""
B.L.A.Z.E — Personalization Engine (Feature 9)
Stores and applies user preferences: name, tone, verbosity, theme, TTS speed.
"""

from blaze.core.database import db


class PersonalizationEngine:
    def __init__(self):
        self.name      = db.get_pref("user_name", "sir")
        self.tone      = db.get_pref("tone", "professional")   # professional / casual / minimal
        self.verbosity = db.get_pref("verbosity", "normal")    # brief / normal / detailed
        self.theme     = db.get_pref("theme", "cyber")         # cyber / dark / minimal
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

    def tone_instruction(self):
        tones = {
            "professional": "Be formal, precise, and professional. Address user as 'sir'.",
            "casual":       "Be friendly, relaxed, and conversational. Use 'sir' occasionally.",
            "minimal":      "Be extremely concise. Max 1-2 sentences. No pleasantries.",
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
