"""
B.L.A.Z.E — Google People (Contacts) API Integration
Resolve contact names to emails/phone numbers for "email X" / "call X" commands.
Uses the same OAuth token as Calendar/Gmail/Drive/Tasks/Sheets.
"""

from blaze.core.logging_audit import log
from blaze.services.google_auth_helper import get_service, NOT_CONFIGURED_MSG


class ContactsManager:
    def __init__(self):
        self._service = None
        self._cache    = {}   # name -> {email, phone}

    def _svc(self):
        if not self._service:
            self._service = get_service("people", "v1")
        return self._service

    def _load_contacts(self):
        svc = self._svc()
        if not svc:
            return {}
        try:
            result = svc.people().connections().list(
                resourceName="people/me",
                pageSize=200,
                personFields="names,emailAddresses,phoneNumbers"
            ).execute()
            connections = result.get("connections", [])
            cache = {}
            for p in connections:
                names = p.get("names", [])
                if not names:
                    continue
                name  = names[0].get("displayName", "").lower()
                email = p.get("emailAddresses", [{}])[0].get("value", "")
                phone = p.get("phoneNumbers", [{}])[0].get("value", "")
                cache[name] = {"email": email, "phone": phone}
            self._cache = cache
            return cache
        except Exception as e:
            log.warning(f"Contacts load error: {e}")
            return {}

    def find_contact(self, name_query: str) -> str:
        if not self._cache:
            self._load_contacts()
        if not self._cache:
            return NOT_CONFIGURED_MSG

        q = name_query.lower().strip()
        for name, info in self._cache.items():
            if q in name:
                parts = [f"Found {name.title()}, sir."]
                if info.get("email"):
                    parts.append(f"Email: {info['email']}")
                if info.get("phone"):
                    parts.append(f"Phone: {info['phone']}")
                return " ".join(parts)
        return f"Could not find a contact matching '{name_query}', sir."

    def get_email(self, name_query: str) -> str | None:
        """Returns just the email for a contact, used internally by send_email."""
        if not self._cache:
            self._load_contacts()
        q = name_query.lower().strip()
        for name, info in self._cache.items():
            if q in name and info.get("email"):
                return info["email"]
        return None


contacts_manager = ContactsManager()
