"""
B.L.A.Z.E — System Services
SystemMonitor, WeatherModule, NewsModule, SmartFileManager,
AppLauncher, and ReminderEngine.
"""

import re
import time
import shutil
import platform
import datetime
import threading
import subprocess
import webbrowser
from pathlib import Path

from blaze.config import CITY, NEWS_API
from blaze.deps import requests, requests_available, psutil, psutil_available
from blaze.core.database import db
from blaze.core.logging_audit import log


# ══════════════════════════════════════════════════════════════════════════════
#  System Monitor
# ══════════════════════════════════════════════════════════════════════════════
class SystemMonitor:
    def __init__(self):
        self.available   = psutil_available
        self._cache      = {}
        self._cache_time = 0

    def _refresh(self):
        if time.time() - self._cache_time < 2 or not self.available:
            return
        try:
            _disk_path = "C:\\" if platform.system() == "Windows" else "/"
            self._cache = {
                "cpu":   psutil.cpu_percent(interval=None),
                "ram":   psutil.virtual_memory().percent,
                "disk":  psutil.disk_usage(_disk_path).percent,
                "bat":   psutil.sensors_battery(),
                "procs": len(psutil.pids()),
            }
            self._cache_time = time.time()
        except Exception as e:
            log.warning(f"Monitor: {e}")

    def cpu(self):   self._refresh(); return self._cache.get("cpu", 0)
    def ram(self):   self._refresh(); return self._cache.get("ram", 0)
    def disk(self):  self._refresh(); return self._cache.get("disk", 0)
    def procs(self): self._refresh(); return self._cache.get("procs", 0)

    def battery(self):
        self._refresh()
        bat = self._cache.get("bat")
        return {"percent": round(bat.percent), "plugged": bat.power_plugged} if bat else None

    def summary(self):
        if not self.available:
            return "psutil not installed."
        parts = [f"CPU: {self.cpu():.0f}%", f"RAM: {self.ram():.0f}%", f"Disk: {self.disk():.0f}%"]
        bat = self.battery()
        if bat:
            plug = "⚡" if bat["plugged"] else "🔋"
            parts.append(f"Battery: {bat['percent']}% {plug}")
        return " | ".join(parts)

    def alert_check(self):
        alerts = []
        if self.cpu()  > 85: alerts.append(f"CPU at {self.cpu():.0f}% — high load")
        if self.ram()  > 90: alerts.append(f"RAM at {self.ram():.0f}% — memory pressure")
        if self.disk() > 92: alerts.append(f"Disk at {self.disk():.0f}% — storage low")
        bat = self.battery()
        if bat and not bat["plugged"] and bat["percent"] < 15:
            alerts.append(f"Battery critical — {bat['percent']}%")
        return alerts


# ══════════════════════════════════════════════════════════════════════════════
#  Weather
# ══════════════════════════════════════════════════════════════════════════════
class WeatherModule:
    WMO = {
        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Foggy", 51: "Light drizzle", 61: "Light rain", 63: "Rain", 65: "Heavy rain",
        71: "Light snow", 73: "Snow", 80: "Rain showers", 95: "Thunderstorm",
    }

    def __init__(self):
        self._cache      = None
        self._cache_time = 0

    def get(self, city=CITY):
        if self._cache and time.time() - self._cache_time < 600:
            return self._cache
        if not requests_available:
            return {"error": "requests not installed"}
        result = self._get_open_meteo(city) or self._get_wttr(city)
        if result and "error" not in result:
            self._cache      = result
            self._cache_time = time.time()
        return result or {"error": "All weather sources failed"}

    def _get_open_meteo(self, city):
        """Primary source: open-meteo (free, no key needed)."""
        try:
            geo = requests.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": city, "count": 1, "format": "json"}, timeout=10
            )
            if not geo.ok or not geo.json().get("results"):
                return None
            loc = geo.json()["results"][0]
            lat, lon = loc["latitude"], loc["longitude"]

            w = requests.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code",
                "timezone": "auto",
            }, timeout=10)
            if not w.ok:
                return None
            data = w.json()
            if "current" not in data:
                return None
            c = data["current"]
            return {
                "temp_c":   round(c["temperature_2m"]),
                "desc":     self.WMO.get(c.get("weather_code", 0), "Unknown"),
                "humidity": c["relative_humidity_2m"],
                "feels":    round(c["apparent_temperature"]),
                "city":     loc.get("name", city),
            }
        except Exception as e:
            log.warning(f"open-meteo failed: {e}")
            return None

    def _get_wttr(self, city):
        """Fallback source: wttr.in (no key, single request)."""
        try:
            r = requests.get(
                f"https://wttr.in/{city.replace(' ', '+')}",
                params={"format": "j1"},
                timeout=10,
                headers={"User-Agent": "BLAZE/1.0"},
            )
            if not r.ok:
                return None
            data    = r.json()
            current = data["current_condition"][0]
            area    = data.get("nearest_area", [{}])[0]
            city_name = (
                area.get("areaName", [{}])[0].get("value", city)
            )
            return {
                "temp_c":   int(current["temp_C"]),
                "desc":     current["weatherDesc"][0]["value"],
                "humidity": int(current["humidity"]),
                "feels":    int(current["FeelsLikeC"]),
                "city":     city_name,
            }
        except Exception as e:
            log.warning(f"wttr.in fallback failed: {e}")
            return None

    def summary_str(self):
        w = self.get()
        if "error" in w:
            return f"Weather unavailable ({w['error']})"
        return (
            f"{w['city']}: {w['temp_c']}°C, {w['desc']} "
            f"(feels {w['feels']}°C, {w['humidity']}% humidity)"
        )


# ══════════════════════════════════════════════════════════════════════════════
#  News
# ══════════════════════════════════════════════════════════════════════════════
class NewsModule:
    def get_headlines(self, count=5):
        if not requests_available:
            return []
        try:
            if NEWS_API:
                r = requests.get(
                    "https://newsapi.org/v2/top-headlines",
                    params={"apiKey": NEWS_API, "language": "en", "pageSize": count},
                    timeout=5
                )
                if r.ok:
                    return [a["title"] for a in r.json().get("articles", [])]
            r = requests.get("https://feeds.bbci.co.uk/news/rss.xml", timeout=5)
            if r.ok:
                titles = re.findall(r"<title><!\[CDATA\[(.+?)\]\]></title>", r.text)
                return [t for t in titles if "BBC" not in t][:count]
        except Exception as e:
            log.warning(f"News: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════════
#  File Manager
# ══════════════════════════════════════════════════════════════════════════════
class SmartFileManager:
    CATS = {
        "Images":    [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"],
        "Videos":    [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv"],
        "Audio":     [".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"],
        "Documents": [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".md"],
        "Archives":  [".zip", ".rar", ".7z", ".tar", ".gz"],
        "Code":      [".py", ".js", ".ts", ".html", ".css", ".java", ".cpp", ".c", ".go"],
        "Data":      [".json", ".xml", ".csv", ".yaml", ".sql"],
    }

    def organize_downloads(self):
        dl = Path.home() / "Downloads"
        if not dl.exists():
            return "Downloads folder not found."
        moved = 0
        for f in dl.iterdir():
            if f.is_file():
                for cat, exts in self.CATS.items():
                    if f.suffix.lower() in exts:
                        dest = dl / cat
                        dest.mkdir(exist_ok=True)
                        try:
                            shutil.move(str(f), str(dest / f.name))
                            moved += 1
                        except Exception:
                            pass
                        break
        return f"Organized {moved} files in Downloads, sir."

    def find_files(self, query, timeout_sec: float = 5.0):
        """Search home directory for files matching query with a hard timeout."""
        results: list = []
        done_event    = threading.Event()

        def _scan():
            try:
                for f in Path.home().rglob(f"*{query}*"):
                    if done_event.is_set():
                        break
                    if len(results) >= 10:
                        break
                    results.append(str(f))
            except (PermissionError, OSError):
                pass
            finally:
                done_event.set()

        worker = threading.Thread(target=_scan, daemon=True)
        worker.start()
        done_event.wait(timeout=timeout_sec)
        if not done_event.is_set():
            done_event.set()
        return results

    def disk_summary(self):
        if not psutil_available:
            return "psutil not installed."
        try:
            disk_path = "C:\\" if platform.system() == "Windows" else str(Path.home())
            u = psutil.disk_usage(disk_path)
            return (
                f"Disk: {u.used//1024**3}GB used / "
                f"{u.total//1024**3}GB total "
                f"({u.free//1024**3}GB free)"
            )
        except Exception as e:
            return f"Disk info error: {e}"


# ══════════════════════════════════════════════════════════════════════════════
#  App Launcher
# ══════════════════════════════════════════════════════════════════════════════
class AppLauncher:
    STORE = {
        "instagram": "start instagram:", "spotify": "start spotify:",
        "whatsapp":  "start whatsapp:",  "netflix":  "start netflix:",
        "discord":   "start discord:",   "telegram": "start telegram:",
        "zoom":      "start zoommtg:",   "xbox":     "start xbox:",
        "prime video":"start primevideo:","tiktok":  "start tiktok:",
        "snapchat":  "start snapchat:",  "linkedin": "start linkedin:",
        "roblox":    "start roblox:",    "teams":    "start msteams:",
    }
    WEB = {
        "twitter":       "https://twitter.com",
        "x":             "https://x.com",
        "facebook":      "https://facebook.com",
        "youtube":       "https://youtube.com",
        "gmail":         "https://mail.google.com",
        "google":        "https://google.com",
        "github":        "https://github.com",
        "reddit":        "https://reddit.com",
        "twitch":        "https://twitch.tv",
        "google drive":  "https://drive.google.com",
        "google docs":   "https://docs.google.com",
        "google sheets": "https://sheets.google.com",
        "google maps":   "https://maps.google.com",
        "chatgpt":       "https://chatgpt.com",
        "notion":        "https://notion.so",
        "figma":         "https://figma.com",
        "canva":         "https://canva.com",
        "stackoverflow": "https://stackoverflow.com",
        "leetcode":      "https://leetcode.com",
        "amazon":        "https://amazon.in",
        "flipkart":      "https://flipkart.com",
        "hotstar":       "https://hotstar.com",
        "claude":        "https://claude.ai",
        "perplexity":    "https://perplexity.ai",
        "trello":        "https://trello.com",
        "slack":         "https://app.slack.com",
        "github trending":"https://github.com/trending",
    }
    WIN = {
        "notepad":       "notepad",
        "calculator":    "calc",
        "paint":         "mspaint",
        "chrome":        "start chrome",
        "google chrome": "start chrome",
        "firefox":       "start firefox",
        "edge":          "start msedge",
        "explorer":      "explorer",
        "file explorer": "explorer",
        "task manager":  "taskmgr",
        "vs code":       "code",
        "vscode":        "code",
        "terminal":      "start cmd",
        "cmd":           "start cmd",
        "powershell":    "start powershell",
        "word":          "start winword",
        "excel":         "start excel",
        "powerpoint":    "start powerpnt",
        "outlook":       "start outlook",
        "vlc":           "start vlc",
        "steam":         "start steam:",
        "obs":           "start obs64",
        "settings":      "start ms-settings:",
        "camera":        "start microsoft.windows.camera:",
        "snipping tool": "snippingtool",
        "control panel": "control",
        "regedit":       "regedit",
    }

    def open(self, app_name):
        app      = app_name.lower().strip()
        sys_name = platform.system()
        if sys_name == "Windows":
            if app in self.STORE:
                subprocess.Popen(["cmd", "/c", self.STORE[app]])
                return f"Launching {app_name} via Store, sir."
            if app in self.WEB:
                webbrowser.open(self.WEB[app])
                return f"Opening {app_name} in browser, sir."
            if app in self.WIN:
                subprocess.Popen(self.WIN[app].split(), shell=False)
                return f"Opening {app_name}, sir."
            safe_name = re.sub(r"[^\w\s.-]", "", app_name).strip()
            if safe_name:
                subprocess.Popen(["cmd", "/c", "start", "", safe_name])
            return f"Attempting to open {app_name}, sir."
        elif sys_name == "Darwin":
            if app in self.WEB:
                webbrowser.open(self.WEB[app])
                return f"Opening {app_name}, sir."
            safe_name = re.sub(r"[^\w\s.-]", "", app_name).strip()
            if safe_name:
                subprocess.Popen(["open", "-a", safe_name])
            return f"Opening {app_name} on macOS, sir."
        else:
            if app in self.WEB:
                webbrowser.open(self.WEB[app])
                return f"Opening {app_name}, sir."
            safe_name = re.sub(r"[^\w\s.-]", "", app_name).strip()
            try:
                subprocess.Popen([safe_name])
                return f"Launching {app_name}, sir."
            except FileNotFoundError:
                return f"'{app_name}' not found on this system."


# ══════════════════════════════════════════════════════════════════════════════
#  Reminder Engine
# ══════════════════════════════════════════════════════════════════════════════
class ReminderEngine:
    def __init__(self, callback):
        self.callback = callback
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            try:
                for msg in db.get_due_reminders():
                    self.callback(msg)
            except Exception as e:
                log.error(f"Reminder: {e}")
            time.sleep(30)

    def parse_and_add(self, text):
        now = datetime.datetime.now()
        m   = re.search(r'in (\d+)\s*(minute|min|hour|hr)', text, re.I)
        if m:
            n, unit = int(m.group(1)), m.group(2).lower()
            delta   = datetime.timedelta(minutes=n) if "m" in unit else datetime.timedelta(hours=n)
            fire    = now + delta
            msg     = re.sub(r'(remind me (to)?|in \d+ \w+)', '', text, flags=re.I).strip() or text
            db.add_reminder(msg, fire)
            return f"Reminder set for {fire.strftime('%I:%M %p')}: {msg}"
        m = re.search(r'at (\d{1,2}):(\d{2})\s*(am|pm)?', text, re.I)
        if m:
            h, mi  = int(m.group(1)), int(m.group(2))
            ampm   = (m.group(3) or "").lower()
            if ampm == "pm" and h < 12: h += 12
            if ampm == "am" and h == 12: h = 0
            fire   = now.replace(hour=h, minute=mi, second=0, microsecond=0)
            if fire < now: fire += datetime.timedelta(days=1)
            msg    = re.sub(r'(remind me (to)?|at \d{1,2}:\d{2}\s*\w*)', '', text, flags=re.I).strip() or text
            db.add_reminder(msg, fire)
            return f"Reminder set for {fire.strftime('%I:%M %p')}: {msg}"
        return None


# ── Singletons ────────────────────────────────────────────────────────────────
monitor     = SystemMonitor()
weather     = WeatherModule()
news_module = NewsModule()
filemanager = SmartFileManager()
launcher    = AppLauncher()