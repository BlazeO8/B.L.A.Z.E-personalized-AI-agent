"""
B.L.A.Z.E — Security
Handles Fernet encryption (CryptoManager), the encrypted vault (SecureVault),
and PIN hashing / verification helpers.

SECURITY NOTE — key co-location:
    The encryption key is stored at ~/.blaze/blaze.key alongside the
    encrypted vault at ~/.blaze/vault.enc.  Anyone with read access to
    your home directory can decrypt the vault by reading both files.
    For stronger protection, move blaze.key to a separate location
    (e.g. an external drive or a secrets manager) and update KEY_PATH
    before launching BLAZE.
"""

import json
import secrets
import hashlib

from blaze.config import KEY_PATH, VAULT_PATH
from blaze.deps import crypto_available, Fernet
from blaze.core.logging_audit import log, audit


# ══════════════════════════════════════════════════════════════════════════════
#  Encryption
# ══════════════════════════════════════════════════════════════════════════════
class CryptoManager:
    """Manages Fernet symmetric encryption for the secure vault."""

    def __init__(self):
        self.fernet = None
        if not crypto_available:
            log.warning(
                "CryptoManager: 'cryptography' package not installed — "
                "vault data will be stored in PLAINTEXT. "
                "Run: pip install cryptography"
            )
            return
        try:
            if KEY_PATH.exists():
                key = KEY_PATH.read_bytes()
            else:
                key = Fernet.generate_key()
                KEY_PATH.write_bytes(key)
                try:
                    KEY_PATH.chmod(0o600)
                except Exception:
                    pass
            self.fernet = Fernet(key)
        except Exception as e:
            log.warning(
                f"CryptoManager: Failed to load/generate key — "
                f"vault data will be stored in PLAINTEXT. ({e})"
            )

    def encrypt(self, text: str) -> str:
        if self.fernet:
            return self.fernet.encrypt(text.encode()).decode()
        return text

    def decrypt(self, token: str) -> str:
        if self.fernet:
            try:
                return self.fernet.decrypt(token.encode()).decode()
            except Exception:
                return token
        return token


# ══════════════════════════════════════════════════════════════════════════════
#  Vault
# ══════════════════════════════════════════════════════════════════════════════
class SecureVault:
    """Encrypted key-value store for sensitive data (passwords, tokens, etc.)"""

    def __init__(self, crypto: CryptoManager):
        self.crypto = crypto
        self._data = self._load()

    def _load(self):
        if VAULT_PATH.exists():
            try:
                raw = VAULT_PATH.read_text()
                decrypted = self.crypto.decrypt(raw)
                return json.loads(decrypted)
            except Exception:
                return {}
        return {}

    def _save(self):
        try:
            raw = json.dumps(self._data)
            encrypted = self.crypto.encrypt(raw)
            VAULT_PATH.write_text(encrypted)
        except Exception as e:
            log.error(f"Vault save error: {e}")

    def set(self, key: str, value: str):
        self._data[key] = value
        self._save()
        audit("VAULT_SET", key)

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def delete(self, key: str):
        if key in self._data:
            del self._data[key]
            self._save()
            audit("VAULT_DELETE", key)

    def list_keys(self):
        return list(self._data.keys())


# ══════════════════════════════════════════════════════════════════════════════
#  PIN helpers
# ══════════════════════════════════════════════════════════════════════════════
def hash_pin(pin: str) -> str:
    """Return a 'salt:hash' string using PBKDF2-HMAC-SHA256 (100k rounds)."""
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt.encode(), 100_000).hex()
    return f"{salt}:{h}"


def verify_pin(entered: str, stored: str) -> bool:
    """Verify a PIN against a stored value.

    Accepts both new 'salt:hash' format and legacy bare SHA-256 hashes so
    existing PINs don't stop working after the upgrade.
    """
    if ":" in stored:
        salt, expected = stored.split(":", 1)
        actual = hashlib.pbkdf2_hmac("sha256", entered.encode(), salt.encode(), 100_000).hex()
        return secrets.compare_digest(actual, expected)
    # Legacy: plain SHA-256
    return secrets.compare_digest(hashlib.sha256(entered.encode()).hexdigest(), stored)


# ── Singletons ────────────────────────────────────────────────────────────────
crypto = CryptoManager()
vault  = SecureVault(crypto)
