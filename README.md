<div align="center">

```
  ██████╗  ██╗       █████╗  ███████╗ ███████╗
  ██╔══██╗ ██║      ██╔══██╗ ╚══███╔╝ ██╔════╝
██████╔╝ ██║      ███████║   ███╔╝  █████╗
██╔══██╗ ██║      ██╔══██║  ███╔╝   ██╔══╝
  ██████╔╝ ███████╗ ██║  ██║ ███████╗ ███████╗
  ╚═════╝  ╚══════╝ ╚═╝  ╚═╝ ╚══════╝ ╚══════╝
```

**Brilliantly Linked Autonomous Zone Engine**

*A personal AI assistant powered by Groq's Llama 3.3 70B*

[![Python](https://img.shields.io/badge/Python-3.12+-blue?style=flat-square&logo=python)](https://python.org)
[![Groq](https://img.shields.io/badge/Groq-Llama_3.3_70B-orange?style=flat-square)](https://groq.com)
[![FastAPI](https://img.shields.io/badge/FastAPI-WebSocket-green?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-purple?style=flat-square)](LICENSE)

</div>

---

## What is B.L.A.Z.E?

B.L.A.Z.E is a fully local, privacy-first personal AI assistant you run on your own machine. It connects to [Groq's free inference API](https://groq.com) to get blazing-fast responses from Llama 3.3 70B, and gives you two interfaces — a desktop GUI and a browser-based web UI you can even open from your phone on the same Wi-Fi.

It's not just a chatbot. It can open apps, search the web, check the weather, set reminders, monitor your system, read the news, manage files, and learn your habits over time.

---

## Features

| Category | What it does |
|---|---|
| **AI Core** | Groq-powered Llama 3.3 70B with persistent conversation history (40-turn context) |
| **Dual Interface** | Desktop Tkinter GUI + FastAPI web UI with real-time WebSocket streaming |
| **System Control** | Open apps, search the web, launch URLs, manage files, list processes |
| **Reminders** | Natural language reminder parsing — *"remind me to call mom at 6pm"* |
| **System Monitor** | Live CPU, RAM, disk, battery stats in the sidebar |
| **Weather & News** | Current weather for your city + top headlines on demand |
| **Voice I/O** | Text-to-speech replies + speech recognition input (optional) |
| **Emotional IQ** | Detects your mood and responds with empathy |
| **Pattern Learner** | Tracks usage habits and makes proactive suggestions |
| **Secure Vault** | Fernet-encrypted local key-value store for sensitive data |
| **Plugin System** | Drop a `.py` file into `~/.blaze/plugins/` and it auto-loads |
| **Domain Expertise** | Specialist prompts for medical, legal, and financial queries |
| **Morning Briefing** | Weather + news + system stats in one shot |
| **Custom Commands** | Define your own trigger → response → action shortcuts |

---

## Project Structure

```
blaze_project/
├── blaze_server.py          ← FastAPI web server (run this)
├── blaze_ui.html            ← Browser frontend
├── requirements.txt
└── blaze/
    ├── main.py              ← Tkinter desktop entry point
    ├── config.py            ← All env vars and constants
    ├── deps.py              ← Optional dependency loader
    ├── ai/
    │   ├── engine.py        ← BlazeAI: chat, TTS, command dispatch
    │   ├── persona.py       ← Tone and verbosity settings
    │   └── voice.py         ← Voice input
    ├── core/
    │   ├── database.py      ← SQLite ORM (10 tables)
    │   ├── security.py      ← Fernet encryption + SecureVault
    │   └── logging_audit.py ← Structured logging
    ├── intelligence/
    │   ├── nlp.py           ← Intent classification + entity extraction
    │   ├── emotional.py     ← Emotion detection + empathetic responses
    │   ├── learner.py       ← Habit and pattern learning
    │   └── domain.py        ← Domain prompts + system prompt builder
    ├── services/
    │   ├── system_monitor.py ← CPU/RAM/disk + weather + news + reminders
    │   └── integrations.py  ← GitHub, Spotify, Wikipedia, currency, etc.
    ├── plugins/
    │   └── manager.py       ← Dynamic plugin loader
    ├── proactive/
    │   └── monitor.py       ← Background alerts + morning briefing
    └── gui/
        ├── app.py           ← Tkinter GUI
        └── dialogs.py       ← Settings windows
```

---

## Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/B.L.A.Z.E.git
cd B.L.A.Z.E
```

### 2. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 3. Create your `.env` file

```env
GROQ_API_KEY=your_groq_api_key_here
WEATHER_API_KEY=your_openweathermap_key_here   # optional
NEWS_API_KEY=your_newsapi_key_here             # optional
BLAZE_CITY=Delhi                               # your city for weather
```

Get a **free** Groq API key at [console.groq.com](https://console.groq.com).

### 4. Run the server

```bash
python blaze_server.py
```

### 5. Open the UI

Go to **http://localhost:8000** in your browser.

> **Phone access:** Open `http://YOUR_PC_IP:8000` on any device on the same Wi-Fi. Your IP is shown in the terminal when the server starts.

---

## Example Commands

```
"What's the weather today?"
"Open Spotify"
"Search for Python tutorials"
"Remind me to drink water at 3pm"
"What's my CPU usage?"
"Give me the latest news"
"Morning briefing"
"Show system stats"
"Open GitHub"
"What's my battery level?"
```

---

## Optional: Desktop GUI

If you want the Tkinter desktop window instead of the browser UI:

```bash
python -m blaze.main
```

---

## Plugin System

Create a file in `~/.blaze/plugins/myplugin.py`:

```python
def register():
    return {
        "name": "my_plugin",
        "commands": ["my_command"],
        "handler": handle
    }

def handle(cmd, arg):
    if cmd == "my_command":
        return f"You said: {arg}"
```

B.L.A.Z.E auto-loads it on the next restart.

---

## Configuration

All settings live in `~/.blaze/` on your machine:

| File | Purpose |
|---|---|
| `blaze.db` | SQLite database (conversations, reminders, notes, habits) |
| `blaze.key` | Encryption key for the vault |
| `vault.enc` | Encrypted secrets store |
| `blaze.log` | Audit log |
| `plugins/` | Custom plugin directory |

---

## Requirements

- Python 3.12+
- Windows 10/11 (primary support; macOS and Linux work with minor limitations)
- A free [Groq API key](https://console.groq.com)
- Internet connection for AI responses, weather, and news

---

## Built by

**Kartik** (BlazeOS) — built as a personal project to have a proper AI assistant that actually controls the computer, not just chats.

---

<div align="center">
<sub>Powered by <a href="https://groq.com">Groq</a> · Built with FastAPI, SQLite, and too much caffeine</sub>
</div>
