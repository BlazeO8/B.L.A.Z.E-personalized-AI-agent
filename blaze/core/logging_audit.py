"""
B.L.A.Z.E — Logging & Audit
Sets up the main logger and a separate security audit trail.
"""

import sys
import logging
import datetime
from blaze.config import DATA_DIR, LOG_PATH

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("BLAZE")


def audit(event: str, detail: str = ""):
    """Write an entry to the security audit log (separate from the debug log)."""
    entry = f"{datetime.datetime.now().isoformat()} | {event} | {detail}\n"
    try:
        with open(DATA_DIR / "audit.log", "a") as f:
            f.write(entry)
    except Exception as e:
        log.warning(f"Audit log write failed: {e}")
