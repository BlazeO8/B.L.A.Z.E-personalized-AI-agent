#!/usr/bin/env python3
"""
B.L.A.Z.E — Dependency Installer
Run this once before starting the server for the first time.

Usage:
    python install_blaze.py
"""

import subprocess
import sys
import platform


def pip(*pkgs):
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", *pkgs])


def section(title):
    print(f"\n{'─' * 50}")
    print(f"  {title}")
    print(f"{'─' * 50}")


section("Core AI (Groq / Llama 3.3 70B)")
pip("groq>=0.9.0")

section("Web server & WebSocket")
pip("fastapi>=0.111.0", "uvicorn[standard]>=0.29.0", "websockets>=12.0", "pydantic>=2.0.0")

section("Environment & config")
pip("python-dotenv>=1.0.0")

section("System monitoring")
pip("psutil>=5.9.0")

section("HTTP requests (weather / news / integrations)")
pip("requests>=2.31.0")

section("Encryption (Secure Vault)")
pip("cryptography>=42.0.0")

section("Text-to-speech (optional)")
pip("pyttsx3>=2.90")

section("Speech recognition (optional)")
pip("SpeechRecognition>=3.10.0")

os_name = platform.system()
if os_name == "Windows":
    try:
        pip("pyaudio")
    except Exception:
        print("  PyAudio install failed — voice input disabled.")
        print("  Fix: pip install pipwin && pipwin install pyaudio")
elif os_name == "Darwin":
    print("  On macOS, install portaudio first:")
    print("    brew install portaudio")
    print("  Then: pip install pyaudio")
else:
    print("  On Linux, install portaudio first:")
    print("    sudo apt install portaudio19-dev python3-pyaudio")
    try:
        pip("pyaudio")
    except Exception:
        print("  PyAudio install failed — voice input disabled.")

print("\n" + "═" * 50)
print("  ✅  All dependencies installed!")
print("═" * 50)
print("\nNext steps:")
print("  1. Create a .env file in your project root:")
print("       GROQ_API_KEY=your_key_here")
print("       WEATHER_API_KEY=your_openweathermap_key   # optional")
print("       NEWS_API_KEY=your_newsapi_key             # optional")
print("       BLAZE_CITY=Delhi                          # your city")
print()
print("  2. Get a FREE Groq API key at: https://console.groq.com")
print()
print("  3. Start the server:")
print("       python blaze_server.py")
print()
print("  4. Open in browser: http://localhost:8000")
print()
print("  5. (Optional) Desktop GUI:")
print("       python -m blaze.main")
