"""
handlers/media_handler.py — "play [song/video]" routing to Spotify or
YouTube. This is your "Music Bot" request — Spotify's actual API/desktop
work lives in services/integrations.py, this file just decides where a
bare "play X" request should go.
"""

from __future__ import annotations
import datetime

from blaze.handlers.base import CommandHandler
from blaze.services.integrations import services
from blaze.services.youtube_service import youtube_manager

PLAY_PREFIXES = [
    "play ", "play song ", "play music ", "play the song ",
    "play video ", "play the video ", "play livestream ",
    "can you play ", "please play ", "put on ",
]

YOUTUBE_KEYWORDS = [" on youtube", " from youtube", " on yt", "livestream", "live stream", "video by", " video "]
SPOTIFY_KEYWORDS = [" on spotify", " from spotify", " in spotify"]
WEB_KEYWORDS = [" web app", " web player", " in browser", " on the web", " browser"]

STRIP_SUFFIXES = [" on spotify", " in spotify", " using spotify",
                  " on youtube", " from youtube", " on yt",
                  " from spotify", " for me", " web app",
                  " web player", " in browser", " on the web", " browser"]


class PlayMusicHandler(CommandHandler):
    def handle(self, ai, user_text: str, t: str, now: datetime.datetime) -> str | None:
        for prefix in PLAY_PREFIXES:
            if not t.startswith(prefix):
                continue
            query = t[len(prefix):]
            wants_youtube = any(k in query for k in YOUTUBE_KEYWORDS)
            wants_spotify = any(k in query for k in SPOTIFY_KEYWORDS)
            wants_web = any(k in query for k in WEB_KEYWORDS)

            for suffix in STRIP_SUFFIXES:
                query = query.replace(suffix, "")
            query = query.strip()
            if not query:
                return None

            if wants_youtube and not wants_spotify:
                return youtube_manager.search(query)
            if wants_web:
                return services.open_spotify_web(query)
            # Default: Spotify desktop app (music-first assumption unless
            # YouTube or the web app was specifically named)
            return services.open_spotify_search(query)
        return None
