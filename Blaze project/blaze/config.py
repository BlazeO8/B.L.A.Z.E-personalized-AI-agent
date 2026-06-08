"""
B.L.A.Z.E — Configuration
All constants, paths, and environment variables live here.

⚠️ SECURITY NOTE:
- Never hardcode API keys here
- Always use .env file for sensitive data
- Use defaults that are safe (empty strings, not actual values)
"""

from dotenv import load_dotenv
load_dotenv()

import os
from pathlib import Path

# ── AI Model ───────────────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
if not GROQ_API_KEY:
    raise ValueError(
        "❌ GROQ_API_KEY not found in .env file!\n"
        "   Get a free key from: https://console.groq.com\n"
        "   Add it to your .env file: GROQ_API_KEY=your_key_here"
    )

MODEL        = "llama-3.3-70b-versatile"
MAX_HISTORY  = 40

# ── Filesystem paths ────────────────────────────────────────────────────────
DATA_DIR   = Path.home() / ".blaze"
DB_PATH    = DATA_DIR / "blaze.db"
KEY_PATH   = DATA_DIR / "blaze.key"
LOG_PATH   = DATA_DIR / "blaze.log"
PLUGIN_DIR = DATA_DIR / "plugins"
VAULT_PATH = DATA_DIR / "vault.enc"

DATA_DIR.mkdir(exist_ok=True)
PLUGIN_DIR.mkdir(exist_ok=True)

# ── External API keys / settings ────────────────────────────────────────────
WEATHER_API     = os.getenv("WEATHER_API_KEY", "")
NEWS_API        = os.getenv("NEWS_API_KEY", "")
CITY            = os.getenv("BLAZE_CITY", "")  # No default - must be set explicitly

# ── Security Configuration ──────────────────────────────────────────────────
SESSION_TIMEOUT = int(os.getenv("SESSION_TIMEOUT", "1800"))  # 30 minutes
API_TOKEN       = os.getenv("API_TOKEN", "")
REQUIRE_AUTH    = os.getenv("REQUIRE_AUTH", "true").lower() == "true"
IP_WHITELIST    = os.getenv("IP_WHITELIST", "").split(",") if os.getenv("IP_WHITELIST") else []

# Validate critical security settings
if REQUIRE_AUTH and not API_TOKEN:
    raise ValueError(
        "❌ API_TOKEN not set but REQUIRE_AUTH=true!\n"
        "   Generate token: python -c \"import secrets; print(secrets.token_urlsafe(32))\"\n"
        "   Add to .env: API_TOKEN=your_token_here"
    )

# ── Server Configuration ─────────────────────────────────────────────────────
SERVER_HOST     = os.getenv("SERVER_HOST", "127.0.0.1")  # Default: localhost only
SERVER_PORT     = int(os.getenv("SERVER_PORT", "8000"))
ENABLE_HTTPS    = os.getenv("ENABLE_HTTPS", "false").lower() == "true"
CERT_FILE       = os.getenv("CERT_FILE", "")
KEY_FILE        = os.getenv("KEY_FILE", "")

# ── Logging & Audit ──────────────────────────────────────────────────────────
LOG_LEVEL                = os.getenv("LOG_LEVEL", "INFO")
ENABLE_REQUEST_LOGGING   = os.getenv("ENABLE_REQUEST_LOGGING", "true").lower() == "true"
ENABLE_AUDIT_LOG         = os.getenv("ENABLE_AUDIT_LOG", "true").lower() == "true"

# ── Rate Limiting ────────────────────────────────────────────────────────────
RATE_LIMIT_REQUESTS      = int(os.getenv("RATE_LIMIT_REQUESTS", "100"))
RATE_LIMIT_WINDOW        = int(os.getenv("RATE_LIMIT_WINDOW", "1"))

# ── Data & Privacy ──────────────────────────────────────────────────────────
HISTORY_RETENTION_DAYS   = int(os.getenv("HISTORY_RETENTION_DAYS", "90"))
ENCRYPT_CONVERSATIONS    = os.getenv("ENCRYPT_CONVERSATIONS", "true").lower() == "true"
MAX_CONNECTIONS          = int(os.getenv("MAX_CONNECTIONS", "50"))

# ── Development Mode ─────────────────────────────────────────────────────────
DEBUG_MODE               = os.getenv("DEBUG_MODE", "false").lower() == "true"
ALLOW_ALL_ORIGINS        = os.getenv("ALLOW_ALL_ORIGINS", "false").lower() == "true"

# ── CORS Configuration ───────────────────────────────────────────────────────
CORS_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:3000",
] if not ALLOW_ALL_ORIGINS else ["*"]

# ── Security Headers ─────────────────────────────────────────────────────────
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains" if ENABLE_HTTPS else "",
}