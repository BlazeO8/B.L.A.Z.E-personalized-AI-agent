"""
handlers/base.py — the shared interface every capability handler implements.

This is what replaced BlazeAI._handle_offline()'s 300-line if/elif chain.
Each handler is a self-contained file with ONE job. The registry
(registry.py) holds them in priority order, and _handle_offline() just
walks the list and asks each one "did you handle this?" — first non-None
result wins, same fall-through semantics the monolith had, just split
into files you can edit independently.

Why handle() returns None to mean "not me" instead of a separate
can_handle() check: several of the original blocks needed to partially
match a prefix, extract an argument, THEN decide the request doesn't
really belong to them (see AppHandler routing "open spotify" as
system-stats if it's actually a stats query in disguise) — splitting
matching from extraction would have meant duplicating that logic in two
places. One method, return None to pass, is simpler and matches how the
original code actually behaved.
"""

from __future__ import annotations
import datetime
from abc import ABC, abstractmethod


class CommandHandler(ABC):
    @abstractmethod
    def handle(self, ai, user_text: str, t: str, now: datetime.datetime) -> str | None:
        """Return a reply string if this handler applies, None to let the
        next handler in the registry try."""
        raise NotImplementedError
