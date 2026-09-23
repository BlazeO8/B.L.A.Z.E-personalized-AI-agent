"""
B.L.A.Z.E — Service Integrations (Feature 2)
External API / web integrations: GitHub, Spotify, Google Drive,
Trello, Slack, Notion, currency, dictionary, Wikipedia, IP info.
"""

import webbrowser

from blaze.deps import requests, requests_available
from blaze.core.logging_audit import log
from blaze.ai.persona import persona


class ServiceIntegrations:
    """Each method tries the API and gracefully falls back if the key isn't set."""

    def _addr(self) -> str:
        """Same tone-aware address helper as BlazeAI._addr() in engine.py —
        duplicated here rather than imported since this class has no
        dependency on BlazeAI and shouldn't need one just for this."""
        return "homie" if persona.tone == "og" else "sir"

    # ── Image generation (Pollinations AI — free, no API key) ──────────────────
    def generate_image(self, prompt: str, width: int = 1024, height: int = 1024) -> str:
        """
        Generate an image from a (ideally already-expanded) text prompt
        and save it to Pictures. Appends quality boosters automatically
        unless the prompt is already saturated with style/quality terms.
        """
        if not requests_available:
            return f"requests not installed, {self._addr()}."
        try:
            import os, time, urllib.parse

            clean_prompt = prompt.strip()
            if not clean_prompt:
                return f"Please tell me what image to generate, {self._addr()}."

            # Auto quality boost — only add if not already present, keeps prompt clean
            lower = clean_prompt.lower()
            boosters = []
            if not any(k in lower for k in ["8k", "detailed", "sharp focus", "high quality"]):
                if any(k in lower for k in ["photorealistic", "dslr", "realistic", "photo"]):
                    boosters.append("sharp focus, natural detail")
                else:
                    boosters.append("highly detailed, high quality")
            final_prompt = clean_prompt + (", " + ", ".join(boosters) if boosters else "")

            encoded = urllib.parse.quote(final_prompt)
            seed    = int(time.time())
            url     = (f"https://image.pollinations.ai/prompt/{encoded}"
                       f"?width={width}&height={height}&seed={seed}&nologo=true")

            log.info(f"Generating image: {clean_prompt}")
            resp = requests.get(url, timeout=60)
            if resp.status_code != 200:
                return f"Image generation failed (status {resp.status_code}), {self._addr()}."

            # Save to Pictures folder
            pictures_dir = os.path.join(os.path.expanduser("~"), "Pictures", "Blaze AI")
            os.makedirs(pictures_dir, exist_ok=True)

            safe_name = "".join(c for c in clean_prompt[:40] if c.isalnum() or c in " -_").strip()
            safe_name = safe_name.replace(" ", "_") or "image"
            filename  = f"{safe_name}_{seed}.png"
            filepath  = os.path.join(pictures_dir, filename)

            with open(filepath, "wb") as f:
                f.write(resp.content)

            log.info(f"Image saved: {filepath}")

            # Open in default image viewer
            try:
                os.startfile(filepath)
            except Exception as e:
                log.warning(f"Could not auto-open image: {e}")

            return f"Image generated and saved to Pictures, {self._addr()}. Opening it now."

        except requests.exceptions.Timeout:
            return f"Image generation timed out, {self._addr()}. The server may be busy — try again."
        except Exception as e:
            log.warning(f"Image generation error: {e}")
            return f"Could not generate image, {self._addr()}. {e}"

    # ── GitHub ────────────────────────────────────────────────────────────────
    def github_repos(self, username: str) -> str:
        if not requests_available:
            return "requests not installed."
        try:
            r = requests.get(
                f"https://api.github.com/users/{username}/repos?sort=updated&per_page=5",
                timeout=5
            )
            if r.ok:
                repos = r.json()
                lines = [f"GitHub repos for {username}:"]
                for repo in repos:
                    lines.append(f"  • {repo['name']} — ⭐{repo['stargazers_count']}")
                return "\n".join(lines)
            return f"GitHub: {r.status_code}"
        except Exception as e:
            return f"GitHub error: {e}"

    def github_trending(self) -> str:
        if not requests_available:
            return "requests not installed."
        try:
            r = requests.get(
                "https://api.github.com/search/repositories"
                "?q=stars:>1000&sort=stars&order=desc&per_page=5",
                timeout=5
            )
            if r.ok:
                items = r.json().get("items", [])
                lines = ["Trending GitHub repos:"]
                for item in items:
                    lines.append(f"  • {item['full_name']} ⭐{item['stargazers_count']}")
                return "\n".join(lines)
            return f"Could not fetch trending repos (HTTP {r.status_code})."
        except Exception as e:
            return f"GitHub trending error: {e}"

    # ── Spotify ───────────────────────────────────────────────────────────────
    def open_spotify_search(self, query: str) -> str:
        """
        Play a song on Spotify desktop app.
        Uses Spotify Web API if credentials set, else URI fallback.
        """
        import os, subprocess, ctypes, threading

        # ── Method 1: Spotify Web API (actually plays the song) ───────────────
        try:
            from blaze.config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET
            if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
                result = self._spotify_play_via_api(query)
                if result:
                    return result
        except Exception as e:
            log.warning(f"Spotify API: {e}")

        # ── Method 2: spotify: URI (opens app + search, user hits play) ───────
        safe = query.replace(" ", "%20")
        uri  = f"spotify:search:{safe}"
        try:
            # First make sure Spotify is running
            home = os.path.expanduser("~")
            exe  = os.path.join(home, "AppData", "Roaming", "Spotify", "Spotify.exe")
            if os.path.exists(exe):
                # Launch Spotify if not running
                subprocess.Popen([exe], shell=False)
                import time; time.sleep(2)  # give it time to open
            # Now open the search URI
            ctypes.windll.shell32.ShellExecuteW(None, "open", uri, None, None, 1)
            return f"Opened Spotify and searched '{query}', {self._addr()}. The song should appear — press play or set up Spotify API for auto-play."
        except Exception:
            pass

        # ── Method 3: Direct exe launch fallback ──────────────────────────────
        import os as _os
        exe = _os.path.join(_os.path.expanduser("~"), "AppData", "Roaming", "Spotify", "Spotify.exe")
        if _os.path.exists(exe):
            import subprocess as _sp
            _sp.Popen([exe])
            import time; time.sleep(2)
            try:
                uri = f"spotify:search:{query.replace(' ', '%20')}"
                import ctypes
                ctypes.windll.shell32.ShellExecuteW(None, "open", uri, None, None, 1)
            except Exception:
                pass
            return f"Opened Spotify desktop app and searched '{query}', {self._addr()}."
        return f"Spotify app not found. Please open Spotify manually, {self._addr()}."

    def open_spotify_desktop(self) -> str:
        """Opens ONLY the Spotify desktop app — no search, no browser fallback
        of any kind. This is the deterministic path for a bare 'open spotify'
        request, called directly from engine.py before the request ever
        reaches the LLM, so there's no ambiguity about desktop vs. web."""
        import os, subprocess, ctypes, time

        exe = os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Spotify", "Spotify.exe")
        if os.path.exists(exe):
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq Spotify.exe"], capture_output=True, text=True
            )
            if "Spotify.exe" not in result.stdout:
                subprocess.Popen([exe], shell=False)
                time.sleep(1.5)
            else:
                # already running — bring it to the foreground via the URI
                # handler rather than launching a second instance
                try:
                    ctypes.windll.shell32.ShellExecuteW(None, "open", "spotify:", None, None, 1)
                except Exception:
                    pass
            return f"Opening Spotify desktop app, {self._addr()}."
        return (
            f"Couldn't find the Spotify desktop app at the usual install path, {self._addr()}. "
            f"If it's installed somewhere else, let me know the path."
        )

    def open_spotify_web(self, query: str = "") -> str:
        """Opens the Spotify web player in the browser — ONLY used when you
        explicitly ask for the web app/browser version. Bare 'open spotify'
        and normal 'play X' requests never come here."""
        url = "https://open.spotify.com/search/" + query.replace(" ", "%20") if query else "https://open.spotify.com"
        webbrowser.open(url)
        return f"Opening the Spotify web app in your browser, {self._addr()}."

    def _spotify_play_via_api(self, query: str) -> str | None:
        """
        Use Spotify Web API to search + play.
        NOTE: start_playback() requires Spotify Premium.
        For free accounts, we use the spotify: URI which opens the desktop app.
        """
        try:
            import spotipy
            from spotipy.oauth2 import SpotifyOAuth
            from blaze.config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI
            import os as _os

            # Use a fixed cache path so auth token persists properly
            cache_path = _os.path.join(_os.path.expanduser("~"), ".blaze_spotify_cache")

            sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
                client_id=SPOTIFY_CLIENT_ID,
                client_secret=SPOTIFY_CLIENT_SECRET,
                redirect_uri=SPOTIFY_REDIRECT_URI,
                scope="user-read-playback-state user-modify-playback-state user-read-currently-playing",
                cache_path=cache_path,
                open_browser=True,
                show_dialog=False
            ))
            # Trigger auth silently — handles redirect automatically
            sp.auth_manager.get_access_token(as_dict=False)

            # Search for the track
            results = sp.search(q=query, type="track", limit=3)
            tracks  = results.get("tracks", {}).get("items", [])
            if not tracks:
                log.warning(f"No Spotify tracks found for: {query}")
                return None

            track  = tracks[0]
            uri    = track["uri"]
            name   = track["name"]
            artist = track["artists"][0]["name"]
            log.info(f"Spotify found: {name} by {artist} ({uri})")

            # Make sure Spotify desktop is running
            import subprocess as _sp, time as _t
            exe = _os.path.join(_os.path.expanduser("~"), "AppData", "Roaming", "Spotify", "Spotify.exe")
            if _os.path.exists(exe):
                # Check if already running
                result = _sp.run(["tasklist", "/FI", "IMAGENAME eq Spotify.exe"],
                                 capture_output=True, text=True)
                if "Spotify.exe" not in result.stdout:
                    log.info("Launching Spotify...")
                    _sp.Popen([exe])
                    _t.sleep(4)  # wait for Spotify to fully load

            # Get active device
            devices = sp.devices().get("devices", [])
            log.info(f"Spotify devices: {[d['name'] for d in devices]}")

            if not devices:
                _t.sleep(2)
                devices = sp.devices().get("devices", [])

            if devices:
                # Prefer this laptop's desktop app over any other Spotify
                # Connect device (phone, speaker, another computer) — you
                # asked for playback to always land on the app that was
                # just opened, not wherever else you're signed in.
                desktop = [d for d in devices if d.get("type") == "Computer"]
                device_id = desktop[0]["id"] if desktop else devices[0]["id"]
                try:
                    # Try Premium playback first
                    sp.start_playback(device_id=device_id, uris=[uri])
                    return f"Now playing '{name}' by {artist} on Spotify, {self._addr()}."
                except spotipy.exceptions.SpotifyException as e:
                    if "Premium" in str(e) or "403" in str(e):
                        # Free account — use URI scheme to open the track
                        log.info("Spotify free account — using URI scheme")
                        import ctypes
                        ctypes.windll.shell32.ShellExecuteW(None, "open", uri, None, None, 1)
                        return f"Opening '{name}' by {artist} on Spotify, {self._addr()}."
                    raise
            else:
                # No device found — open via URI
                import ctypes
                ctypes.windll.shell32.ShellExecuteW(None, "open", uri, None, None, 1)
                return f"Opening '{name}' by {artist} — please ensure Spotify is active, {self._addr()}."

        except ImportError:
            log.info("spotipy not installed — run: py -3.11 -m pip install spotipy")
            return None
        except Exception as e:
            log.warning(f"Spotify API error: {e}")
            return None

    # ── Google Drive ──────────────────────────────────────────────────────────
    def open_drive(self) -> str:
        webbrowser.open("https://drive.google.com")
        return f"Opening Google Drive in browser, {self._addr()}."

    def search_drive(self, query: str) -> str:
        url = f"https://drive.google.com/drive/search?q={query.replace(' ', '+')}"
        webbrowser.open(url)
        return f"Searching Google Drive for '{query}', {self._addr()}."

    # ── Trello ────────────────────────────────────────────────────────────────
    def open_trello(self) -> str:
        webbrowser.open("https://trello.com")
        return f"Opening Trello, {self._addr()}."

    # ── Slack ─────────────────────────────────────────────────────────────────
    def open_slack(self) -> str:
        webbrowser.open("https://app.slack.com")
        return f"Opening Slack in browser, {self._addr()}."

    # ── Notion ────────────────────────────────────────────────────────────────
    def open_notion(self) -> str:
        webbrowser.open("https://notion.so")
        return f"Opening Notion, {self._addr()}."

    # ── Currency conversion ───────────────────────────────────────────────────
    def convert_currency(self, amount: float, from_cur: str, to_cur: str) -> str:
        if not requests_available:
            return "requests not installed."
        try:
            r = requests.get(
                f"https://api.exchangerate-api.com/v4/latest/{from_cur.upper()}",
                timeout=5
            )
            if r.ok:
                rate = r.json()["rates"].get(to_cur.upper())
                if rate:
                    result = amount * rate
                    return f"{amount} {from_cur.upper()} = {result:.2f} {to_cur.upper()}"
            return "Currency conversion failed."
        except Exception as e:
            return f"Currency error: {e}"

    # ── Dictionary ────────────────────────────────────────────────────────────
    def define_word(self, word: str) -> str:
        if not requests_available:
            return "requests not installed."
        try:
            r = requests.get(
                f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}",
                timeout=5
            )
            if r.ok:
                data = r.json()
                if isinstance(data, list) and data:
                    meanings = data[0].get("meanings", [])
                    if meanings:
                        defs = meanings[0].get("definitions", [])
                        if defs:
                            return f"{word}: {defs[0]['definition']}"
            return f"Definition not found for '{word}'."
        except Exception as e:
            return f"Dictionary error: {e}"

    # ── Wikipedia ─────────────────────────────────────────────────────────────
    def wiki_summary(self, query: str) -> str:
        if not requests_available:
            return "requests not installed."
        try:
            r = requests.get(
                "https://en.wikipedia.org/api/rest_v1/page/summary/"
                + query.replace(" ", "_"),
                timeout=5
            )
            if r.ok:
                data    = r.json()
                extract = data.get("extract", "")
                return extract[:400] + "..." if len(extract) > 400 else extract
            return f"No Wikipedia article found for '{query}'."
        except Exception as e:
            return f"Wikipedia error: {e}"

    # ── IP info ───────────────────────────────────────────────────────────────
    def ip_info(self) -> str:
        if not requests_available:
            return "requests not installed."
        try:
            r = requests.get("https://ipinfo.io/json", timeout=5)
            if r.ok:
                d = r.json()
                return (
                    f"IP: {d.get('ip')} | "
                    f"Location: {d.get('city')}, {d.get('region')}, {d.get('country')} | "
                    f"ISP: {d.get('org')}"
                )
        except Exception as e:
            return f"IP info error: {e}"
        return "Could not fetch IP info."


# ── Singleton ─────────────────────────────────────────────────────────────────
services = ServiceIntegrations()
