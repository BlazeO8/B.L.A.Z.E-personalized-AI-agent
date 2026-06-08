"""
B.L.A.Z.E — Configuration
All constants, paths, and environment variables live here.
"""

from dotenv import load_dotenv
load_dotenv()

import os
from pathlib import Path

# ── AI Model ──────────────────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
MODEL        = "llama-3.3-70b-versatile"
MAX_HISTORY  = 40

# ── Filesystem paths ──────────────────────────────────────────────────────────
DATA_DIR   = Path.home() / ".blaze"
DB_PATH    = DATA_DIR / "blaze.db"
KEY_PATH   = DATA_DIR / "blaze.key"
LOG_PATH   = DATA_DIR / "blaze.log"
PLUGIN_DIR = DATA_DIR / "plugins"
VAULT_PATH = DATA_DIR / "vault.enc"

DATA_DIR.mkdir(exist_ok=True)
PLUGIN_DIR.mkdir(exist_ok=True)

# ── External API keys / settings ──────────────────────────────────────────────
WEATHER_API     = os.getenv("WEATHER_API_KEY", "")
NEWS_API        = os.getenv("NEWS_API_KEY", "")
CITY            = os.getenv("BLAZE_CITY", "Delhi")
SESSION_TIMEOUT = 1800  # 30 min auto-lock
