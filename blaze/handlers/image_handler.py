"""
handlers/image_handler.py — your "Image Bot" request. Only catches
short/simple image requests offline; anything already richly-described
(commas, style cues) still gets handled here directly, but vague requests
return None so chat() falls through to GROQ for prompt expansion first.
services/integrations.py's generate_image() does the actual API call.
"""

from __future__ import annotations
import datetime

from blaze.handlers.base import CommandHandler
from blaze.services.integrations import services

IMAGE_PREFIXES = [
    "generate an image of ", "generate image of ", "generate a picture of ",
    "create an image of ", "create image of ", "create a picture of ",
    "draw me ", "draw a ", "draw an ", "make an image of ", "make a picture of ",
    "can you generate an image of ", "can you draw ", "please generate an image of ",
    "image of ", "picture of ",
]

DETAIL_CUES = ["style", "lighting", "realistic", "anime", "painting", "cinematic", "detailed"]


class ImageGenerationHandler(CommandHandler):
    def handle(self, ai, user_text: str, t: str, now: datetime.datetime) -> str | None:
        for prefix in IMAGE_PREFIXES:
            if not t.startswith(prefix):
                continue
            desc = user_text[len(prefix):].strip()
            if not desc:
                return None
            is_detailed = ("," in desc or len(desc.split()) > 8 or
                           any(cue in desc.lower() for cue in DETAIL_CUES))
            if is_detailed:
                return services.generate_image(desc)
            # Not detailed enough — let GROQ expand the prompt properly
            return None
        return None
