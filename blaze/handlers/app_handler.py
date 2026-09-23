"""
handlers/app_handler.py — opening/closing apps, folders, and files.

This is where today's Spotify fix lives now: bare "open spotify" always
goes to the desktop app, "web app"/"browser" phrasing is the only way to
get the browser version, and song requests route through the
desktop-biased search/play path. See services/integrations.py for the
actual Spotify methods — this file just does the routing.
"""

from __future__ import annotations
import os
import datetime
import subprocess

from blaze.handlers.base import CommandHandler
from blaze.services.system_monitor import monitor, launcher
from blaze.services.integrations import services
from blaze.deps import psutil_available
from blaze.core import devices as dev

OPEN_PREFIXES = [
    "can you open ", "please open ", "could you open ", "would you open ",
    "i want to open ", "i want you to open ", "hey open ",
    "can you launch ", "please launch ",
    "open ", "launch ", "start ", "run ",
]

CLOSE_PREFIXES = [
    "can you close ", "please close ", "could you close ",
    "would you close ", "can you quit ",
    "close ", "quit ", "exit ", "kill ", "stop ", "shut down ",
]

SYSTEM_KEYWORDS = ["system stat", "system info", "cpu", "ram", "disk",
                   "battery", "detailed system", "system status"]

MUSIC_KEYWORDS = ["song", "music", "track", "album", "playlist", "artist",
                  "on spotify", "from spotify", "using spotify"]

SPOTIFY_WEB_KEYWORDS = ["web app", "web player", "in browser", "on the web", "browser"]

SPOTIFY_STRIP_KEYWORDS = ["spotify", "web app", "web player", "in browser",
                          "on the web", "browser", "song", "music", "track",
                          "album", "playlist", "artist", "on ", "from ",
                          "using ", "open ", "play ", "launch ", "start "]

APP_FILLERS = [
    "the ", "my ", "app ", "application ",
    "folder named ", "named ", "called ",
    " from my desktop", " from desktop",
    " from my documents", " from documents",
    " from my downloads", " from downloads",
    " on my desktop", " on desktop",
    " on my pc", " on my computer",
    " please", " now",
]


class OpenAppHandler(CommandHandler):
    def handle(self, ai, user_text: str, t: str, now: datetime.datetime) -> str | None:
        # If this targets 2+ devices at once ("open X on both"), that's
        # multi_device_handler.py's job — it runs earlier in the registry
        # so in practice this never fires, but keep the guard here too so
        # the two files' responsibilities stay honestly non-overlapping.
        if len(dev.resolve_devices(t)) > 1:
            return None
        # If this is explicitly targeting the phone only (by name or a
        # custom alias), defer to phone_handler.py even though it also
        # runs earlier — same defense-in-depth reasoning.
        if dev.resolve_devices(t) == {"phone"}:
            return None

        for prefix in OPEN_PREFIXES:
            if not t.startswith(prefix):
                continue
            app = t[len(prefix):].strip()

            # Block system/stats queries from being treated as app open
            if any(kw in app for kw in SYSTEM_KEYWORDS):
                return monitor.summary() if psutil_available else "psutil not installed."

            # Spotify: deterministic desktop-vs-web routing, bypasses the
            # LLM entirely so it's never left to chance.
            if "spotify" in app:
                wants_web = any(kw in app for kw in SPOTIFY_WEB_KEYWORDS)
                song_query = app
                for kw in SPOTIFY_STRIP_KEYWORDS:
                    song_query = song_query.replace(kw, "")
                song_query = song_query.strip()

                if wants_web:
                    return services.open_spotify_web(song_query)
                if song_query:
                    return services.open_spotify_search(song_query)
                return services.open_spotify_desktop()

            # Generic music request without saying "spotify" explicitly
            if any(kw in app for kw in MUSIC_KEYWORDS):
                for kw in MUSIC_KEYWORDS + ["open ", "play "]:
                    app = app.replace(kw, "")
                app = app.strip()
                if app:
                    return services.open_spotify_search(app)

            for filler in APP_FILLERS:
                app = app.replace(filler, "")
            # Strip trailing "on <desktop alias>" (e.g. "on laptop", or
            # whatever the user has named this machine) so an explicit
            # single-device desktop request doesn't leave a mangled app
            # name like "chrome on laptop".
            for alias in dev.alias_names_for("desktop"):
                app = app.replace(f" on {alias}", "").replace(f" on my {alias}", "")
            app = app.strip()
            if not app:
                return None

            # Desktop shortcut: scan desktop first if "desktop" mentioned
            if "desktop" in t:
                desktop = os.path.join(os.path.expanduser("~"), "Desktop")
                if os.path.exists(desktop):
                    for entry in os.scandir(desktop):
                        if app.lower() in entry.name.lower():
                            subprocess.Popen(f'explorer "{entry.path}"', shell=True)
                            return f"Opening {entry.name} from your desktop, {ai._addr()}."

            result = launcher.open(app)
            return f"Opening {app}, {ai._addr()}. {result}"

        return None


class CloseAppHandler(CommandHandler):
    def handle(self, ai, user_text: str, t: str, now: datetime.datetime) -> str | None:
        for prefix in CLOSE_PREFIXES:
            if not t.startswith(prefix):
                continue
            app = t[len(prefix):].strip()
            for filler in ["the ", "my ", "app ", "application "]:
                app = app.replace(filler, "")
            app = app.strip()
            if app:
                return launcher.close(app)
            return None
        return None
