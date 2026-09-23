"""
handlers/automation_handler.py — custom automation rules: checking if the
current input matches a saved trigger, plus listing/deleting rules.
"""

from __future__ import annotations
import datetime

from blaze.handlers.base import CommandHandler
from blaze.intelligence.automations import automation
from blaze.services.system_monitor import launcher


class AutomationTriggerHandler(CommandHandler):
    """Checks whether the input matches a user-defined automation rule
    (e.g. "good morning" -> open chrome + open spotify). Kept separate
    from AutomationCommandsHandler (list/delete) since this one fires on
    almost every message (cheap check) while the other only matches
    explicit management phrases."""

    def handle(self, ai, user_text: str, t: str, now: datetime.datetime) -> str | None:
        actions = automation.check_trigger(t)
        if not actions:
            return None
        results = []
        for action in actions:
            if action.startswith("open "):
                res = launcher.open(action.replace("open ", "").strip())
            elif action.startswith("close "):
                res = launcher.close(action.replace("close ", "").strip())
            else:
                res = action
            results.append(res)
        return f"Automation triggered, {ai._addr()}. " + " ".join(results)


class AutomationCommandsHandler(CommandHandler):
    """Management commands: list rules, delete a rule."""

    LIST_TRIGGERS = ["list automations", "my automations", "show automations"]

    def handle(self, ai, user_text: str, t: str, now: datetime.datetime) -> str | None:
        if any(x in t for x in self.LIST_TRIGGERS):
            return automation.list_rules()

        if "delete automation" in t or "remove automation" in t:
            name = t.replace("delete automation ", "").replace("remove automation ", "").strip()
            return automation.delete_rule(name)

        return None
