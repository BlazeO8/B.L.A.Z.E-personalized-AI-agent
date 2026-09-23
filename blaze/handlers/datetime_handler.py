"""handlers/datetime_handler.py — "what time is it" / "what's the date"."""

from __future__ import annotations
import datetime

from blaze.handlers.base import CommandHandler

TIME_TRIGGERS = ["what time", "current time", "time is it", "what is the time"]
DATE_TRIGGERS = ["what date", "today's date", "what day", "what is today", "current date"]


class TimeHandler(CommandHandler):
    def handle(self, ai, user_text: str, t: str, now: datetime.datetime) -> str | None:
        if any(x in t for x in TIME_TRIGGERS) or t == "time":
            return f"It is {now.strftime('%I:%M %p')}, {ai._addr()}."
        return None


class DateHandler(CommandHandler):
    def handle(self, ai, user_text: str, t: str, now: datetime.datetime) -> str | None:
        if any(x in t for x in DATE_TRIGGERS) or t == "date":
            return f"Today is {now.strftime('%A, %B %d %Y')}, {ai._addr()}."
        return None
