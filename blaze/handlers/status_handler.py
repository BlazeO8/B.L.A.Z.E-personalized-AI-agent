"""
handlers/status_handler.py — "how are you", system stats, and battery.
This is your "System Stats Bot" from the earlier request, minus the
theater of a separate repo/process — same capability, one file.
"""

from __future__ import annotations
import datetime

from blaze.handlers.base import CommandHandler
from blaze.services.system_monitor import monitor
from blaze.deps import psutil_available

HOW_ARE_YOU_TRIGGERS = ["how are you", "how are you doing", "you ok", "you okay"]
SYSTEM_STATS_TRIGGERS = ["system status", "system stats", "system info", "cpu", "ram usage"]


class HowAreYouHandler(CommandHandler):
    def handle(self, ai, user_text: str, t: str, now: datetime.datetime) -> str | None:
        if t not in HOW_ARE_YOU_TRIGGERS:
            return None
        cpu = monitor.cpu() if psutil_available else 0
        ram = monitor.ram() if psutil_available else 0
        return f"All systems nominal, {ai._addr()}. CPU at {cpu:.0f}%, RAM at {ram:.0f}%. Ready to assist."


class SystemStatsHandler(CommandHandler):
    def handle(self, ai, user_text: str, t: str, now: datetime.datetime) -> str | None:
        if not any(x in t for x in SYSTEM_STATS_TRIGGERS):
            return None
        return monitor.summary() if psutil_available else f"psutil not installed, {ai._addr()}."


class BatteryHandler(CommandHandler):
    def handle(self, ai, user_text: str, t: str, now: datetime.datetime) -> str | None:
        if "battery" not in t:
            return None
        bat = monitor.battery() if psutil_available else None
        if bat:
            plug = "plugged in" if bat["plugged"] else "on battery"
            return f"Battery is at {bat['percent']}%, {plug}, {ai._addr()}."
        return f"Battery info unavailable, {ai._addr()}."
