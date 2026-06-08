"""
B.L.A.Z.E — AI Engine
Groq LLM integration, TTS, system command dispatch, and feedback logging.
"""

import re
import time
import queue
import threading
import webbrowser
import datetime

from blaze.config import GROQ_API_KEY, MODEL, MAX_HISTORY
from blaze.deps import Groq, groq_available, pyttsx3, tts_available, psutil, psutil_available
from blaze.core.database import db
from blaze.core.security import vault
from blaze.core.logging_audit import log
from blaze.intelligence.nlp import nlp
from blaze.intelligence.emotional import ei
from blaze.intelligence.learner import learner
from blaze.intelligence.domain import build_system_prompt
from blaze.services.system_monitor import (
    monitor, weather, news_module, filemanager, launcher,
)
from blaze.services.integrations import services


class BlazeAI:
    def __init__(self):
        try:
            self.client = Groq(api_key=GROQ_API_KEY) if (groq_available and GROQ_API_KEY) else None
        except Exception as e:
            log.error(f"Groq client init failed: {e}")
            self.client = None

        self.history          = db.load_history()
        self.tts_engine       = None
        self.tts_queue        = queue.Queue()
        self.voice_enabled    = db.get_pref("voice_enabled", "true") == "true"
        self._last_user_msg   = ""
        self._last_blaze_msg  = ""
        self._reminder_engine = None  # set after GUI init

        # TTS init
        if tts_available:
            try:
                from blaze.ai.persona import persona
                self.tts_engine = pyttsx3.init()
                voices = self.tts_engine.getProperty("voices")
                for v in voices:
                    if any(p in v.name.lower() for p in ["david", "mark", "daniel", "english"]):
                        self.tts_engine.setProperty("voice", v.id)
                        break
                self.tts_engine.setProperty("rate",   persona.tts_speed)
                self.tts_engine.setProperty("volume", 0.95)
                threading.Thread(target=self._tts_worker, daemon=True).start()
            except Exception as e:
                log.warning(f"TTS: {e}")
                self.tts_engine = None

    def _tts_worker(self):
        while True:
            text = self.tts_queue.get()
            if text is None:
                break
            if not self.tts_engine:
                continue
            try:
                self.tts_engine.say(text)
                self.tts_engine.runAndWait()
            except Exception:
                try:
                    from blaze.ai.persona import persona
                    self.tts_engine = pyttsx3.init()
                    self.tts_engine.setProperty("rate", persona.tts_speed)
                except Exception:
                    self.tts_engine = None

    def speak(self, text):
        if not self.voice_enabled or not self.tts_engine:
            return
        clean = re.sub(r"\[SYSTEM:[^\]]+\]", "", text)
        clean = re.sub(r"[*_`#]", "", clean).strip()
        if clean:
            self.tts_queue.put(clean)

    def stop_speaking(self):
        if self.tts_engine:
            try:
                self.tts_engine.stop()
            except Exception:
                pass

    # ── Main chat method ──────────────────────────────────────────────────────
    def chat(self, user_text):
        if not self.client:
            return (
                "GROQ_API_KEY not configured, sir. "
                "Add it to your .env file. Free key at console.groq.com"
            )

        nlp_result = nlp.analyze(user_text)
        intent     = nlp_result["intent"]
        emotion    = nlp_result["emotion"]

        # Custom command check
        for trigger, response, action in db.get_custom_commands():
            if trigger.lower() in user_text.lower():
                result = response
                if action:
                    result += f" [SYSTEM:open_app:{action}]"
                return result

        # Reminder shortcut
        if intent == "reminder" and self._reminder_engine is not None:
            result = self._reminder_engine.parse_and_add(user_text)
            if result:
                return result

        learner.record(user_text[:40])
        db.log_command(user_text[:60])

        self._last_user_msg = user_text
        self.history.append({"role": "user", "content": user_text})
        db.save_message("user", user_text, emotion)
        if len(self.history) > MAX_HISTORY:
            self.history = self.history[-MAX_HISTORY:]

        empathy = ""
        if emotion != "neutral":
            empathy = ei.get_empathetic_prefix(emotion)

        try:
            last_err = None
            for attempt in range(3):
                try:
                    response = self.client.chat.completions.create(
                        model=MODEL,
                        messages=[
                            {"role": "system", "content": build_system_prompt(nlp_result)}
                        ] + self.history,
                        max_tokens=1024,
                        temperature=0.72,
                    )
                    break
                except Exception as e:
                    last_err = e
                    err_str  = str(e).lower()
                    if "rate" in err_str or "429" in err_str or "500" in err_str or "503" in err_str:
                        wait = 2 ** attempt
                        log.warning(f"Groq transient error (attempt {attempt+1}/3), retrying in {wait}s: {e}")
                        time.sleep(wait)
                        continue
                    raise
            else:
                raise last_err

            reply = response.choices[0].message.content
            if empathy and emotion in ["sad", "stress", "angry"]:
                reply = empathy + "\n\n" + reply
            self.history.append({"role": "assistant", "content": reply})
            db.save_message("assistant", reply, "neutral")
            self._last_blaze_msg = reply
            return reply

        except Exception as e:
            err = str(e)
            log.error(f"Chat error: {err}")
            if "api_key" in err.lower() or "auth" in err.lower():
                return "Invalid API key, sir. Check console.groq.com"
            if "rate" in err.lower():
                return "Rate limit hit, sir. Groq free tier — try again shortly."
            return f"Neural core error, sir: {err}"

    # ── System command dispatcher ─────────────────────────────────────────────
    def execute_system_commands(self, reply):
        results  = []
        seen_cmds = set()

        # Pre-scan: if reply has web_search or open_url, skip any open_app tags
        # (LLM often emits both, causing two browser tabs)
        all_tags = re.findall(r"\[SYSTEM:([^\]]+)\]", reply)
        has_browser_cmd = any(
            t.split(":", 1)[0] in ("web_search", "open_url")
            for t in all_tags
        )
        browser_opened = False

        for tag in all_tags:
            parts = tag.split(":", 1)
            cmd   = parts[0]
            arg   = parts[1] if len(parts) > 1 else ""

            # Skip exact duplicates
            key = f"{cmd}:{arg}"
            if key in seen_cmds:
                continue
            seen_cmds.add(key)

            # If we already have a web_search/open_url, skip open_app entirely
            if has_browser_cmd and cmd == "open_app":
                continue

            # Only ever open one browser tab per reply
            if cmd in ("web_search", "open_url"):
                if browser_opened:
                    continue
                browser_opened = True

            result = self._dispatch(cmd, arg)
            if result:
                results.append(result)
        return results

    def _dispatch(self, cmd, arg):
        if cmd == "open_app":
            return launcher.open(arg)
        if cmd == "web_search":
            webbrowser.open(f"https://google.com/search?q={arg.replace(' ', '+')}")
            return f"Searching: {arg}"
        if cmd == "open_url":
            webbrowser.open(arg if arg.startswith("http") else f"https://{arg}")
            return f"Opening {arg}"
        if cmd == "weather":
            return weather.summary_str()
        if cmd == "system_stats":
            return monitor.summary()
        if cmd == "news":
            h = news_module.get_headlines(5)
            return ("Top headlines:\n" + "\n".join(f"• {x}" for x in h)) if h else "News unavailable."
        if cmd == "organize_downloads":
            return filemanager.organize_downloads()
        if cmd == "find_file":
            r = filemanager.find_files(arg)
            return "\n".join(r) if r else f"No files matching '{arg}'"
        if cmd == "disk_summary":
            return filemanager.disk_summary()
        if cmd == "list_processes":
            if not psutil_available:
                return "psutil not installed."
            procs = sorted(
                psutil.process_iter(["name", "cpu_percent"]),
                key=lambda p: p.info["cpu_percent"] or 0,
                reverse=True
            )[:8]
            return "Top processes:\n" + "\n".join(
                f"• {p.info['name']}: {p.info['cpu_percent']:.1f}%" for p in procs
            )
        if cmd == "add_reminder":
            if "|" in arg:
                msg, ts = arg.split("|", 1)
                try:
                    h, mi = map(int, ts.strip().split(":"))
                    fire  = datetime.datetime.now().replace(hour=h, minute=mi, second=0)
                    if fire < datetime.datetime.now():
                        fire += datetime.timedelta(days=1)
                    db.add_reminder(msg.strip(), fire)
                    return f"Reminder set: {msg.strip()} at {fire.strftime('%I:%M %p')}"
                except Exception as e:
                    return f"Could not parse reminder time '{ts.strip()}', sir. Use HH:MM format. ({e})"
            return "Reminder format error, sir. Expected: message|HH:MM"
        if cmd == "list_reminders":
            rows = db.get_all_reminders()
            return ("\n".join(f"• {m} @ {f[11:16]}" for _, m, f in rows)) if rows else "No pending reminders, sir."
        if cmd == "save_note":
            if "|" in arg:
                title, content = arg.split("|", 1)
                db.save_note(title.strip(), content.strip())
                return f"Note saved: {title.strip()}"
        if cmd == "search_notes":
            rows = db.search_notes(arg)
            return ("\n".join(f"• [{d}] {t}: {c[:60]}..." for t, c, d in rows)) if rows else f"No notes for '{arg}'"
        if cmd == "vault_set":
            if "|" in arg:
                k, v = arg.split("|", 1)
                vault.set(k.strip(), v.strip())
                return f"Stored '{k.strip()}' in secure vault, sir."
        if cmd == "vault_get":
            v = vault.get(arg.strip())
            return f"{arg}: {v}" if v else f"No vault entry for '{arg}'"
        if cmd == "vault_list":
            keys = vault.list_keys()
            return ("Vault keys:\n" + "\n".join(f"• {k}" for k in keys)) if keys else "Vault is empty, sir."
        if cmd == "define":
            return services.define_word(arg)
        if cmd == "wiki":
            return services.wiki_summary(arg)
        if cmd == "currency":
            if "|" in arg:
                parts = arg.split("|")
                if len(parts) == 3:
                    try:
                        return services.convert_currency(float(parts[0].strip()), parts[1].strip(), parts[2].strip())
                    except ValueError:
                        return "Currency format error, sir. Use: amount|FROM|TO (e.g. 100|USD|INR)"
        if cmd == "github_repos":      return services.github_repos(arg)
        if cmd == "github_trending":   return services.github_trending()
        if cmd == "open_drive":        return services.open_drive()
        if cmd == "search_drive":      return services.search_drive(arg)
        if cmd == "open_spotify":      return services.open_spotify_search(arg)
        if cmd == "ip_info":           return services.ip_info()
        if cmd == "top_commands":
            rows = db.get_top_commands()
            return "Most used:\n" + "\n".join(f"• {c}: {n}x" for c, n in rows)
        if cmd == "clear_history":
            db.clear_history()
            self.history.clear()
            return "History cleared, sir."
        if cmd == "habit_summary":     return learner.weekly_summary()
        if cmd == "feedback_stats":    return learner.get_feedback_stats()

        # Fall through to plugin system
        from blaze.plugins.manager import plugins
        return plugins.dispatch(cmd, arg)

    def save_feedback(self, rating: int):
        db.save_feedback(self._last_user_msg, self._last_blaze_msg, rating)
        return f"Thank you, sir. Rating of {rating}/5 recorded."