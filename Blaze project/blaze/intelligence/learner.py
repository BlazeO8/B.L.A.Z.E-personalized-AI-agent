"""
B.L.A.Z.E — Pattern Learner (Feature 3)
Learns user habits by time-of-day and day-of-week, tracks command frequency,
and generates predictive suggestions.
"""

import datetime
from blaze.core.database import db


class PatternLearner:
    """
    Learns user habits:
    - Time-based patterns (what the user does at 9am, etc.)
    - Frequency patterns (most used commands)
    - Predictive suggestions
    """

    def __init__(self):
        self._session_commands = []

    def record(self, command: str):
        now     = datetime.datetime.now()
        hour    = now.hour
        dow     = now.strftime("%A")
        pattern = f"{dow}@{hour}h:{command[:30]}"
        db.update_habit(pattern)
        self._session_commands.append(command)

    def predict_suggestion(self) -> str:
        now    = datetime.datetime.now()
        hour   = now.hour
        dow    = now.strftime("%A")
        prefix = f"{dow}@{hour}h:"
        rows   = db.fetchall(
            "SELECT pattern, frequency FROM habit_patterns "
            "WHERE pattern LIKE ? ORDER BY frequency DESC LIMIT 1",
            (f"{prefix}%",)
        )
        if rows:
            pattern, freq = rows[0]
            cmd = pattern.split(":", 1)[-1] if ":" in pattern else pattern
            if freq >= 2:
                return f"You often run '{cmd}' at this time, sir. Shall I proceed?"
        return ""

    def weekly_summary(self) -> str:
        rows = db.get_top_habits(5)
        if not rows:
            return "No patterns recorded yet, sir."
        lines = ["Top habits this week:"]
        for pattern, freq in rows:
            cmd = pattern.split(":", 1)[-1] if ":" in pattern else pattern
            lines.append(f"  • {cmd} ({freq}x)")
        return "\n".join(lines)

    def get_feedback_stats(self) -> str:
        avg   = db.get_avg_rating()
        total = db.fetchone("SELECT COUNT(*) FROM feedback")[0]
        if avg:
            return f"Average satisfaction: {avg}/5 across {total} rated responses."
        return "No feedback recorded yet."


# ── Singleton ─────────────────────────────────────────────────────────────────
learner = PatternLearner()
