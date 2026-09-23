"""
B.L.A.Z.E — Google Translate API Integration
Free tier: 500,000 characters/month.
"""

from blaze.deps import requests, requests_available
from blaze.core.logging_audit import log


class TranslateManager:
    URL = "https://translation.googleapis.com/language/translate/v2"

    def _api_key(self):
        from blaze.config import GOOGLE_API_KEY
        return GOOGLE_API_KEY

    def translate(self, text: str, target_lang: str = "en") -> str:
        key = self._api_key()
        if not key:
            return "Translation needs GOOGLE_API_KEY in .env, sir."
        if not requests_available:
            return "requests not installed, sir."

        try:
            resp = requests.post(self.URL, params={"key": key}, data={
                "q": text, "target": target_lang, "format": "text"
            }, timeout=10)
            data = resp.json()

            if "error" in data:
                return f"Translation failed, sir. {data['error'].get('message', '')}"

            translated = data["data"]["translations"][0]["translatedText"]
            detected   = data["data"]["translations"][0].get("detectedSourceLanguage", "")

            return f"Translation ({detected} → {target_lang}), sir: {translated}"

        except Exception as e:
            log.warning(f"Translate error: {e}")
            return f"Could not translate, sir. {e}"

    # Common language name -> code mapping for natural voice commands
    LANG_CODES = {
        "spanish": "es", "french": "fr", "german": "de", "hindi": "hi",
        "japanese": "ja", "chinese": "zh", "korean": "ko", "arabic": "ar",
        "russian": "ru", "portuguese": "pt", "italian": "it", "english": "en",
        "tamil": "ta", "telugu": "te", "bengali": "bn", "marathi": "mr",
        "punjabi": "pa", "urdu": "ur", "gujarati": "gu",
    }

    def resolve_lang(self, name: str) -> str:
        return self.LANG_CODES.get(name.lower().strip(), name.lower().strip())


translate_manager = TranslateManager()
