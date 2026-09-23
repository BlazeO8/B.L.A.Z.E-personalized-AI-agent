"""
B.L.A.Z.E — Automation Rules Engine
Users can create rules like:
  "every morning at 8am open Chrome and Spotify"
  "when I say work mode, open VS Code and close Discord"
"""

import os
import json
import datetime
import threading
from blaze.core.logging_audit import log

RULES_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "automations.json")


class AutomationEngine:
    def __init__(self, executor_callback=None):
        self._rules    = []
        self._callback = executor_callback  # fn(list_of_commands)
        self._thread   = None
        self._load()

    def _load(self):
        try:
            os.makedirs(os.path.dirname(RULES_FILE), exist_ok=True)
            if os.path.exists(RULES_FILE):
                with open(RULES_FILE) as f:
                    self._rules = json.load(f)
            else:
                self._rules = []
                self._save()
        except Exception as e:
            log.warning(f"Automations load: {e}")
            self._rules = []

    def _save(self):
        try:
            with open(RULES_FILE, "w") as f:
                json.dump(self._rules, f, indent=2)
        except Exception as e:
            log.warning(f"Automations save: {e}")

    def add_rule(self, name: str, trigger: str, actions: list, time_str: str = None) -> str:
        """
        Add an automation rule.
        trigger: "morning" | "work mode" | "time:08:00" | "keyword:xyz"
        actions: ["open chrome", "open spotify", "close discord"]
        time_str: "08:00" for time-based rules
        """
        rule = {
            "name": name,
            "trigger": trigger.lower(),
            "actions": actions,
            "time": time_str,
            "enabled": True
        }
        # Remove existing rule with same name
        self._rules = [r for r in self._rules if r["name"].lower() != name.lower()]
        self._rules.append(rule)
        self._save()
        log.info(f"Automation added: {name}")
        return f"Automation '{name}' saved, sir. It will run when you say '{trigger}'."

    def check_trigger(self, text: str) -> list:
        """Check if user text matches any keyword trigger. Returns list of actions."""
        t = text.lower()
        matched = []
        for rule in self._rules:
            if not rule.get("enabled"):
                continue
            trigger = rule.get("trigger", "")
            if trigger.startswith("keyword:"):
                keyword = trigger[8:]
                if keyword in t:
                    matched.extend(rule.get("actions", []))
            elif trigger in t:
                matched.extend(rule.get("actions", []))
        return matched

    def list_rules(self) -> str:
        if not self._rules:
            return "No automation rules set up yet, sir."
        lines = []
        for r in self._rules:
            status = "ON" if r.get("enabled") else "OFF"
            time_info = f" at {r['time']}" if r.get("time") else ""
            lines.append(f"• {r['name']} [{status}]{time_info}: {', '.join(r['actions'])}")
        return "Your automations:\n" + "\n".join(lines)

    def delete_rule(self, name: str) -> str:
        before = len(self._rules)
        self._rules = [r for r in self._rules if r["name"].lower() != name.lower()]
        self._save()
        return f"Automation '{name}' deleted." if len(self._rules) < before else f"No rule named '{name}' found."

    def start_scheduler(self, callback):
        """Start background thread that fires time-based rules."""
        self._callback = callback
        self._thread   = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._thread.start()
        log.info("Automation scheduler started.")

    def _scheduler_loop(self):
        import time
        fired_today = set()
        while True:
            try:
                now  = datetime.datetime.now()
                key  = now.strftime("%H:%M")
                date = now.strftime("%Y-%m-%d")
                for rule in self._rules:
                    if not rule.get("enabled") or not rule.get("time"):
                        continue
                    rule_key = f"{date}_{rule['name']}"
                    if rule["time"] == key and rule_key not in fired_today:
                        fired_today.add(rule_key)
                        log.info(f"Automation fired: {rule['name']}")
                        if self._callback:
                            self._callback(rule["actions"])
                # Clear fired set at midnight
                if key == "00:00":
                    fired_today.clear()
            except Exception as e:
                log.warning(f"Scheduler error: {e}")
            time.sleep(30)


automation = AutomationEngine()
