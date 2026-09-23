"""
B.L.A.Z.E — Proactive Monitor
Runs in the background and triggers alerts, daily briefings,
and habit-prediction suggestions automatically.
"""

import time
import datetime
import threading

from blaze.core.database import db
from blaze.core.logging_audit import log
from blaze.services.system_monitor import monitor
from blaze.intelligence.learner import learner


class ProactiveMonitor:
    def __init__(self, callback):
        self.callback     = callback
        self._last_alert  = {}
        _today            = str(datetime.date.today())
        self._suggestion_shown = db.get_pref(f"suggestion_shown_{_today}") == "1"
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        time.sleep(12)
        while True:
            try:
                for alert in monitor.alert_check():
                    if time.time() - self._last_alert.get(alert, 0) > 300:
                        self._last_alert[alert] = time.time()
                        self.callback("alert", f"⚠ {alert}")
                self._check_briefing()
                self._check_prediction()
            except Exception as e:
                log.error(f"Proactive: {e}")
            time.sleep(60)

    def _check_briefing(self):
        now       = datetime.datetime.now()
        today_key = f"briefing_{now.date()}"
        if db.get_pref(today_key) == "done":
            return
        if now.hour == 8 and now.minute < 5:
            db.set_pref(today_key, "done")
            self.callback("briefing", None)
            return
        if now.hour >= 8:
            missed_key = f"briefing_missed_{now.date()}"
            if db.get_pref(missed_key) != "shown":
                db.set_pref(missed_key, "shown")
                db.set_pref(today_key, "done")
                self.callback("briefing", None)

    def _check_prediction(self):
        if self._suggestion_shown:
            return
        suggestion = learner.predict_suggestion()
        if suggestion:
            self._suggestion_shown = True
            _today = str(datetime.date.today())
            db.set_pref(f"suggestion_shown_{_today}", "1")
            self.callback("suggestion", suggestion)

    def _reset_suggestion(self):
        self._suggestion_shown = False
