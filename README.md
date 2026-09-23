<div align="center">

# 🔥 B.L.A.Z.E 🔥

### *Your desktop's new best friend. It talks. It listens. It judges your CPU usage.*

!\[Python](https://img.shields.io/badge/python-3.11+-ffcc00?style=for-the-badge\&logo=python\&logoColor=black)
!\[PySide6](https://img.shields.io/badge/GUI-PySide6-ff5500?style=for-the-badge\&logo=qt\&logoColor=white)
!\[Groq](https://img.shields.io/badge/brain-Groq\_LLM-ff0044?style=for-the-badge)
!\[FastAPI](https://img.shields.io/badge/server-FastAPI-00c7a5?style=for-the-badge\&logo=fastapi\&logoColor=white)
!\[Vibes](https://img.shields.io/badge/vibes-immaculate-9d00ff?style=for-the-badge)

**Say *"Hey Blaze"* → a glowing orb wakes up → your computer suddenly has opinions.**

</div>

\---

## 🧨 What even is this?

**B.L.A.Z.E** is a voice-controlled AI desktop assistant that lives on your machine like a tiny
J.A.R.V.I.S. with a caffeine problem. It has a **glowing animated orb**, a **chat window**, a
**phone-friendly web dashboard**, and enough integrations to make your other apps jealous.

It can chat, remind, brief, monitor, search, open apps, mirror your Android phone, play Spotify,
read your Gmail, and quietly panic when your RAM hits 95%.

\---

## ⚡ Features (the good stuff)

||Power|What it does|
|-|-|-|
|🎙️|**Wake word**|Say *"Hey Blaze"* (it even tolerates hilarious mishearings like "hey blade" and "hey glaze")|
|🔮|**Talk Mode**|Animated orb UI that reacts to what's happening, including a danger state when your system is in trouble|
|💬|**Chat Mode**|Full chat window with thinking animation, cancel button, command history, quick actions, live weather and vitals|
|🧠|**LLM brain**|Powered by [Groq](https://console.groq.com) (default model: `openai/gpt-oss-120b`)|
|😤|**Emotional intelligence**|Detects when you're sad, stressed, angry or hyped and adjusts its tone|
|📱|**Phone Mirror**|Live Android screen mirroring + control over `adb`, decoded with PyAV|
|🖥️|**System monitor**|CPU, RAM, disk, battery, GPU stats, with proactive alerts before things catch fire|
|⏰|**Reminders \& automations**|"Remind me to..." actually stores things now. Revolutionary.|
|☀️|**Morning Brief**|Real weather, news and system data, with zero hallucinated numbers|
|📧|**Google suite**|Calendar, Gmail, Drive, Tasks, Sheets, Contacts, YouTube, Maps, Translate|
|🎵|**Spotify**|Control playback (Premium needed for the API bits)|
|🔐|**Encrypted vault**|Because "password123" deserves protection too|
|🧩|**Plugins**|Drop-in plugin system for extending Blaze|
|🌐|**Web dashboard**|FastAPI server + WebSocket UI you can open from your phone|
|🖼️|**Extras**|Image generation, currency conversion, dictionary, Wikipedia, GitHub trending, IP info|
|🦕|**Legacy mode**|The original tkinter UI is still around if you're feeling nostalgic|

\---

## 🚀 Quick Start (5 minutes, tops)

### 1\. Clone it

```bash
git clone https://github.com/BlazeO8/B.L.A.Z.E-personalized-AI-agent.git

cd B.L.A.Z.E-personalized-AI-agent```

### 2\. Make a virtual environment

```bash
python -m venv .venv

# Windows
.venv\\Scripts\\activate

# macOS / Linux
source .venv/bin/activate
```

### 3\. Install the goodies

```bash
pip install -r requirements.txt
```

### 4\. Set up your secrets 🤫

```bash
cp .env.example .env      # Windows: copy .env.example .env
```

Then open `.env` and fill in **at least** these two:

```env
GROQ\_API\_KEY=your\_free\_key\_from\_console.groq.com
API\_TOKEN=paste\_a\_random\_token\_here
```

Generate a token in one line:

```bash
python -c "import secrets; print(secrets.token\_urlsafe(32))"
```

> ⚠️ Blaze \*\*refuses to start\*\* without `GROQ\_API\_KEY`, and without `API\_TOKEN` while `REQUIRE\_AUTH=true`. That's a feature, not a bug.

### 5\. 🔥 LIGHT IT UP

```bash
python -m blaze.main
```

\---

## 🎮 Ways to run it

|Command|What you get|
|-|-|
|`python -m blaze.main`|The shiny **PySide6** desktop app (orb + chat)|
|`python -m blaze.main\_tkinter`|The **legacy tkinter** UI|
|`python blaze\_server.py`|The **web dashboard** at `http://localhost:8000`|
|`python google\_auth.py`|One-time Google OAuth setup|
|`python spotify\_auth.py`|One-time Spotify OAuth setup|

\---

## 🗣️ Things you can say

```text
"Hey Blaze"
"Switch to chat mode"          "Switch to talk mode"
"Give me my morning brief"
"What's the weather?"          "Any news today?"
"Remind me to stretch at 5pm"
"How's my CPU doing?"
"Open Chrome"
"Tell me a joke"
"What can you do?"
```

\---

## 🔌 Optional superpowers

<details>
<summary><b>📧 Google services (Calendar, Gmail, Drive, Tasks, Sheets)</b></summary>

1. Go to the [Google Cloud Console](https://console.cloud.google.com/) and create a project.
2. Enable the Calendar, Gmail, Drive, Tasks and Sheets APIs.
3. Create an **OAuth client ID** (type: *Desktop app*).
4. Add yourself as a **test user** on the consent screen.
5. Put `GOOGLE\_CLIENT\_ID` and `GOOGLE\_CLIENT\_SECRET` in `.env`.
6. Run `python google\_auth.py` once.

</details>

<details>
<summary><b>🎵 Spotify</b></summary>

1. Create an app at the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).
2. Add `http://127.0.0.1:8888/callback` as a redirect URI.
3. Put `SPOTIFY\_CLIENT\_ID` and `SPOTIFY\_CLIENT\_SECRET` in `.env`.
4. Run `python spotify\_auth.py` once.

</details>

<details>
<summary><b>📱 Phone Mirror (Android)</b></summary>

1. Install [Android Platform Tools](https://developer.android.com/tools/releases/platform-tools) and make sure `adb` is on your `PATH`.
2. Enable **USB debugging** on your phone and plug it in.
3. Open the phone mirror panel in the app.

`scrcpy` is optional and only used by the legacy embedded-window mode (`BLAZE\_ENABLE\_SCRCPY\_EMBED=1`).
FFmpeg is **not** required separately since PyAV bundles what it needs.

</details>

<details>
<summary><b>🌐 Web dashboard on your phone</b></summary>

```bash
python blaze\_server.py
```

Open `http://localhost:8000`. To reach it from another device on your network, set
`SERVER\_HOST=0.0.0.0` in `.env` and keep `REQUIRE\_AUTH=true`. Don't expose it to the open internet
without HTTPS and a strong `API\_TOKEN`.

</details>

\---

## 🗂️ Project layout

```text
Blaze/
├── blaze/
│   ├── main.py              # 🚪 PySide6 entry point
│   ├── main\_tkinter.py      # 🦕 legacy tkinter entry point
│   ├── config.py            # ⚙️  all settings, loaded from .env
│   ├── security.py          # 🛡️  security helpers
│   ├── deps.py              # 📦 optional-dependency detection
│   ├── ai/                  # 🧠 LLM engine, persona, voice / wake word
│   ├── core/                # 🗄️  database, devices, encryption, audit log
│   ├── gui/                 # 🎨 orb, chat window, phone mirror, dialogs
│   ├── handlers/            # 🎯 one handler per command type
│   ├── intelligence/        # 🔮 NLP, emotion, learning, automations
│   ├── proactive/           # 🚨 background alerts \& suggestions
│   ├── plugins/             # 🧩 plugin manager
│   ├── services/            # 🔌 Google, Spotify, Android, system stats...
│   └── data/                # 📁 starter automations \& knowledge
├── blaze\_server.py          # 🌐 FastAPI + WebSocket server
├── blaze\_ui.html            # 📱 web dashboard front-end
├── google\_auth.py           # 🔑 one-time Google OAuth
├── spotify\_auth.py          # 🔑 one-time Spotify OAuth
├── docs/CHANGES.md          # 📝 detailed development notes
├── requirements.txt
├── .env.example
└── .gitignore
```

Runtime data (database, logs, encryption key, vault, plugins) lives in `\~/.blaze/`, **outside** the repo.

\---

## 🛡️ Security notes

* 🔑 API keys live in `.env`, which is **git-ignored**. Never commit it.
* 🔒 The web server binds to `127.0.0.1` by default and requires a token.
* 🧱 CORS is restricted to localhost unless you flip `ALLOW\_ALL\_ORIGINS`.
* 🗝️ Conversations are encrypted by default (`ENCRYPT\_CONVERSATIONS=true`).

If you ever accidentally commit a key, **rotate it immediately**. Deleting the commit isn't enough.

\---

## 🪟 Platform notes

Blaze is developed primarily on **Windows** (`pywin32` and `WMI` are Windows-only and installed
automatically there). Most features are guarded so they degrade gracefully on macOS and Linux, but
expect some rough edges.

\---

## 🧯 Troubleshooting

|Problem|Fix|
|-|-|
|`GROQ\_API\_KEY not found`|Create `.env` from `.env.example` and add your key|
|`API\_TOKEN not set but REQUIRE\_AUTH=true`|Generate a token (see Quick Start step 4)|
|Model returns 404 / `model\_not\_found`|Set `GROQ\_MODEL` in `.env` to a currently supported Groq model|
|Phone mirror shows nothing|Check `adb devices`, USB debugging and the USB cable|
|Wake word never triggers|Check your microphone and that `SpeechRecognition` installed properly|

\---

## 🤝 Contributing

1. Fork it 🍴
2. Branch it 🌿 `git checkout -b feature/absurdly-cool-thing`
3. Commit it 💾
4. Push it 🚀
5. Open a PR 🎉

\---

## 📜 License

MIT, see [LICENSE](LICENSE). Go build something wild.

<div align="center">

**Made with ☕, 🔥 and questionable sleep schedules.**

⭐ *If Blaze made you smile, smash that star button.* ⭐

</div>

