"""handlers/greeting_handler.py — the fallback greeting when no other
handler matched but it's clearly just a hello."""

from __future__ import annotations
import datetime

from blaze.handlers.base import CommandHandler

GREETING_TRIGGERS = ["hey blaze", "hello blaze", "hi blaze", "yo blaze", "hello", "hi"]


class GreetingHandler(CommandHandler):
    def handle(self, ai, user_text: str, t: str, now: datetime.datetime) -> str | None:
        if t not in GREETING_TRIGGERS:
            return None
        return f"Hello {ai._addr()}, I am online. How may I assist you?"
