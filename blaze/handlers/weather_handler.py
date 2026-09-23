"""handlers/weather_handler.py — your "Weather Bot" request, minus the
separate-repo theater. WeatherModule itself (services/system_monitor.py)
already does the real API work; this just routes text to it."""

from __future__ import annotations
import datetime

from blaze.handlers.base import CommandHandler
from blaze.services.system_monitor import weather

WEATHER_TRIGGERS = ["weather", "temperature", "how hot", "how cold", "rain"]


class WeatherHandler(CommandHandler):
    def handle(self, ai, user_text: str, t: str, now: datetime.datetime) -> str | None:
        if not any(x in t for x in WEATHER_TRIGGERS):
            return None
        return weather.summary_str()
