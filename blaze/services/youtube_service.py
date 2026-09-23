"""
B.L.A.Z.E — YouTube Data API Integration
Search YouTube and get real video results/info.
Uses GOOGLE_API_KEY (simple API key, not OAuth) — free tier: 10,000 units/day.
"""

import webbrowser
from blaze.deps import requests, requests_available
from blaze.core.logging_audit import log


class YouTubeManager:
    BASE = "https://www.googleapis.com/youtube/v3"

    def _api_key(self):
        from blaze.config import GOOGLE_API_KEY
        return GOOGLE_API_KEY

    def search(self, query: str, max_results: int = 5, open_top: bool = True) -> str:
        key = self._api_key()
        if not key:
            # Fallback: just open YouTube search in browser
            url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
            webbrowser.open(url)
            return f"Searching YouTube for '{query}', sir. (Add GOOGLE_API_KEY in .env for richer results.)"

        if not requests_available:
            return "requests not installed, sir."

        try:
            resp = requests.get(f"{self.BASE}/search", params={
                "part": "snippet", "q": query, "type": "video",
                "maxResults": max_results, "key": key
            }, timeout=10)
            data  = resp.json()
            items = data.get("items", [])
            if not items:
                return f"No YouTube results found for '{query}', sir."

            lines = []
            top_url = None
            for it in items:
                vid   = it["id"]["videoId"]
                title = it["snippet"]["title"]
                chan  = it["snippet"]["channelTitle"]
                url   = f"https://youtube.com/watch?v={vid}"
                if top_url is None:
                    top_url = url
                lines.append(f"• {title} — {chan}")

            if open_top and top_url:
                webbrowser.open(top_url)

            return f"Found {len(items)} video(s) for '{query}', sir. Playing the top result.\n" + "\n".join(lines)

        except Exception as e:
            log.warning(f"YouTube search error: {e}")
            url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
            webbrowser.open(url)
            return f"Opened YouTube search for '{query}', sir."


youtube_manager = YouTubeManager()
