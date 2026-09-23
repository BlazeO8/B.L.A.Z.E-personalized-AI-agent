"""
handlers/briefing_handler.py — the morning brief, built from real data
(weather/news/calendar/reminders/system), never a template guess.
"""

from __future__ import annotations
import datetime

from blaze.handlers.base import CommandHandler
from blaze.services.system_monitor import monitor, weather, news_module
from blaze.services.calendar import calendar_manager
from blaze.core.database import db
from blaze.deps import psutil_available

BRIEFING_TRIGGERS = ["morning brief", "morning briefing", "daily briefing",
                     "full briefing", "give me a briefing"]


class MorningBriefingHandler(CommandHandler):
    def handle(self, ai, user_text: str, t: str, now: datetime.datetime) -> str | None:
        if not any(x in t for x in BRIEFING_TRIGGERS):
            return None

        date_str = now.strftime("%A, %B %d, %Y")
        time_str = now.strftime("%I:%M %p")

        try:
            w = weather.summary_str()
        except Exception:
            w = f"Weather unavailable, {ai._addr()}."

        try:
            headlines = news_module.get_headlines(3)
            news_str = "; ".join(headlines[:3]) if headlines else "No news available right now."
        except Exception:
            news_str = f"News unavailable, {ai._addr()}."

        try:
            events = calendar_manager.upcoming_summary()
        except Exception:
            events = f"Calendar unavailable, {ai._addr()}."

        try:
            rows = db.get_all_reminders()
            rem_str = ("; ".join(f"{m} at {f[11:16]}" for _, m, f in rows)
                       if rows else f"No reminders for today, {ai._addr()}.")
        except Exception:
            rem_str = f"Reminders unavailable, {ai._addr()}."

        try:
            sys_str = monitor.summary() if psutil_available else ""
        except Exception:
            sys_str = ""

        parts = [
            f"Good {'morning' if now.hour < 12 else ('afternoon' if now.hour < 17 else 'evening')}, {ai._addr()}.",
            f"Today is {date_str}, {time_str}.",
            f"Weather: {w}",
            f"Top news: {news_str}",
            f"Your schedule: {events}",
            f"Reminders: {rem_str}",
        ]
        if sys_str:
            parts.append(f"System status: {sys_str}")
        return " ".join(parts)
