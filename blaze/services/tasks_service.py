"""
B.L.A.Z.E — Google Tasks Integration
Voice-controlled to-do list synced with the Google Tasks app on your phone.
"""

from blaze.core.logging_audit import log
from blaze.services.google_auth_helper import get_service, NOT_CONFIGURED_MSG


class TasksManager:
    def __init__(self):
        self._service  = None
        self._list_id  = None

    def _svc(self):
        if not self._service:
            self._service = get_service("tasks", "v1")
        return self._service

    def _default_list(self):
        if self._list_id:
            return self._list_id
        svc = self._svc()
        if not svc:
            return None
        try:
            lists = svc.tasklists().list().execute().get("items", [])
            if lists:
                self._list_id = lists[0]["id"]
            return self._list_id
        except Exception as e:
            log.warning(f"Tasks list error: {e}")
            return None

    def add_task(self, title: str, notes: str = "", due: str = None) -> str:
        svc = self._svc()
        if not svc:
            return NOT_CONFIGURED_MSG
        list_id = self._default_list()
        if not list_id:
            return "Could not access your task list, sir."
        try:
            body = {"title": title, "notes": notes}
            if due:
                body["due"] = due  # RFC3339 timestamp
            svc.tasks().insert(tasklist=list_id, body=body).execute()
            return f"Added to your to-do list, sir: '{title}'."
        except Exception as e:
            log.warning(f"Add task error: {e}")
            return f"Could not add task, sir. {e}"

    def list_tasks(self, show_completed: bool = False) -> str:
        svc = self._svc()
        if not svc:
            return NOT_CONFIGURED_MSG
        list_id = self._default_list()
        if not list_id:
            return "Could not access your task list, sir."
        try:
            result = svc.tasks().list(
                tasklist=list_id, showCompleted=show_completed
            ).execute()
            tasks = result.get("items", [])
            pending = [t for t in tasks if t.get("status") != "completed"]
            if not pending:
                return "Your to-do list is empty, sir. Nothing pending."
            lines = [f"• {t['title']}" for t in pending]
            return f"You have {len(pending)} task(s), sir:\n" + "\n".join(lines)
        except Exception as e:
            log.warning(f"List tasks error: {e}")
            return f"Could not fetch tasks, sir. {e}"

    def complete_task(self, title_query: str) -> str:
        svc = self._svc()
        if not svc:
            return NOT_CONFIGURED_MSG
        list_id = self._default_list()
        if not list_id:
            return "Could not access your task list, sir."
        try:
            result = svc.tasks().list(tasklist=list_id).execute()
            tasks = result.get("items", [])
            for t in tasks:
                if title_query.lower() in t["title"].lower():
                    svc.tasks().patch(
                        tasklist=list_id, task=t["id"],
                        body={"status": "completed"}
                    ).execute()
                    return f"Marked '{t['title']}' as done, sir."
            return f"Could not find a task matching '{title_query}', sir."
        except Exception as e:
            log.warning(f"Complete task error: {e}")
            return f"Could not complete task, sir. {e}"


tasks_manager = TasksManager()
