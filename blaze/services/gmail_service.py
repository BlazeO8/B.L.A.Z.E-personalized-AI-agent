"""
B.L.A.Z.E — Gmail Integration
Read inbox, search emails, draft and send emails by voice.
"""

import base64
from email.mime.text import MIMEText
from blaze.core.logging_audit import log
from blaze.services.google_auth_helper import get_service, is_configured, NOT_CONFIGURED_MSG


class GmailManager:
    def __init__(self):
        self._service = None

    def _svc(self):
        if not self._service:
            self._service = get_service("gmail", "v1")
        return self._service

    def get_unread_summary(self, max_results: int = 5) -> str:
        svc = self._svc()
        if not svc:
            return NOT_CONFIGURED_MSG
        try:
            result = svc.users().messages().list(
                userId="me", labelIds=["INBOX", "UNREAD"], maxResults=max_results
            ).execute()
            messages = result.get("messages", [])
            if not messages:
                return "No unread emails, sir. Inbox is clear."

            lines = []
            for m in messages:
                msg = svc.users().messages().get(
                    userId="me", id=m["id"], format="metadata",
                    metadataHeaders=["From", "Subject"]
                ).execute()
                headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
                sender  = headers.get("From", "Unknown").split("<")[0].strip()
                subject = headers.get("Subject", "(no subject)")
                lines.append(f"• {sender}: {subject}")

            return f"You have {len(messages)} unread email{'s' if len(messages)!=1 else ''}, sir:\n" + "\n".join(lines)
        except Exception as e:
            log.warning(f"Gmail unread error: {e}")
            return f"Could not check inbox, sir. {e}"

    def search_emails(self, query: str, max_results: int = 5) -> str:
        svc = self._svc()
        if not svc:
            return NOT_CONFIGURED_MSG
        try:
            result = svc.users().messages().list(
                userId="me", q=query, maxResults=max_results
            ).execute()
            messages = result.get("messages", [])
            if not messages:
                return f"No emails found matching '{query}', sir."

            lines = []
            for m in messages:
                msg = svc.users().messages().get(
                    userId="me", id=m["id"], format="metadata",
                    metadataHeaders=["From", "Subject"]
                ).execute()
                headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
                sender  = headers.get("From", "Unknown").split("<")[0].strip()
                subject = headers.get("Subject", "(no subject)")
                lines.append(f"• {sender}: {subject}")

            return f"Found {len(messages)} email(s), sir:\n" + "\n".join(lines)
        except Exception as e:
            log.warning(f"Gmail search error: {e}")
            return f"Search failed, sir. {e}"

    def send_email(self, to: str, subject: str, body: str) -> str:
        svc = self._svc()
        if not svc:
            return NOT_CONFIGURED_MSG
        try:
            message = MIMEText(body)
            message["to"]      = to
            message["subject"] = subject
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

            svc.users().messages().send(
                userId="me", body={"raw": raw}
            ).execute()

            return f"Email sent to {to}, sir. Subject: '{subject}'."
        except Exception as e:
            log.warning(f"Gmail send error: {e}")
            return f"Could not send email, sir. {e}"


gmail_manager = GmailManager()
