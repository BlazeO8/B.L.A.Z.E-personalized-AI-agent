"""
B.L.A.Z.E — Google Sheets Integration
Log expenses, append rows, read data from spreadsheets by voice.
Uses a single "BLAZE Log" spreadsheet auto-created on first use.
"""

from blaze.core.logging_audit import log
from blaze.core.database import db
from blaze.services.google_auth_helper import get_service, NOT_CONFIGURED_MSG


class SheetsManager:
    def __init__(self):
        self._service     = None
        self._sheet_id    = None

    def _svc(self):
        if not self._service:
            self._service = get_service("sheets", "v4")
        return self._service

    def _get_or_create_log_sheet(self):
        """Get the BLAZE Log spreadsheet ID, creating it if needed."""
        if self._sheet_id:
            return self._sheet_id

        saved_id = db.get_pref("blaze_sheet_id", "")
        if saved_id:
            self._sheet_id = saved_id
            return saved_id

        svc = self._svc()
        if not svc:
            return None
        try:
            spreadsheet = svc.spreadsheets().create(body={
                "properties": {"title": "BLAZE Log"},
                "sheets": [{"properties": {"title": "Entries"}}]
            }).execute()
            sheet_id = spreadsheet["spreadsheetId"]

            # Add header row
            svc.spreadsheets().values().append(
                spreadsheetId=sheet_id, range="Entries!A1",
                valueInputOption="RAW",
                body={"values": [["Date", "Category", "Description", "Amount"]]}
            ).execute()

            db.set_pref("blaze_sheet_id", sheet_id)
            self._sheet_id = sheet_id
            log.info(f"Created BLAZE Log spreadsheet: {sheet_id}")
            return sheet_id
        except Exception as e:
            log.warning(f"Sheet creation error: {e}")
            return None

    def log_entry(self, category: str, description: str, amount: str = "") -> str:
        """Quick-log an entry (e.g. expense) to the BLAZE Log sheet."""
        svc = self._svc()
        if not svc:
            return NOT_CONFIGURED_MSG
        sheet_id = self._get_or_create_log_sheet()
        if not sheet_id:
            return "Could not access your log sheet, sir."
        try:
            import datetime
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            svc.spreadsheets().values().append(
                spreadsheetId=sheet_id, range="Entries!A1",
                valueInputOption="RAW",
                body={"values": [[today, category, description, amount]]}
            ).execute()
            amt_str = f" — ₹{amount}" if amount else ""
            return f"Logged to your sheet, sir: {category} - {description}{amt_str}."
        except Exception as e:
            log.warning(f"Sheet log error: {e}")
            return f"Could not log entry, sir. {e}"

    def read_range(self, spreadsheet_id: str, cell_range: str) -> str:
        """Read a specific range from any spreadsheet by ID."""
        svc = self._svc()
        if not svc:
            return NOT_CONFIGURED_MSG
        try:
            result = svc.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id, range=cell_range
            ).execute()
            values = result.get("values", [])
            if not values:
                return "No data found in that range, sir."
            lines = [", ".join(row) for row in values]
            return "Data found, sir:\n" + "\n".join(lines)
        except Exception as e:
            log.warning(f"Sheet read error: {e}")
            return f"Could not read sheet, sir. {e}"


sheets_manager = SheetsManager()
