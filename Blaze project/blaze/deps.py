"""
B.L.A.Z.E — Optional Dependency Detection
All optional imports are resolved here so every other module can simply do:
    from blaze.deps import groq_available, tts_available, ...
"""

# ── dotenv ────────────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Groq ──────────────────────────────────────────────────────────────────────
try:
    from groq import Groq
    groq_available = True
except ImportError:
    Groq = None
    groq_available = False
    print(
        "[BLAZE] WARNING: 'groq' package not found — AI features will be disabled.\n"
        "        To fix, run:  pip install groq\n"
        "        Then restart BLAZE."
    )

# ── TTS ───────────────────────────────────────────────────────────────────────
try:
    import pyttsx3
    tts_available = True
except ImportError:
    pyttsx3 = None
    tts_available = False

# ── Voice / Speech Recognition ────────────────────────────────────────────────
try:
    import speech_recognition as sr
    try:
        _test_mic = sr.Microphone()
        del _test_mic
        voice_available = True
    except (AttributeError, OSError, Exception):
        voice_available = False
except ImportError:
    sr = None
    voice_available = False

# ── Requests ──────────────────────────────────────────────────────────────────
try:
    import requests
    requests_available = True
except ImportError:
    requests = None
    requests_available = False

# ── psutil ────────────────────────────────────────────────────────────────────
try:
    import psutil
    psutil_available = True
except ImportError:
    psutil = None
    psutil_available = False

# ── Cryptography ──────────────────────────────────────────────────────────────
try:
    from cryptography.fernet import Fernet
    crypto_available = True
except ImportError:
    Fernet = None
    crypto_available = False
