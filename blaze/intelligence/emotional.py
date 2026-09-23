"""
B.L.A.Z.E — Emotional Intelligence (Feature 6)
Detects user mood and provides empathetic response prefixes with a cooldown
so the same empathy phrase isn't repeated too quickly.
"""

import time
import random


class EmotionalIntelligence:
    RESPONSES = {
        "sad": [
            "I'm sorry to hear you're feeling down, sir. I'm here if you need to talk.",
            "That sounds tough, sir. Would you like a distraction or someone to listen?",
            "I understand, sir. Sometimes things get heavy. How can I help lighten the load?",
        ],
        "angry": [
            "I can sense your frustration, sir. Let's work through this together.",
            "Understood, sir. Let me help resolve whatever's causing this.",
            "Take a breath, sir. I've got you. What do you need?",
        ],
        "happy": [
            "That's wonderful to hear, sir! Your energy is contagious.",
            "Excellent! Good mood detected — let's make the most of it, sir.",
            "Glad to hear it, sir. How can I keep that momentum going?",
        ],
        "stress": [
            "I can tell things are piling up, sir. Let's tackle them one at a time.",
            "Stress detected, sir. Shall I help prioritize your tasks?",
            "Deep breath, sir. Tell me what's on your plate and we'll sort it out.",
        ],
    }

    # Minimum seconds between empathy prefixes for the same emotion
    COOLDOWN_SEC = 600  # 10 minutes

    def __init__(self):
        self._last_empathy: dict = {}

    def get_empathetic_prefix(self, emotion: str) -> str:
        now  = time.time()
        last = self._last_empathy.get(emotion, 0)
        if now - last < self.COOLDOWN_SEC:
            return ""
        responses = self.RESPONSES.get(emotion, [])
        if not responses:
            return ""
        self._last_empathy[emotion] = now
        return random.choice(responses)

    def mood_tag(self, emotion: str) -> str:
        tags = {"sad": "💙", "angry": "🔥", "happy": "✨", "stress": "⚡", "neutral": ""}
        return tags.get(emotion, "")


# ── Singleton ─────────────────────────────────────────────────────────────────
ei = EmotionalIntelligence()
