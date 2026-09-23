"""
B.L.A.Z.E — Shared Google Authentication
One token, one auth flow, used by Calendar, Gmail, Drive, Tasks, Sheets.
"""

import os
from blaze.core.logging_audit import log

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/contacts.readonly",
]
TOKEN_PATH = os.path.join(os.path.expanduser("~"), ".blaze_google_token.json")

_creds_cache = None


def get_credentials():
    """Returns valid Google credentials, or None if not authenticated."""
    global _creds_cache
    if _creds_cache and _creds_cache.valid:
        return _creds_cache

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        if not os.path.exists(TOKEN_PATH):
            return None

        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(TOKEN_PATH, "w") as f:
                    f.write(creds.to_json())
            except Exception as e:
                if "invalid_scope" in str(e) or "invalid_grant" in str(e):
                    log.warning(
                        "Google token has outdated/mismatched scopes. "
                        "Delete ~/.blaze_google_token.json and run google_auth.py again."
                    )
                else:
                    log.warning(f"Google token refresh failed: {e}")
                return None

        _creds_cache = creds
        return creds

    except Exception as e:
        log.warning(f"Google auth error: {e}")
        return None


def get_service(api_name: str, version: str):
    """Returns an authenticated Google API service, or None."""
    creds = get_credentials()
    if not creds:
        return None
    try:
        from googleapiclient.discovery import build
        return build(api_name, version, credentials=creds)
    except Exception as e:
        log.warning(f"Google {api_name} service error: {e}")
        return None


def is_configured() -> bool:
    from blaze.config import GOOGLE_CLIENT_ID
    return bool(GOOGLE_CLIENT_ID) and os.path.exists(TOKEN_PATH)


NOT_CONFIGURED_MSG = (
    "Google services aren't connected yet, sir. "
    "Run google_auth.py once to link your account."
)
