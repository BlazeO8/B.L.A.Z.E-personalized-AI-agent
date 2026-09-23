"""
B.L.A.Z.E — Google Drive Integration
Search, list, and open files in your Google Drive.
"""

import webbrowser
from blaze.core.logging_audit import log
from blaze.services.google_auth_helper import get_service, NOT_CONFIGURED_MSG


class DriveManager:
    def __init__(self):
        self._service = None

    def _svc(self):
        if not self._service:
            self._service = get_service("drive", "v3")
        return self._service

    def search_files(self, query: str, max_results: int = 8) -> str:
        svc = self._svc()
        if not svc:
            return NOT_CONFIGURED_MSG
        try:
            result = svc.files().list(
                q=f"name contains '{query}' and trashed=false",
                pageSize=max_results,
                fields="files(id, name, mimeType, webViewLink)"
            ).execute()
            files = result.get("files", [])
            if not files:
                return f"No files found matching '{query}' in your Drive, sir."
            lines = [f"• {f['name']}" for f in files]
            # Open the top result automatically
            if files:
                webbrowser.open(files[0]["webViewLink"])
            return f"Found {len(files)} file(s), sir. Opening the top result.\n" + "\n".join(lines)
        except Exception as e:
            log.warning(f"Drive search error: {e}")
            return f"Could not search Drive, sir. {e}"

    def list_recent(self, max_results: int = 8) -> str:
        svc = self._svc()
        if not svc:
            return NOT_CONFIGURED_MSG
        try:
            result = svc.files().list(
                pageSize=max_results,
                orderBy="modifiedTime desc",
                fields="files(id, name, modifiedTime)"
            ).execute()
            files = result.get("files", [])
            if not files:
                return "No files found in your Drive, sir."
            lines = [f"• {f['name']}" for f in files]
            return f"Your recent Drive files, sir:\n" + "\n".join(lines)
        except Exception as e:
            log.warning(f"Drive list error: {e}")
            return f"Could not fetch Drive files, sir. {e}"

    def open_drive(self) -> str:
        webbrowser.open("https://drive.google.com")
        return "Opening Google Drive, sir."


drive_manager = DriveManager()
