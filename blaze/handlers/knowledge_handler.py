"""
handlers/knowledge_handler.py — "remember that X", setting your name/city,
and reviewing what BLAZE knows about you.
"""

from __future__ import annotations
import datetime

from blaze.handlers.base import CommandHandler
from blaze.intelligence.knowledge import knowledge

REMEMBER_PREFIXES = ["remember that ", "remember: ", "note that ", "add to knowledge"]
NAME_PREFIXES = ["my name is ", "i am ", "i'm "]
CITY_PREFIXES = ["my city is ", "i live in ", "i am from "]
SHOW_TRIGGERS = ["show my knowledge", "what do you know about me", "my knowledge base"]


class KnowledgeHandler(CommandHandler):
    def handle(self, ai, user_text: str, t: str, now: datetime.datetime) -> str | None:
        if any(x in t for x in REMEMBER_PREFIXES):
            fact = t
            for p in REMEMBER_PREFIXES:
                fact = fact.replace(p, "")
            fact = fact.strip()
            return knowledge.add_fact(fact)

        if any(x in t for x in NAME_PREFIXES):
            for prefix in NAME_PREFIXES:
                if t.startswith(prefix):
                    name = t[len(prefix):].strip().title()
                    knowledge.set_personal("name", name)
                    return f"Got it {ai._addr()}, I'll remember your name is {name}."

        if "my city is " in t or "i live in " in t or "i am from " in t:
            for prefix in CITY_PREFIXES:
                if prefix in t:
                    city = t.split(prefix)[1].strip().title()
                    knowledge.set_personal("city", city)
                    return f"Got it, I'll remember you're from {city}, {ai._addr()}."

        if any(x in t for x in SHOW_TRIGGERS):
            return knowledge.list_all()

        return None
