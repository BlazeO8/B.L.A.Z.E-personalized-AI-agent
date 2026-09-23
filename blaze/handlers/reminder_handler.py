"""handlers/reminder_handler.py — "list my reminders". Setting NEW
reminders goes through the "reminder" nlp intent -> ReminderEngine
directly (see engine.py's chat() method); this handler is just for
reviewing what's already scheduled."""

from __future__ import annotations
import datetime

from blaze.handlers.base import CommandHandler
from blaze.core.database import db

LIST_TRIGGERS = ["list reminders", "my reminders", "show reminders", "pending reminders"]


class ReminderListHandler(CommandHandler):
    def handle(self, ai, user_text: str, t: str, now: datetime.datetime) -> str | None:
        if not any(x in t for x in LIST_TRIGGERS):
            return None
        rows = db.get_all_reminders()
        if not rows:
            return f"No pending reminders, {ai._addr()}."
        return "Your reminders: " + ", ".join(f"{m} at {f[11:16]}" for _, m, f in rows)
