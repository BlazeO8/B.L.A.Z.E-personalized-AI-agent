"""
B.L.A.Z.E — System Services
SystemMonitor, WeatherModule, NewsModule, SmartFileManager,
AppLauncher, and ReminderEngine.
"""

import os
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
    """
    Universal app/file/folder launcher for Windows.
    Priority order:
      1. Known Windows built-in commands
      2. Known Microsoft Store URI schemes
      3. Known web apps  
      4. Smart search: Start Menu, Desktop, common install paths
      5. Absolute path given by user
      6. os.startfile fallback
    """

    # ── Built-in Windows executables ──────────────────────────────────────────
    WIN = {
        "notepad":        "notepad",
        "calculator":     "calc",
        "paint":          "mspaint",
        "chrome":         "chrome",
        "google chrome":  "chrome",
        "firefox":        "firefox",
        "edge":           "msedge",
        "microsoft edge": "msedge",
        "explorer":       "explorer",
        "file explorer":  "explorer",
        "files":          "explorer",
        "task manager":   "taskmgr",
        "taskmgr":        "taskmgr",
        "vs code":        "code",
        "vscode":         "code",
        "visual studio code": "code",
        "cmd":            "cmd",
        "command prompt": "cmd",
        "terminal":       "wt",          # Windows Terminal
        "windows terminal": "wt",
        "powershell":     "powershell",
        "word":           "winword",
        "excel":          "excel",
        "powerpoint":     "powerpnt",
        "outlook":        "outlook",
        "vlc":            "vlc",
        "obs":            "obs64",
        "regedit":        "regedit",
        "snipping tool":  "snippingtool",
        "control panel":  "control",
        "paint 3d":       "ms-paint3d:",
        "wordpad":        "wordpad",
        "magnifier":      "magnify",
        "narrator":       "narrator",
        "on-screen keyboard": "osk",
        "character map":  "charmap",
        "disk cleanup":   "cleanmgr",
        "event viewer":   "eventvwr",
        "device manager": "devmgmt.msc",
        "services":       "services.msc",
        "task scheduler": "taskschd.msc",
        "resource monitor": "resmon",
        "performance monitor": "perfmon",
        "mstsc":          "mstsc",
        "remote desktop": "mstsc",
    }

    # ── Microsoft Store / UWP URI schemes ─────────────────────────────────────
    STORE = {
        "instagram":   "instagram:",
        "spotify":     "spotify:",
        "whatsapp":    "whatsapp:",
        "netflix":     "netflix:",
        "discord":     "discord:",
        "telegram":    "telegram:",
        "zoom":        "zoommtg:",
        "xbox":        "xbox:",
        "prime video": "primevideo:",
        "tiktok":      "tiktok:",
        "snapchat":    "snapchat:",
        "linkedin":    "linkedin:",
        "roblox":      "roblox:",
        "teams":       "msteams:",
        "microsoft teams": "msteams:",
        "settings":    "ms-settings:",
        "camera":      "microsoft.windows.camera:",
        "photos":      "ms-photos:",
        "maps":        "bingmaps:",
        "mail":        "outlookmail:",
        "calendar":    "outlookcal:",
        "store":       "ms-windows-store:",
        "microsoft store": "ms-windows-store:",
        "cortana":     "ms-cortana:",
        "get started": "ms-get-started:",
        "groove music": "mswindowsmusic:",
        "movies":      "mswindowsvideo:",
        "sticky notes": "ms-stickynotes:",
        "clock":       "ms-clock:",
        "alarms":      "ms-clock:",
        "weather":     "bingweather:",
        "news":        "bingnews:",
        "onenote":     "onenote:",
        "skype":       "skype:",
        "paint 3d":    "ms-paint3d:",
    }

    # ── Web apps (open in browser) ─────────────────────────────────────────────
    WEB = {
        "twitter": "https://twitter.com", "x": "https://x.com",
        "facebook": "https://facebook.com", "youtube": "https://youtube.com",
        "gmail": "https://mail.google.com", "google": "https://google.com",
        "github": "https://github.com", "reddit": "https://reddit.com",
        "twitch": "https://twitch.tv", "google drive": "https://drive.google.com",
        "google docs": "https://docs.google.com", "google sheets": "https://sheets.google.com",
        "google maps": "https://maps.google.com", "chatgpt": "https://chatgpt.com",
        "notion": "https://notion.so", "figma": "https://figma.com",
        "canva": "https://canva.com", "stackoverflow": "https://stackoverflow.com",
        "leetcode": "https://leetcode.com", "amazon": "https://amazon.in",
        "flipkart": "https://flipkart.com", "hotstar": "https://hotstar.com",
        "claude": "https://claude.ai", "perplexity": "https://perplexity.ai",
        "trello": "https://trello.com", "slack web": "https://app.slack.com",
        "github trending": "https://github.com/trending",
        "vercel": "https://vercel.com", "netlify": "https://netlify.com",
        "replit": "https://replit.com", "codepen": "https://codepen.io",
    }

    # ── Process names for close() ──────────────────────────────────────────────
    PROCESS_MAP = {
        "chrome": ["chrome.exe"], "google chrome": ["chrome.exe"],
        "firefox": ["firefox.exe"], "edge": ["msedge.exe"],
        "microsoft edge": ["msedge.exe"], "notepad": ["notepad.exe"],
        "calculator": ["calculatorapp.exe", "calculator.exe"],
        "paint": ["mspaint.exe"], "explorer": ["explorer.exe"],
        "file explorer": ["explorer.exe"], "task manager": ["taskmgr.exe"],
        "vs code": ["code.exe"], "vscode": ["code.exe"],
        "visual studio code": ["code.exe"],
        "spotify": ["spotify.exe"], "discord": ["discord.exe"],
        "telegram": ["telegram.exe"], "whatsapp": ["whatsapp.exe"],
        "zoom": ["zoom.exe"], "teams": ["teams.exe"],
        "microsoft teams": ["teams.exe"], "vlc": ["vlc.exe"],
        "steam": ["steam.exe"], "obs": ["obs64.exe", "obs32.exe"],
        "word": ["winword.exe"], "excel": ["excel.exe"],
        "powerpoint": ["powerpnt.exe"], "outlook": ["outlook.exe"],
        "cmd": ["cmd.exe"], "powershell": ["powershell.exe"],
        "terminal": ["cmd.exe", "powershell.exe", "WindowsTerminal.exe"],
        "roblox": ["RobloxPlayerBeta.exe"], "netflix": ["Netflix.exe"],
        "instagram": ["Instagram.exe"], "snapchat": ["Snapchat.exe"],
        "tiktok": ["TikTok.exe"], "snipping tool": ["SnippingTool.exe"],
        "skype": ["Skype.exe"], "onenote": ["ONENOTE.EXE"],
    }

    # ── Common install directories to search ───────────────────────────────────
    SEARCH_DIRS = [
        "{DESKTOP}",
        "{STARTMENU}",
        "C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs",
        "C:\\Program Files",
        "C:\\Program Files (x86)",
        "{LOCALAPPDATA}\\Programs",
        "{LOCALAPPDATA}",
        "{DOWNLOADS}",
        "{DOCUMENTS}",
        "{APPDATA}",
    ]

    def _resolve_dirs(self):
        """Resolve SEARCH_DIRS with actual user paths."""
        import os as _os
        home = _os.path.expanduser("~")
        return [
            d.replace("{DESKTOP}",      _os.path.join(home, "Desktop"))
             .replace("{STARTMENU}",    _os.path.join(home, "AppData", "Roaming", "Microsoft", "Windows", "Start Menu", "Programs"))
             .replace("{LOCALAPPDATA}", _os.path.join(home, "AppData", "Local"))
             .replace("{DOWNLOADS}",    _os.path.join(home, "Downloads"))
             .replace("{DOCUMENTS}",    _os.path.join(home, "Documents"))
             .replace("{APPDATA}",      _os.path.join(home, "AppData", "Roaming"))
            for d in self.SEARCH_DIRS
        ]

    def _search_filesystem(self, name: str) -> str | None:
        """
        Multi-strategy app search:
        1. Windows 'where' command (PATH-based, finds installed CLI apps)
        2. PowerShell Get-StartApps (finds ALL Start Menu + Store apps by name)
        3. Registry uninstall keys (finds anything installed via installer)
        4. Manual filesystem scan (Desktop, Program Files, Downloads etc.)
        """
        import glob, winreg
        n = name.lower().strip()
        user = os.environ.get("USERNAME", os.environ.get("USER", ""))

        # ── Strategy 1: Windows WHERE command ────────────────────────────────
        try:
            result = subprocess.run(
                ["where", name], capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0:
                path = result.stdout.strip().splitlines()[0]
                if os.path.exists(path):
                    return path
        except Exception:
            pass

        # ── Strategy 2: PowerShell Get-StartApps (finds Store + Start Menu) ──
        try:
            ps = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-StartApps | Where-Object {$_.Name -like '*" + name + "*'} | Select-Object -First 1 -ExpandProperty AppID"],
                capture_output=True, text=True, timeout=5
            )
            app_id = ps.stdout.strip()
            if app_id:
                return "shell:appsfolder\\" + app_id
                return "shell:appsfolder\\" + app_id
        except Exception:
            pass

        # ── Strategy 3: Registry uninstall scan ───────────────────────────────
        reg_paths = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        ]
        for reg_path in reg_paths:
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path)
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        sub = winreg.OpenKey(key, winreg.EnumKey(key, i))
                        try:
                            disp = winreg.QueryValueEx(sub, "DisplayName")[0].lower()
                            if n in disp or disp in n:
                                try:
                                    loc = winreg.QueryValueEx(sub, "InstallLocation")[0]
                                    if loc and os.path.exists(loc):
                                        exes = []
                                        for root_d, dirs_d, files_d in os.walk(loc):
                                            for f in files_d:
                                                if f.lower().endswith(".exe"):
                                                    fp = os.path.join(root_d, f)
                                                    exes.append((os.path.getsize(fp), fp))
                                        if exes:
                                            # Prefer exe with app name in it
                                            for sz, fp in exes:
                                                if n in os.path.basename(fp).lower():
                                                    return fp
                                            # Otherwise return the largest exe (likely main)
                                            exes.sort(reverse=True)
                                            return exes[0][1]
                                except Exception:
                                    pass
                        except Exception:
                            pass
                    except Exception:
                        continue
            except Exception:
                continue

        # ── Strategy 4: Filesystem scan ───────────────────────────────────────
        for base in self._resolve_dirs():
            if not os.path.exists(base):
                continue
            for ext in ("*.lnk", "*.exe", "*.url"):
                try:
                    for match in glob.glob(os.path.join(base, "**", ext), recursive=True):
                        fname = os.path.splitext(os.path.basename(match))[0].lower()
                        if n in fname or fname in n:
                            return match
                except Exception:
                    continue
            try:
                for entry in os.scandir(base):
                    if entry.is_dir() and n in entry.name.lower():
                        return entry.path
            except Exception:
                continue

        return None

    def open(self, app_name: str) -> str:
        import os as _os
        app = app_name.lower().strip()
        user = _os.environ.get("USERNAME", _os.environ.get("USER", ""))

        # 0. Special folder keywords
        special = {
            "downloads":  rf"C:\Users\{user}\Downloads",
            "documents":  rf"C:\Users\{user}\Documents",
            "desktop":    rf"C:\Users\{user}\Desktop",
            "pictures":   rf"C:\Users\{user}\Pictures",
            "music":      rf"C:\Users\{user}\Music",
            "videos":     rf"C:\Users\{user}\Videos",
            "appdata":    rf"C:\Users\{user}\AppData\Roaming",
        }
        if app in special:
            try:
                _os.startfile(special[app])
                return f"Opening {app} folder, sir."
            except Exception as e:
                return f"Could not open {app} folder: {e}"

        # 1. Absolute path given directly
        if os.path.exists(app_name):
            try:
                os.startfile(app_name)
                return f"Opened '{app_name}', sir."
            except Exception as e:
                return f"Could not open path: {e}"

        # 2. Built-in Windows command
        if app in self.WIN:
            try:
                subprocess.Popen(["cmd", "/c", "start", "", self.WIN[app]],
                                 shell=False)
                return f"Opening {app_name}, sir."
            except Exception as e:
                return f"Could not launch {app_name}: {e}"

        # 3. Microsoft Store URI — use ShellExecute (most reliable for URI schemes)
        if app in self.STORE:
            uri = self.STORE[app]
            try:
                import ctypes
                ctypes.windll.shell32.ShellExecuteW(None, "open", uri, None, None, 1)
                return f"Launching {app_name}, sir."
            except Exception:
                pass
            try:
                subprocess.Popen(["cmd", "/c", "start", "", uri], shell=False)
                return f"Launching {app_name}, sir."
            except Exception as e:
                return f"Could not launch {app_name}: {e}"

        # 4. Web app
        if app in self.WEB:
            webbrowser.open(self.WEB[app])
            return f"Opening {app_name} in browser, sir."

        # 5. Smart filesystem / registry / Start Menu search
        found = self._search_filesystem(app_name)
        if found:
            try:
                if found.startswith("shell:appsfolder"):
                    subprocess.Popen(['explorer', found], shell=False)
                else:
                    os.startfile(found)
                return f"Found and opened '{app_name}', sir."
            except Exception as e:
                return f"Found '{app_name}' but could not open it: {e}"

        # 6. Last resort — try running the name directly via shell
        try:
            subprocess.Popen(["cmd", "/c", "start", "", app_name], shell=False)
            return f"Attempting to open '{app_name}', sir."
        except Exception as e:
            return f"Could not find or open '{app_name}'. Try saying the exact file path, sir."

    def close(self, app_name: str) -> str:
        app = app_name.lower().strip()

        targets = self.PROCESS_MAP.get(app)
        if not targets:
            safe = re.sub(r"[^\w]", "", app)
            targets = [safe + ".exe"]

        killed = []
        for proc in targets:
            try:
                result = subprocess.run(
                    ["taskkill", "/F", "/IM", proc],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    killed.append(proc)
            except Exception:
                pass

        if killed:
            return f"{app_name.title()} closed successfully, sir."

        # Fallback: kill by window title
        try:
            safe = re.sub(r"[^\w\s]", "", app_name).strip()
            subprocess.run(
                ["taskkill", "/F", "/FI", f"WINDOWTITLE eq *{safe}*"],
                capture_output=True
            )
            return f"Attempted to close {app_name}, sir."
        except Exception:
            return f"Could not find a running process for '{app_name}', sir."


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