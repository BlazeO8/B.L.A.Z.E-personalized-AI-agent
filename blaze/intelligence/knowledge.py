"""
B.L.A.Z.E — Personal Knowledge Base
User can add custom facts, preferences, and personal info.
BLAZE reads this on every query so it always knows about you.
"""

import os
import json
from blaze.core.logging_audit import log

KNOWLEDGE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "knowledge.json")

DEFAULT_KNOWLEDGE = {
    "personal": {
        "name": "",
        "city": "",
        "profession": "",
        "interests": [],
        "preferences": {}
    },
    "facts": [],
    "custom_commands": {}
}


class KnowledgeBase:
    def __init__(self):
        self._data = {}
        self._load()

    def _load(self):
        try:
            os.makedirs(os.path.dirname(KNOWLEDGE_FILE), exist_ok=True)
            if os.path.exists(KNOWLEDGE_FILE):
                with open(KNOWLEDGE_FILE, "r") as f:
                    self._data = json.load(f)
            else:
                self._data = dict(DEFAULT_KNOWLEDGE)
                self._save()
        except Exception as e:
            log.warning(f"KnowledgeBase load: {e}")
            self._data = dict(DEFAULT_KNOWLEDGE)

    def _save(self):
        try:
            with open(KNOWLEDGE_FILE, "w") as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            log.warning(f"KnowledgeBase save: {e}")

    def add_fact(self, fact: str):
        facts = self._data.setdefault("facts", [])
        if fact not in facts:
            facts.append(fact)
            self._save()
            return f"Got it, I'll remember: '{fact}'"
        return "I already know that, sir."

    def set_personal(self, key: str, value):
        self._data.setdefault("personal", {})[key] = value
        self._save()
        return f"Updated {key}: {value}"

    def add_custom_command(self, trigger: str, action: str):
        """e.g. trigger='morning routine', action='open chrome|open spotify'"""
        self._data.setdefault("custom_commands", {})[trigger.lower()] = action
        self._save()
        return f"Custom command saved: '{trigger}' → {action}"

    def get_custom_command(self, text: str):
        for trigger, action in self._data.get("custom_commands", {}).items():
            if trigger in text.lower():
                return action
        return None

    def summary_for_prompt(self) -> str:
        """Returns a string to inject into the system prompt."""
        lines = []
        p = self._data.get("personal", {})
        if p.get("name"):
            lines.append(f"User's name: {p['name']}")
        if p.get("city"):
            lines.append(f"User's city: {p['city']}")
        if p.get("profession"):
            lines.append(f"User's profession: {p['profession']}")
        if p.get("interests"):
            lines.append(f"User's interests: {', '.join(p['interests'])}")
        for k, v in p.get("preferences", {}).items():
            lines.append(f"User preference — {k}: {v}")
        for fact in self._data.get("facts", []):
            lines.append(f"Known fact: {fact}")
        return "\n".join(lines) if lines else ""

    def list_all(self) -> str:
        p = self._data.get("personal", {})
        facts = self._data.get("facts", [])
        cmds = self._data.get("custom_commands", {})
        out = []
        if any(p.values()):
            out.append("Personal info: " + ", ".join(f"{k}={v}" for k,v in p.items() if v))
        if facts:
            out.append("Facts: " + "; ".join(facts))
        if cmds:
            out.append("Custom commands: " + "; ".join(f"{k}→{v}" for k,v in cmds.items()))
        return "\n".join(out) if out else "Knowledge base is empty. Tell me things about yourself!"


knowledge = KnowledgeBase()
