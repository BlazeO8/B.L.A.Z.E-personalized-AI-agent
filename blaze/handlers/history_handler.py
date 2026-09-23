"""handlers/history_handler.py — "clear history" / "clear chat"."""

from __future__ import annotations
import datetime

from blaze.handlers.base import CommandHandler
from blaze.core.database import db

CLEAR_TRIGGERS = ["clear history", "clear chat"]


class ClearHistoryHandler(CommandHandler):
    def handle(self, ai, user_text: str, t: str, now: datetime.datetime) -> str | None:
        if not any(x in t for x in CLEAR_TRIGGERS):
            return None
        db.clear_history()
        ai.history.clear()
        return f"Conversation history cleared, {ai._addr()}."
