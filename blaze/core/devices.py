"""
core/devices.py — lets you name your devices ("call my phone motorola")
and have commands route to the right one(s), including both at once
("open youtube on both").

This is deliberately simple: there are exactly two device *types* right
now — "desktop" (the machine BLAZE is running on) and "phone" (whatever's
connected via android_control.py). Aliases are just friendly names that
map onto those two types. If you ever pair a second phone, this would
need to grow into per-serial aliases — not built yet since you only have
one phone, no point adding complexity for a case that doesn't exist.

Aliases are stored in the same db.get_pref/set_pref key-value store
everything else in this codebase already uses.
"""

from __future__ import annotations
import json

from blaze.core.database import db

DEFAULT_ALIASES = {
    "laptop": "desktop", "desktop": "desktop", "pc": "desktop",
    "computer": "desktop", "this device": "desktop",
    "phone": "phone", "mobile": "phone", "android": "phone",
}

BOTH_KEYWORDS = ["both", "everywhere", "all devices", "all my devices"]

_PREF_KEY = "device_aliases_json"


def get_alias_map() -> dict[str, str]:
    raw = db.get_pref(_PREF_KEY, "")
    custom = {}
    if raw:
        try:
            custom = json.loads(raw)
        except Exception:
            custom = {}
    merged = dict(DEFAULT_ALIASES)
    merged.update(custom)
    return merged


def set_alias(name: str, device_type: str) -> None:
    if device_type not in ("desktop", "phone"):
        raise ValueError(f"unknown device_type {device_type!r}, expected 'desktop' or 'phone'")
    raw = db.get_pref(_PREF_KEY, "")
    try:
        custom = json.loads(raw) if raw else {}
    except Exception:
        custom = {}
    custom[name.lower().strip()] = device_type
    db.set_pref(_PREF_KEY, json.dumps(custom))


def resolve_devices(text: str) -> set[str]:
    """Returns which device type(s) a phrase refers to — a subset of
    {'desktop', 'phone'}. Empty set means no device was mentioned at all
    (caller should treat that as "unspecified", not "none")."""
    t = text.lower()
    if any(kw in t for kw in BOTH_KEYWORDS):
        return {"desktop", "phone"}

    aliases = get_alias_map()
    # Sort longest-alias-first so a custom alias like "my old laptop"
    # matches before the generic "laptop" would.
    found = set()
    for alias in sorted(aliases, key=len, reverse=True):
        if alias in t:
            found.add(aliases[alias])
    return found


def alias_names_for(device_type: str) -> list[str]:
    """All names currently pointing at a device type, for display purposes
    (e.g. telling the user what BLAZE currently calls their phone)."""
    return sorted(name for name, dt in get_alias_map().items() if dt == device_type)


# ── Per-device friendly names ────────────────────────────────────────────
# Separate from the alias map above: aliases route a *spoken phrase* to a
# device *type* ("phone" vs "desktop"). This section instead labels each
# physically-paired Android device (identified by its adb serial/IP:port,
# which isn't something a person would ever want to say out loud) with a
# friendly display name, e.g. "Kartik's Pixel" — used in the phone mirror
# panel and anywhere else a specific paired device needs to be shown or
# picked. Same db.get_pref/set_pref storage pattern as everything else
# here, just a different key so the two concerns don't collide.

_DEVICE_NAMES_KEY = "device_names_json"


def get_device_names() -> dict[str, str]:
    """serial -> friendly name, for every device that's ever been renamed.
    A device with no entry here just displays as its raw serial/IP."""
    raw = db.get_pref(_DEVICE_NAMES_KEY, "")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def get_device_name(serial: str) -> str:
    """Friendly name for a device serial, falling back to the serial
    itself if it hasn't been given a name yet."""
    return get_device_names().get(serial, serial)


def set_device_name(serial: str, name: str) -> None:
    name = name.strip()
    names = get_device_names()
    if name:
        names[serial] = name
    else:
        # empty name = reset to showing the raw serial
        names.pop(serial, None)
    db.set_pref(_DEVICE_NAMES_KEY, json.dumps(names))
