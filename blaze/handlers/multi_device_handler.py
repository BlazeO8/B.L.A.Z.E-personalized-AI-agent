"""
handlers/multi_device_handler.py — "open youtube on both", and setting
device names ("call my phone motorola", "name my laptop WorkPC").

Two handlers in this file:
- DeviceAliasHandler: teaches BLAZE what to call a device.
- MultiDeviceHandler: only fires when a command resolves to 2+ devices
  at once (e.g. "both", or naming both a phone alias and a desktop alias
  in the same sentence). Single-device phrasing ("open youtube on
  motorola") is intentionally left to app_handler.py / phone_handler.py,
  which now also understand aliases — this file only owns the "do it on
  more than one device" case, so there's exactly one place that knows how
  to fan a command out to multiple targets.
"""

from __future__ import annotations
import datetime
import re

from blaze.handlers.base import CommandHandler
from blaze.core import devices as dev

OPEN_ON_RE = re.compile(r"(?:open|launch|start)\s+(?:the\s+|my\s+)?(.+?)\s+on\s+(.+)")
SET_ALIAS_RE = re.compile(
    r"(?:call|name)\s+my\s+(phone|laptop|desktop|pc|computer)\s+(?:as\s+)?([a-zA-Z0-9' ]+)"
)


class DeviceAliasHandler(CommandHandler):
    def handle(self, ai, user_text: str, t: str, now: datetime.datetime) -> str | None:
        m = SET_ALIAS_RE.search(t)
        if not m:
            return None
        which_raw, new_name = m.group(1), m.group(2).strip()
        device_type = "phone" if which_raw == "phone" else "desktop"
        new_name = new_name.strip().rstrip(".")
        if not new_name:
            return None
        dev.set_alias(new_name, device_type)
        return f"Got it, {ai._addr()}. I'll call your {device_type} '{new_name}' from now on."


class MultiDeviceHandler(CommandHandler):
    def handle(self, ai, user_text: str, t: str, now: datetime.datetime) -> str | None:
        m = OPEN_ON_RE.search(t)
        if not m:
            return None
        app_name = m.group(1).strip()
        target_text = m.group(2).strip()
        target_devices = dev.resolve_devices(target_text)

        if len(target_devices) < 2:
            # Single device or nothing recognized — let app_handler.py /
            # phone_handler.py handle it, they understand aliases too now.
            return None

        results = []
        if "desktop" in target_devices:
            from blaze.services.system_monitor import launcher
            try:
                res = launcher.open(app_name)
            except Exception as e:
                res = str(e)
            results.append(f"Laptop: {res}")

        if "phone" in target_devices:
            from blaze.services import android_control as ac
            if not ac.adb_available():
                results.append("Phone: adb not set up.")
            elif not ac.is_connected():
                results.append("Phone: not connected.")
            else:
                ok, res = ac.open_app(app_name)
                results.append(f"Phone: {res}")

        return f"Opening {app_name} on both, {ai._addr()}. " + " ".join(results)
