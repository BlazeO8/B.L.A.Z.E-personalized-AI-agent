"""
B.L.A.Z.E — Google Calendar Integration
Creates calendar events with auto-generated Google Meet links,
and fires reminders/notifications before meetings start.
"""

import os
import json
import datetime
import threading
import time as _time
from blaze.core.logging_audit import log

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/contacts.readonly",
]
TOKEN_PATH  = os.path.join(os.path.expanduser("~"), ".blaze_google_token.json")
CREDS_CACHE = os.path.join(os.path.expanduser("~"), ".blaze_google_creds.json")


class GoogleCalendarManager:
    def __init__(self):
        self._service       = None
        self._notify_cb     = None     # fn(meeting_title, minutes_until)
        self._notified_ids  = set()    # avoid duplicate notifications
        self._scheduler_thread = None
        self._scheduler_active = False

    # ── Auth ──────────────────────────────────────────────────────────────────
    def _get_service(self):
        """Returns authenticated Google Calendar service, or None if not set up."""
        if self._service:
            return self._service
        from blaze.services.google_auth_helper import get_service
        self._service = get_service("calendar", "v3")
        return self._service

    def is_configured(self) -> bool:
        from blaze.services.google_auth_helper import is_configured
        return is_configured()

    # ── Create meeting ────────────────────────────────────────────────────────
    def create_meeting(self, title: str, start_time: datetime.datetime,
                        duration_minutes: int = 30, description: str = "",
                        attendees: list = None) -> dict:
        """
        Creates a calendar event with an auto-generated Google Meet link.
        Returns dict with 'success', 'meet_link', 'event_link', 'message'.
        """
        service = self._get_service()
        if not service:
            return {
                "success": False,
                "message": ("Google Calendar isn't set up yet, sir. "
                            "Run google_auth.py once to connect your account.")
            }

        try:
            end_time = start_time + datetime.timedelta(minutes=duration_minutes)

            event_body = {
                "summary": title,
                "description": description,
                "start": {
                    "dateTime": start_time.isoformat(),
                    "timeZone": "Asia/Kolkata",
                },
                "end": {
                    "dateTime": end_time.isoformat(),
                    "timeZone": "Asia/Kolkata",
                },
                "conferenceData": {
                    "createRequest": {
                        "requestId": f"blaze-{int(_time.time())}",
                        "conferenceSolutionKey": {"type": "hangoutsMeet"}
                    }
                },
                "reminders": {
                    "useDefault": False,
                    "overrides": [
                        {"method": "popup", "minutes": 10},
                        {"method": "popup", "minutes": 1},
                    ],
                },
            }

            if attendees:
                event_body["attendees"] = [{"email": e} for e in attendees]

            event = service.events().insert(
                calendarId="primary",
                body=event_body,
                conferenceDataVersion=1,
                sendUpdates="all" if attendees else "none"
            ).execute()

            meet_link  = event.get("hangoutLink", "")
            event_link = event.get("htmlLink", "")

            log.info(f"Calendar event created: {title} at {start_time}")

            return {
                "success": True,
                "event_id": event["id"],
                "meet_link": meet_link,
                "event_link": event_link,
                "message": (f"Meeting '{title}' scheduled for "
                           f"{start_time.strftime('%A, %B %d at %I:%M %p')}, sir. "
                           f"Google Meet link: {meet_link or 'generating...'}")
            }

        except Exception as e:
            log.warning(f"Calendar create error: {e}")
            return {"success": False, "message": f"Could not create meeting, sir. {e}"}

    # ── List upcoming meetings ────────────────────────────────────────────────
    def list_upcoming(self, max_results: int = 10) -> list:
        service = self._get_service()
        if not service:
            return []
        try:
            now = datetime.datetime.utcnow().isoformat() + "Z"
            result = service.events().list(
                calendarId="primary", timeMin=now,
                maxResults=max_results, singleEvents=True,
                orderBy="startTime"
            ).execute()
            return result.get("items", [])
        except Exception as e:
            log.warning(f"Calendar list error: {e}")
            return []

    def upcoming_summary(self) -> str:
        events = self.list_upcoming(5)
        if not events:
            return "No upcoming meetings found, sir."
        lines = []
        for e in events:
            title = e.get("summary", "Untitled")
            start = e.get("start", {}).get("dateTime", e.get("start", {}).get("date", ""))
            try:
                dt = datetime.datetime.fromisoformat(start.replace("Z", "+00:00"))
                start_str = dt.strftime("%a %I:%M %p")
            except Exception:
                start_str = start
            lines.append(f"• {title} — {start_str}")
        return "Your upcoming meetings:\n" + "\n".join(lines)

    # ── Notification scheduler ────────────────────────────────────────────────
    def start_notifier(self, callback):
        """
        callback(title, minutes_until, meet_link) called when a meeting
        is approaching (10 min and 1 min before).
        """
        self._notify_cb = callback
        if self._scheduler_active:
            return
        self._scheduler_active = True
        self._scheduler_thread = threading.Thread(
            target=self._notify_loop, daemon=True
        )
        self._scheduler_thread.start()
        log.info("Calendar notifier started.")

    def _notify_loop(self):
        consecutive_failures = 0
        while self._scheduler_active:
            try:
                if not self.is_configured():
                    _time.sleep(60)
                    continue
                events = self.list_upcoming(10)
                consecutive_failures = 0  # reset on success
                now = datetime.datetime.now(datetime.timezone.utc)
                for e in events:
                    start = e.get("start", {}).get("dateTime")
                    if not start:
                        continue
                    try:
                        start_dt = datetime.datetime.fromisoformat(start.replace("Z", "+00:00"))
                    except Exception:
                        continue
                    minutes_until = (start_dt - now).total_seconds() / 60
                    event_id = e.get("id", "")

                    for threshold, key_suffix in [(10, "_10"), (1, "_1")]:
                        notif_key = event_id + key_suffix
                        if (threshold - 0.5) <= minutes_until <= (threshold + 0.5) \
                           and notif_key not in self._notified_ids:
                            self._notified_ids.add(notif_key)
                            title     = e.get("summary", "Meeting")
                            meet_link = e.get("hangoutLink", "")
                            if self._notify_cb:
                                self._notify_cb(title, threshold, meet_link)
            except Exception as ex:
                consecutive_failures += 1
                log.warning(f"Calendar notify loop error ({consecutive_failures}): {ex}")
                if consecutive_failures >= 3:
                    # Likely a scope/auth mismatch — back off to avoid log spam
                    log.warning("Calendar notifier backing off for 5 minutes after repeated failures.")
                    _time.sleep(300)
                    continue
            _time.sleep(30)   # check every 30s


calendar_manager = GoogleCalendarManager()
