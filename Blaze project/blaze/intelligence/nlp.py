"""
B.L.A.Z.E — NLP Engine (Feature 1)
Intent classification, entity extraction, sentiment analysis,
emotion detection, and multi-turn context tracking.
"""

import re
from collections import deque


class NLPEngine:
    INTENTS = {
        "open_app":      r"\b(open|launch|start|run|pull up|load)\b.{0,30}\b(\w+)\b",
        "reminder":      r"\b(remind|reminder|alarm|alert me|don.t let me forget)\b",
        "weather":       r"\b(weather|temperature|temp|rain|sunny|forecast|climate|hot|cold)\b",
        "news":          r"\b(news|headlines|what.s happening|latest|current events)\b",
        "time":          r"\b(time|clock|what time|current time)\b",
        "date":          r"\b(date|today|what day|day is it)\b",
        "system":        r"\b(cpu|ram|memory|disk|battery|system|resources|processes)\b",
        "search":        r"\b(search|google|look up|find|look for)\b",
        "files":         r"\b(file|folder|organize|downloads|find file|disk)\b",
        "notes":         r"\b(note|save|remember|store|knowledge|write down)\b",
        "joke":          r"\b(joke|funny|laugh|humor|make me smile)\b",
        "greeting":      r"^(hi|hey|hello|good morning|good afternoon|good evening|sup|yo|what.s up)\b",
        "thanks":        r"\b(thank|thanks|appreciate|good job|well done|nice)\b",
        "capabilities":  r"\b(what can you do|your capabilities|features|help|commands|abilities)\b",
        "vault":         r"\b(vault|secret|password|store securely|encrypt)\b",
        "feedback":      r"\b(rate|feedback|rating|thumbs|good response|bad response)\b",
        "domain_med":    r"\b(medical|medicine|symptom|diagnosis|drug|health|disease|treatment)\b",
        "domain_law":    r"\b(legal|law|rights|contract|lawsuit|attorney|court|regulation)\b",
        "domain_fin":    r"\b(finance|stock|invest|money|tax|budget|crypto|market|trading)\b",
        "emotion_sad":   r"\b(sad|depressed|lonely|upset|crying|unhappy|down|hopeless)\b",
        "emotion_angry": r"\b(angry|frustrated|annoyed|pissed|mad|furious)\b",
        "emotion_happy": r"\b(happy|excited|great|awesome|amazing|love it|fantastic)\b",
        "emotion_stress":r"\b(stressed|anxious|overwhelmed|panic|worried|nervous)\b",
        "morning_brief": r"\b(morning brief|briefing|daily update|daily brief|good morning brief)\b",
    }

    ENTITIES = {
        "time":     r"\b(\d{1,2}:\d{2}\s*(?:am|pm)?|\d{1,2}\s*(?:am|pm))\b",
        "url":      r"https?://[^\s]+",
        "number":   r"\b(\d+(?:\.\d+)?)\b",
        "email":    r"\b[\w.+-]+@[\w-]+\.\w+\b",
        "duration": r"\b(\d+)\s*(minute|min|hour|hr|second|sec|day|week)\b",
    }

    SENTIMENT_POS = {"great","good","awesome","love","perfect","excellent","happy","thanks","nice","well"}
    SENTIMENT_NEG = {"bad","terrible","awful","hate","wrong","broken","useless","stupid","error","fail"}

    def __init__(self):
        self._context     = deque(maxlen=10)
        self._last_intent = None

    def analyze(self, text: str) -> dict:
        text_lower = text.lower().strip()
        intent     = self._classify_intent(text_lower)
        entities   = self._extract_entities(text)
        sentiment, score = self._sentiment(text_lower)
        emotion    = self._detect_emotion(text_lower)

        self._context.append({"text": text, "intent": intent, "emotion": emotion})
        self._last_intent = intent

        return {
            "intent":    intent,
            "entities":  entities,
            "sentiment": sentiment,
            "score":     score,
            "emotion":   emotion,
            "context":   list(self._context),
        }

    def _classify_intent(self, text):
        scores = {}
        for intent, pattern in self.INTENTS.items():
            if re.search(pattern, text, re.I):
                scores[intent] = scores.get(intent, 0) + 1
        return max(scores, key=scores.get) if scores else "general"

    def _extract_entities(self, text):
        entities = {}
        for etype, pattern in self.ENTITIES.items():
            matches = re.findall(pattern, text, re.I)
            if matches:
                entities[etype] = matches
        return entities

    def _sentiment(self, text):
        words = set(text.split())
        pos   = len(words & self.SENTIMENT_POS)
        neg   = len(words & self.SENTIMENT_NEG)
        score = pos - neg
        if score > 0: return "positive", score
        if score < 0: return "negative", score
        return "neutral", 0

    def _detect_emotion(self, text):
        for emotion in ["sad", "angry", "happy", "stress"]:
            key = f"emotion_{emotion}"
            if key in self.INTENTS and re.search(self.INTENTS[key], text, re.I):
                return emotion
        return "neutral"

    def get_context_summary(self):
        if not self._context:
            return ""
        recent  = list(self._context)[-3:]
        intents = [c["intent"] for c in recent]
        emotions= [c["emotion"] for c in recent if c["emotion"] != "neutral"]
        parts   = []
        if intents:  parts.append(f"Recent intents: {', '.join(intents)}")
        if emotions: parts.append(f"Detected emotions: {', '.join(set(emotions))}")
        return "; ".join(parts)


# ── Singleton ─────────────────────────────────────────────────────────────────
nlp = NLPEngine()
