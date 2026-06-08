"""
B.L.A.Z.E — Database
SQLite-backed persistence for conversations, reminders, notes,
preferences, usage stats, feedback, habit patterns, and custom commands.
"""

import datetime
import sqlite3
import threading
import atexit

from blaze.config import DB_PATH, MAX_HISTORY
from blaze.core.logging_audit import log


# ══════════════════════════════════════════════════════════════════════════════
#  Batch writer helper
# ══════════════════════════════════════════════════════════════════════════════
class _BatchWriter:
    """Wraps a Database connection so multiple inserts share one commit."""

    def __init__(self, db_instance):
        self._db = db_instance

    def __enter__(self):
        return self

    def execute(self, sql, params=()):
        with self._db._lock:
            self._db.conn.execute(sql, params)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        with self._db._lock:
            if exc_type is None:
                self._db.conn.commit()
            else:
                self._db.conn.rollback()
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  Database
# ══════════════════════════════════════════════════════════════════════════════
class Database:
    def __init__(self):
        self.conn  = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self):
        with self._lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    role     TEXT NOT NULL,
                    content  TEXT NOT NULL,
                    emotion  TEXT DEFAULT 'neutral',
                    ts       DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS preferences (
                    key      TEXT PRIMARY KEY,
                    value    TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reminders (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    message  TEXT NOT NULL,
                    fire_at  DATETIME NOT NULL,
                    done     INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS automation_rules (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    trigger  TEXT NOT NULL,
                    action   TEXT NOT NULL,
                    enabled  INTEGER DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS knowledge_base (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    title    TEXT NOT NULL,
                    content  TEXT NOT NULL,
                    tags     TEXT,
                    domain   TEXT DEFAULT 'general',
                    created  DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS usage_stats (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    command  TEXT NOT NULL,
                    hour     INTEGER,
                    dow      INTEGER,
                    ts       DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS feedback (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_msg   TEXT,
                    blaze_msg  TEXT,
                    rating     INTEGER,
                    ts         DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS habit_patterns (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern   TEXT NOT NULL,
                    frequency INTEGER DEFAULT 1,
                    last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS custom_commands (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    trigger  TEXT NOT NULL UNIQUE,
                    response TEXT NOT NULL,
                    action   TEXT DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS domain_notes (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    domain   TEXT NOT NULL,
                    content  TEXT NOT NULL,
                    ts       DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
            self.conn.commit()
            self._migrate()

    def _migrate(self):
        """Add any missing columns to existing tables (safe to run on every startup)."""
        migrations = [
            ("usage_stats",    "hour",    "INTEGER"),
            ("usage_stats",    "dow",     "INTEGER"),
            ("conversations",  "emotion", "TEXT DEFAULT 'neutral'"),
            ("knowledge_base", "domain",  "TEXT DEFAULT 'general'"),
            ("custom_commands","action",  "TEXT DEFAULT ''"),
        ]
        for table, column, col_type in migrations:
            try:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                self.conn.commit()
                log.info(f"DB migration: added {table}.{column}")
            except sqlite3.OperationalError:
                pass  # Column already exists — expected on a fresh DB

    # ── Core query helpers ────────────────────────────────────────────────────
    def execute(self, sql, params=()):
        with self._lock:
            cur = self.conn.cursor()
            cur.execute(sql, params)
            self.conn.commit()
            return cur

    def batch_write(self):
        """Context manager that batches multiple writes into a single commit."""
        return _BatchWriter(self)

    def fetchall(self, sql, params=()):
        with self._lock:
            cur = self.conn.cursor()
            cur.execute(sql, params)
            return cur.fetchall()

    def fetchone(self, sql, params=()):
        with self._lock:
            cur = self.conn.cursor()
            cur.execute(sql, params)
            return cur.fetchone()

    # ── Preferences ───────────────────────────────────────────────────────────
    def get_pref(self, key, default=None):
        row = self.fetchone("SELECT value FROM preferences WHERE key=?", (key,))
        return row[0] if row else default

    def set_pref(self, key, value):
        self.execute(
            "INSERT OR REPLACE INTO preferences (key,value) VALUES (?,?)",
            (key, str(value))
        )

    # ── Conversation history ──────────────────────────────────────────────────
    def save_message(self, role, content, emotion="neutral"):
        self.execute(
            "INSERT INTO conversations (role,content,emotion) VALUES (?,?,?)",
            (role, content, emotion)
        )

    def load_history(self, limit=MAX_HISTORY):
        rows = self.fetchall(
            "SELECT role, content FROM conversations ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        return [{"role": r, "content": c} for r, c in reversed(rows)]

    def clear_history(self):
        self.execute("DELETE FROM conversations")

    def trim_history(self, keep: int = 500):
        """Delete old messages, keeping only the most recent `keep` rows."""
        self.execute(
            "DELETE FROM conversations WHERE id NOT IN "
            "(SELECT id FROM conversations ORDER BY id DESC LIMIT ?)",
            (keep,)
        )

    # ── Reminders ─────────────────────────────────────────────────────────────
    def add_reminder(self, message, fire_at):
        self.execute(
            "INSERT INTO reminders (message,fire_at) VALUES (?,?)",
            (message, fire_at.isoformat())
        )

    def get_due_reminders(self):
        now = datetime.datetime.now().isoformat()
        rows = self.fetchall(
            "SELECT id, message FROM reminders WHERE fire_at<=? AND done=0",
            (now,)
        )
        for rid, _ in rows:
            self.execute("UPDATE reminders SET done=1 WHERE id=?", (rid,))
        return [msg for _, msg in rows]

    def get_all_reminders(self):
        return self.fetchall(
            "SELECT id, message, fire_at FROM reminders WHERE done=0 ORDER BY fire_at"
        )

    # ── Knowledge base ────────────────────────────────────────────────────────
    def save_note(self, title, content, tags="", domain="general"):
        self.execute(
            "INSERT INTO knowledge_base (title,content,tags,domain) VALUES (?,?,?,?)",
            (title, content, tags, domain)
        )

    def search_notes(self, query):
        return self.fetchall(
            "SELECT title, content, domain FROM knowledge_base "
            "WHERE title LIKE ? OR content LIKE ? OR tags LIKE ?",
            (f"%{query}%", f"%{query}%", f"%{query}%")
        )

    # ── Usage stats ───────────────────────────────────────────────────────────
    def log_command(self, command):
        now = datetime.datetime.now()
        self.execute(
            "INSERT INTO usage_stats (command,hour,dow) VALUES (?,?,?)",
            (command[:80], now.hour, now.weekday())
        )

    def get_top_commands(self, limit=10):
        return self.fetchall(
            "SELECT command, COUNT(*) as cnt FROM usage_stats "
            "GROUP BY command ORDER BY cnt DESC LIMIT ?",
            (limit,)
        )

    # ── Feedback ──────────────────────────────────────────────────────────────
    def save_feedback(self, user_msg, blaze_msg, rating):
        self.execute(
            "INSERT INTO feedback (user_msg,blaze_msg,rating) VALUES (?,?,?)",
            (user_msg, blaze_msg, rating)
        )

    def get_avg_rating(self):
        row = self.fetchone("SELECT AVG(rating) FROM feedback WHERE rating IS NOT NULL")
        return round(row[0], 2) if row and row[0] else None

    # ── Habit patterns ────────────────────────────────────────────────────────
    def update_habit(self, pattern):
        row = self.fetchone(
            "SELECT id, frequency FROM habit_patterns WHERE pattern=?", (pattern,)
        )
        if row:
            self.execute(
                "UPDATE habit_patterns SET frequency=frequency+1, last_seen=CURRENT_TIMESTAMP WHERE id=?",
                (row[0],)
            )
        else:
            self.execute("INSERT INTO habit_patterns (pattern) VALUES (?)", (pattern,))

    def get_top_habits(self, limit=5):
        return self.fetchall(
            "SELECT pattern, frequency FROM habit_patterns ORDER BY frequency DESC LIMIT ?",
            (limit,)
        )

    def cleanup_old_stats(self, days=90):
        """Delete usage_stats and habit_patterns rows older than `days` days.
        Call on startup to prevent unbounded growth."""
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
        self.execute("DELETE FROM usage_stats WHERE ts < ?", (cutoff,))
        self.execute("DELETE FROM habit_patterns WHERE last_seen < ?", (cutoff,))
        log.info(f"DB cleanup: removed stats older than {days} days")

    # ── Custom commands ───────────────────────────────────────────────────────
    def add_custom_command(self, trigger, response, action=""):
        self.execute(
            "INSERT OR REPLACE INTO custom_commands (trigger,response,action) VALUES (?,?,?)",
            (trigger, response, action)
        )

    def get_custom_commands(self):
        return self.fetchall("SELECT trigger, response, action FROM custom_commands")

    # ── Automation rules ──────────────────────────────────────────────────────
    def add_rule(self, trigger, action):
        self.execute(
            "INSERT INTO automation_rules (trigger,action) VALUES (?,?)",
            (trigger, action)
        )


# ── Singleton ─────────────────────────────────────────────────────────────────
db = Database()
db.trim_history(500)
db.cleanup_old_stats(90)
atexit.register(lambda: db.conn.close())