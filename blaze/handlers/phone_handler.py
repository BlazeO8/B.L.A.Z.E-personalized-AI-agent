"""
handlers/phone_handler.py — "open camera on my phone" (or "on motorola"
if that's what you've named it), "take a screenshot of my phone",
"mirror my phone", "what's my phone's battery", "open that screenshot".

Matching uses keyword-AND logic rather than a fixed list of exact
phrases — far more forgiving of natural phrasing variance, matches how
every other handler in this codebase works.

Now alias-aware: core/devices.py lets you rename your phone (e.g. "call
my phone motorola"), and this handler checks against your current phone
aliases, not just the literal word "phone". "open X on both" (phone AND
desktop together) is NOT handled here — that's multi_device_handler.py,
which owns anything targeting more than one device so there's exactly
one place that knows how to fan a command out.

Bugs fixed here across three rounds of real testing:
1. Required exact phrases like "screenshot of my phone", missed "take a
   screenshot IN my phone" — fell through to the LLM, which wrongly
   opened a literal app called "phone".
2. "Open that screenshot" has no "phone" in it, so the old gate rejected
   it before this handler even looked — fell through to the LLM again,
   which opened a generic Pictures/images folder. Opening an
   already-taken screenshot doesn't need adb/connection at all — it's
   local file access — so that check runs before any adb checks.
3. Only recognized the literal word "phone", so a custom alias like
   "motorola" wouldn't route here at all.

Actual ADB work lives in services/android_control.py — this file only
does command routing. Every reply here is honest about failure.
"""

from __future__ import annotations
import datetime
import os
import re
import time as _time

from blaze.handlers.base import CommandHandler
from blaze.services import android_control as ac
from blaze.core import devices as dev

# Generic "open/launch/start <app> on <target>" — target gets checked
# against your current device aliases rather than assumed to be "phone".
OPEN_ON_RE = re.compile(r"(?:open|launch|start)\s+(?:the\s+|my\s+)?(.+?)\s+on\s+(.+)")

# Tracks the most recent LOCAL copy of a phone screenshot across calls,
# so "open that screenshot" knows what "that" refers to. Session-only —
# resets when BLAZE restarts, which is fine, "that" implies "recent".
_last_screenshot_path: str | None = None


def _mentions_phone(t: str) -> bool:
    """True if the text refers to the phone by any current alias, not
    just the literal word "phone"."""
    return "phone" in dev.resolve_devices(t)


class PhoneHandler(CommandHandler):
    def handle(self, ai, user_text: str, t: str, now: datetime.datetime) -> str | None:
        global _last_screenshot_path

        mentions_screenshot = "screenshot" in t or "screen shot" in t
        phone_referenced = _mentions_phone(t)

        if not phone_referenced and not mentions_screenshot:
            return None

        wants_open_last_screenshot = (
            mentions_screenshot and "open" in t
            and not any(verb in t for verb in ["take", "grab", "get", "new"])
        )

        # Opening an already-taken screenshot is just opening a local
        # file — no adb, no phone connection needed for this one.
        if wants_open_last_screenshot:
            if not _last_screenshot_path or not os.path.exists(_last_screenshot_path):
                return f"No screenshot taken yet this session, {ai._addr()}. Say 'take a screenshot of my phone' first."
            try:
                os.startfile(_last_screenshot_path)
                return f"Opening the screenshot, {ai._addr()}."
            except Exception as e:
                return f"Couldn't open it, {ai._addr()}: {e}"

        if not phone_referenced:
            # A bare "screenshot" mention with no phone reference at all
            # isn't this handler's job (could be a desktop screenshot
            # request, which this handler doesn't own).
            return None

        # If this is actually a "both devices" request, let
        # multi_device_handler.py own it instead — it runs earlier in the
        # registry, so in practice we'd never even see it, but this guard
        # keeps the two files' responsibilities honestly non-overlapping.
        target_devices = dev.resolve_devices(t)
        if len(target_devices) > 1:
            return None

        # Nothing else here should even attempt an adb call if it's not
        # installed — fail fast with one clear message.
        if not ac.adb_available():
            return (
                f"Phone control needs Android SDK Platform Tools (adb) installed "
                f"and on PATH, {ai._addr()}. Not set up yet — see the setup notes "
                f"in services/android_control.py."
            )

        wants_connect = "connect" in t
        wants_battery = "battery" in t
        wants_screenshot = mentions_screenshot  # capture a NEW one
        wants_mirror = "mirror" in t or "cast" in t
        wants_apps = "apps" in t or "applications" in t
        open_match = OPEN_ON_RE.search(t)
        open_app_name = None
        if open_match and dev.resolve_devices(open_match.group(2)) == {"phone"}:
            open_app_name = open_match.group(1).strip()

        # "open/show/display my phone screen" (open the embedded mirror
        # panel's attention) and "make it bigger/smaller" — handled
        # deterministically here rather than as an LLM system-command tag,
        # since this is a pure GUI action (resize a widget), not something
        # that needs the model's judgment, and doing it here means it still
        # works even if the LLM backend is down (see the Groq model
        # deprecation this codebase just hit).
        mentions_mirror_screen = "screen" in t and not mentions_screenshot
        wants_show_mirror = mentions_mirror_screen and any(
            v in t for v in ("open", "show", "display")
        )
        wants_bigger_mirror = mentions_mirror_screen and any(
            v in t for v in ("bigger", "enlarge", "larger", "expand", "increase", "zoom")
        )
        wants_smaller_mirror = mentions_mirror_screen and any(
            v in t for v in ("smaller", "shrink", "reduce", "decrease", "minimize")
        )

        if not any([wants_connect, wants_battery, wants_screenshot,
                    wants_mirror, wants_apps, open_app_name,
                    wants_show_mirror, wants_bigger_mirror, wants_smaller_mirror]):
            return None

        if wants_show_mirror or wants_bigger_mirror or wants_smaller_mirror:
            if ai.gui_phone_mirror_callback is None:
                return (
                    f"The phone mirror panel isn't available right now, {ai._addr()} — "
                    f"that's a desktop-GUI-only feature, not available when running headless "
                    f"or via the web server."
                )
            enlarge = wants_bigger_mirror or wants_show_mirror
            ai.gui_phone_mirror_callback(enlarge)
            return (
                f"Made the phone mirror bigger, {ai._addr()}." if enlarge
                else f"Shrunk the phone mirror back down, {ai._addr()}."
            )

        if wants_connect:
            if ac.is_connected():
                return f"Already connected to your phone, {ai._addr()}."
            return (
                f"No phone connected, {ai._addr()}. If you've already paired once, "
                f"tell me the IP to reconnect — otherwise this needs a one-time "
                f"pairing step on your phone first (see setup notes)."
            )

        if not ac.is_connected():
            return f"Your phone isn't connected right now, {ai._addr()}. Try 'connect my phone' first."

        if wants_battery:
            bat = ac.battery_status()
            if not bat or bat["level"] is None:
                return f"Couldn't read your phone's battery, {ai._addr()}."
            state = "plugged in" if bat["plugged"] else "on battery"
            return f"Your phone is at {bat['level']}%, {state}, {ai._addr()}."

        if wants_screenshot:
            filename = f"blaze_phone_screenshot_{_time.strftime('%Y%m%d_%H%M%S')}.png"
            path = os.path.join(os.path.expanduser("~"), "Pictures", filename)
            ok, result = ac.screenshot(path)
            if ok:
                if os.path.exists(path):
                    _last_screenshot_path = path
                return f"Screenshot saved, {ai._addr()}: {result}"
            return f"Couldn't grab a screenshot, {ai._addr()}: {result}"

        if wants_mirror:
            ok, result = ac.mirror_screen()
            return result

        if wants_apps:
            apps = ac.list_apps()
            if not apps:
                return f"Couldn't list apps on your phone, {ai._addr()}."
            return f"You have {len(apps)} apps installed, {ai._addr()}. A few: " + ", ".join(apps[:8])

        if open_app_name:
            ok, result = ac.open_app(open_app_name)
            return result

        return None
