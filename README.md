# 🔥 B.L.A.Z.E

**A voice-enabled, privacy-minded AI desktop assistant** — powered by Groq LLMs, with a PySide6 GUI (talk-mode orb + chat mode), a FastAPI web/phone interface, Android phone mirroring, and integrations for Google, Spotify, weather and news.

> ⚠️ Windows is the primary target (some features use `pywin32`/`WMI`). Core features run on macOS/Linux too.

---

## ✨ Features

- 🧠 **LLM chat** via [Groq](https://console.groq.com) (default model: `openai/gpt-oss-120b`, configurable)
- 🎙️ **Voice**: wake-word listening, speech recognition, text-to-speech (`pyttsx3` / `edge-tts`)
- 🖥️ **Two GUIs**: modern PySide6 (talk-mode orb + chat window) and the original tkinter GUI
- 🌐 **Web server** (FastAPI + WebSocket) with a browser/phone UI (`blaze_ui.html`)
- 📱 **Android control & screen mirroring** over `adb`
- 📅 **Google integrations**: Calendar, Gmail, Drive, Tasks, Sheets, YouTube, Translate, Maps
- 🎵 **Spotify** playback control
- ⏰ Reminders, automations, daily briefings, weather & news
- 📊 System monitoring & proactive alerts (CPU / RAM / GPU)
- 🔐 Encrypted conversation storage, token auth, rate limiting, audit log
- 🔌 Plugin system

## 📁 Project Structure

```
Blaze/
├── blaze/
│   ├── ai/              # LLM engine, persona, voice
│   ├── core/            # database, security, devices, audit logging
│   ├── data/            # default automations & knowledge JSON
│   ├── gui/             # PySide6 + tkinter interfaces, phone mirror
│   ├── handlers/        # intent handlers (weather, apps, media, ...)
│   ├── intelligence/    # NLP, emotion, learning, automations
│   ├── plugins/         # plugin manager
│   ├── proactive/       # proactive monitor
│   ├── services/        # Google, Spotify-adjacent, system, Android...
│   ├── config.py        # env-driven configuration
│   ├── main.py          # PySide6 GUI entry point
│   └── main_tkinter.py  # legacy tkinter GUI entry point
├── blaze_server.py      # FastAPI web server
├── blaze_ui.html        # Browser / phone UI
├── google_auth.py       # One-time Google OAuth setup
├── spotify_auth.py      # One-time Spotify OAuth setup
├── docs/CHANGES.md      # Development notes
├── .env.example         # Config template
└── requirements.txt
```

## 🚀 Getting Started

### 1. Clone & create a virtual environment

```bash
git clone https://github.com/<your-username>/Blaze.git
cd Blaze

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Python **3.11** is recommended.

### 2. Configure environment variables

```bash
cp .env.example .env        # Windows: copy .env.example .env
```

Edit `.env`. Two values are **required** — the app will refuse to start without them:

| Variable | Required | Where to get it |
|---|---|---|
| `GROQ_API_KEY` | ✅ | https://console.groq.com |
| `API_TOKEN` | ✅ (when `REQUIRE_AUTH=true`) | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `WEATHER_API_KEY` | optional | https://openweathermap.org/api |
| `NEWS_API_KEY` | optional | https://newsapi.org |
| `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` | optional | https://developer.spotify.com/dashboard |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_API_KEY` | optional | https://console.cloud.google.com |
| `BLAZE_CITY` | optional | City used for weather |
| `GROQ_MODEL` | optional | Override the default model |

See `.env.example` for every available setting (server host/port, HTTPS, rate limits, logging, etc.).

### 3. Run it

```bash
# Desktop app (PySide6 GUI)
python -m blaze.main

# Legacy tkinter GUI
python -m blaze.main_tkinter

# Web server  →  http://localhost:8000
python blaze_server.py
```

## 🔗 Optional Integrations

**Google (Calendar, Gmail, Drive, Tasks, Sheets)** — enable the APIs in Google Cloud, create a *Desktop app* OAuth client, add your credentials to `.env`, then run once:

```bash
python google_auth.py
```

**Spotify** — create an app on the Spotify dashboard, set the redirect URI to match `SPOTIFY_REDIRECT_URI`, then:

```bash
python spotify_auth.py
```

**Android phone mirroring** — install [Android Platform Tools](https://developer.android.com/tools/releases/platform-tools) (`adb` on your `PATH`), enable USB debugging, and connect your phone. [`scrcpy`](https://github.com/Genymobile/scrcpy) is optional.

**Microphone input** — if `SpeechRecognition` can't find a mic, install PyAudio: `pip install pyaudio`.

## 🗄️ Where data is stored

Runtime data lives **outside the repo**, in your home directory:

- `~/.blaze/` — database, encryption key (`blaze.key`), encrypted vault, logs, plugins
- `~/.blaze_google_token.json` — Google OAuth token
- `~/.blaze_spotify_cache` — Spotify OAuth cache

## 🔒 Security Notes

- **Never commit `.env`** — it's in `.gitignore`. Only `.env.example` is tracked.
- Keep `REQUIRE_AUTH=true` and set a strong `API_TOKEN`, especially if exposing the server on your LAN (`SERVER_HOST=0.0.0.0`). Use `IP_WHITELIST` to restrict access.
- Keep `DEBUG_MODE=false` and `ALLOW_ALL_ORIGINS=false` outside of development.
- Back up `~/.blaze/blaze.key` — without it, encrypted history can't be decrypted.

## 🤝 Contributing

Issues and PRs are welcome. Please don't include API keys or personal data in commits.

## 📄 License

MIT — see [LICENSE](LICENSE).
