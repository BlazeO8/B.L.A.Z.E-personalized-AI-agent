"""
handlers/registry.py — the ONE list defining dispatch order.

Order matters and must match the original monolith's order exactly (e.g.
morning briefing is checked before automations, which is checked before
app-open, etc.) — this is the only file that needs to change if you want
to reorder priority; every handler itself stays untouched.

To add a new capability: write a new handlers/x_handler.py implementing
CommandHandler, import it here, add one line to HANDLERS. That's the
whole point of this refactor — you never touch this file's neighbors.
"""

from blaze.handlers.briefing_handler import MorningBriefingHandler
from blaze.handlers.automation_handler import AutomationTriggerHandler, AutomationCommandsHandler
from blaze.handlers.knowledge_handler import KnowledgeHandler
from blaze.handlers.multi_device_handler import DeviceAliasHandler, MultiDeviceHandler
from blaze.handlers.phone_handler import PhoneHandler
from blaze.handlers.app_handler import OpenAppHandler, CloseAppHandler
from blaze.handlers.datetime_handler import TimeHandler, DateHandler
from blaze.handlers.status_handler import HowAreYouHandler, SystemStatsHandler, BatteryHandler
from blaze.handlers.weather_handler import WeatherHandler
from blaze.handlers.reminder_handler import ReminderListHandler
from blaze.handlers.history_handler import ClearHistoryHandler
from blaze.handlers.image_handler import ImageGenerationHandler
from blaze.handlers.media_handler import PlayMusicHandler
from blaze.handlers.greeting_handler import GreetingHandler

HANDLERS = [
    MorningBriefingHandler(),
    AutomationTriggerHandler(),
    KnowledgeHandler(),
    AutomationCommandsHandler(),
    DeviceAliasHandler(),
    MultiDeviceHandler(),
    PhoneHandler(),
    OpenAppHandler(),
    CloseAppHandler(),
    TimeHandler(),
    DateHandler(),
    HowAreYouHandler(),
    SystemStatsHandler(),
    BatteryHandler(),
    WeatherHandler(),
    ReminderListHandler(),
    ClearHistoryHandler(),
    ImageGenerationHandler(),
    PlayMusicHandler(),
    GreetingHandler(),
]
