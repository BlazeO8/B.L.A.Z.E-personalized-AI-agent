"""
B.L.A.Z.E — Settings Dialog
Saves ALL settings to DB so they persist across restarts.
"""

import os
import tkinter as tk
from tkinter import ttk
from blaze.core.database import db
from blaze.core.security import hash_pin
from blaze.ai.persona import persona
from blaze.intelligence.knowledge import knowledge
from blaze.intelligence.automations import automation

# Neon colours
BG      = "#000000"
BG2     = "#050510"
BG3     = "#0a0a1a"
PANEL   = "#080818"
CYAN    = "#00c8ff"
PURPLE  = "#bf00ff"
PURPLE2 = "#330044"
WHITE   = "#e8f4ff"
GREEN   = "#00ff9f"
MUTED   = "#334466"
BORDER  = "#0d1a33"
RED     = "#ff2244"
FM      = ("Courier", 10)
FM8     = ("Courier", 8)
FM9     = ("Courier", 9)
FB      = ("Courier", 11, "bold")


def _section(parent, title):
    tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=16, pady=(10, 2))
    tk.Label(parent, text=title, font=FM8, bg=BG, fg=CYAN).pack(anchor="w", padx=16)


def _row(parent, label, widget_fn, **kw):
    f = tk.Frame(parent, bg=BG)
    f.pack(fill="x", padx=16, pady=3)
    tk.Label(f, text=label, font=FM9, bg=BG, fg=MUTED,
             width=20, anchor="w").pack(side="left")
    w = widget_fn(f, **kw)
    return f, w


def _entry(parent, default="", show=None, width=28):
    e = tk.Entry(parent, font=FM, bg=BG3, fg=WHITE,
                 insertbackground=CYAN, relief="flat",
                 highlightthickness=1, highlightbackground=BORDER,
                 show=show or "", width=width)
    e.insert(0, str(default))
    e.pack(side="left", fill="x", expand=True, ipady=5)
    return e


def _btn(parent, text, cmd, fg=CYAN, bg=BG3):
    b = tk.Button(parent, text=text, font=FM8, bg=bg, fg=fg,
                  relief="flat", padx=10, pady=5, cursor="hand2",
                  activebackground=BG2, command=cmd)
    b.pack(side="left", padx=(4, 0))
    return b


def _update_env(key, value):
    """Update or add a key in .env file. Always uses UTF-8 to avoid Windows cp1252 crashes."""
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    env_path = os.path.abspath(env_path)
    lines = []
    found = False
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            # Fallback: read with errors ignored, salvage what we can
            with open(env_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={value}\n")
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def open_settings_dialog(gui):
    win = tk.Toplevel(gui.root)
    win.title("BLAZE — Settings")
    win.geometry("580x760")
    win.configure(bg=BG)
    win.resizable(False, True)
    win.grab_set()

    # Scrollable canvas
    canvas = tk.Canvas(win, bg=BG, highlightthickness=0)
    sb = tk.Scrollbar(win, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    frame = tk.Frame(canvas, bg=BG)
    canvas.create_window((0, 0), window=frame, anchor="nw")
    frame.bind("<Configure>", lambda e: canvas.configure(
        scrollregion=canvas.bbox("all")))
    def _on_mousewheel(e):
        try:
            if win.winfo_exists() and canvas.winfo_exists():
                canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        except Exception:
            pass  # window/canvas already destroyed — ignore safely

    # Bind only while this window exists, scoped to the window itself
    canvas.bind("<MouseWheel>", _on_mousewheel)
    frame.bind("<MouseWheel>", _on_mousewheel)

    def _on_close():
        try:
            canvas.unbind("<MouseWheel>")
            frame.unbind("<MouseWheel>")
        except Exception:
            pass
        try:
            win.destroy()
        except Exception:
            pass
    win.protocol("WM_DELETE_WINDOW", _on_close)

    # ── Header ────────────────────────────────────────────────────────────────
    tk.Frame(frame, bg=CYAN, height=2).pack(fill="x")
    tk.Label(frame, text="⚙  B.L.A.Z.E  SETTINGS",
             font=("Courier", 14, "bold"), bg=BG, fg=CYAN,
             pady=10).pack()

    # ── Personal ──────────────────────────────────────────────────────────────
    _section(frame, "// PERSONAL INFO")

    _, name_e   = _row(frame, "Your name:",  _entry, default=db.get_pref("user_name", "sir"))
    _, city_e   = _row(frame, "City:",        _entry, default=db.get_pref("BLAZE_CITY", ""))
    _, wthr_e   = _row(frame, "Weather key:", _entry, default=db.get_pref("WEATHER_API_KEY", ""))
    _, news_e   = _row(frame, "News key:",    _entry, default=db.get_pref("NEWS_API_KEY", ""))
    _, sp_id_e  = _row(frame, "Spotify ID:",  _entry, default=db.get_pref("SPOTIFY_CLIENT_ID", ""))
    _, sp_sec_e = _row(frame, "Spotify Secret:", _entry, default=db.get_pref("SPOTIFY_CLIENT_SECRET", ""), show="*")
    _, groq_e   = _row(frame, "GROQ API key:", _entry, default=db.get_pref("GROQ_API_KEY", ""), show="*")

    # ── Voice & TTS ───────────────────────────────────────────────────────────
    _section(frame, "// VOICE & TTS")

    # Tone
    f = tk.Frame(frame, bg=BG); f.pack(fill="x", padx=16, pady=3)
    tk.Label(f, text="Tone:", font=FM9, bg=BG, fg=MUTED, width=20, anchor="w").pack(side="left")
    tone_var = tk.StringVar(value=persona.tone)
    for t in ["professional", "casual", "minimal"]:
        tk.Radiobutton(f, text=t, variable=tone_var, value=t, font=FM9,
                       bg=BG, fg=WHITE, selectcolor=PURPLE2,
                       activebackground=BG).pack(side="left", padx=6)

    # Verbosity
    f = tk.Frame(frame, bg=BG); f.pack(fill="x", padx=16, pady=3)
    tk.Label(f, text="Verbosity:", font=FM9, bg=BG, fg=MUTED, width=20, anchor="w").pack(side="left")
    verb_var = tk.StringVar(value=persona.verbosity)
    for v in ["brief", "normal", "detailed"]:
        tk.Radiobutton(f, text=v, variable=verb_var, value=v, font=FM9,
                       bg=BG, fg=WHITE, selectcolor=PURPLE2,
                       activebackground=BG).pack(side="left", padx=6)

    # TTS Speed
    f = tk.Frame(frame, bg=BG); f.pack(fill="x", padx=16, pady=3)
    tk.Label(f, text="Voice speed:", font=FM9, bg=BG, fg=MUTED, width=20, anchor="w").pack(side="left")
    speed_var = tk.IntVar(value=persona.tts_speed)
    tk.Scale(f, from_=80, to=280, orient="horizontal", variable=speed_var,
             bg=BG, fg=WHITE, troughcolor=BG3, highlightthickness=0,
             length=220, showvalue=True, tickinterval=0,
             activebackground=CYAN).pack(side="left")

    # Voice selector
    _section(frame, "// BLAZE VOICE")
    tk.Label(frame, text="Select the voice BLAZE speaks in:",
             font=FM9, bg=BG, fg=MUTED).pack(anchor="w", padx=16)

    # Edge TTS neural voices (best quality, free)
    EDGE_VOICES = [
        ("Prabhat (Indian Male — Natural)",  "en-IN-PrabhatNeural"),
        ("Neerja (Indian Female — Natural)", "en-IN-NeerjaNeural"),
        ("Guy (US Male — Natural)",          "en-US-GuyNeural"),
        ("Jenny (US Female — Natural)",      "en-US-JennyNeural"),
        ("Davis (US Male — Calm)",           "en-US-DavisNeural"),
        ("Andrew (US Male — Confident)",     "en-US-AndrewNeural"),
        ("Brian (US Male — Casual)",         "en-US-BrianNeural"),
        ("Ryan (UK Male — Natural)",         "en-GB-RyanNeural"),
        ("Sonia (UK Female — Natural)",      "en-GB-SoniaNeural"),
        ("Natasha (AU Female)",              "en-AU-NatashaNeural"),
        ("William (AU Male)",                "en-AU-WilliamNeural"),
    ]

    # Also get installed Windows voices as fallback
    win_voices  = persona.get_all_voices()
    all_voices  = EDGE_VOICES + [
        (f"[Windows] {n}", vid) for n, vid in win_voices
    ]

    tk.Label(frame,
             text="★ Top section = Neural AI voices (Edge TTS) — much more natural",
             font=FM8, bg=BG, fg=GREEN).pack(anchor="w", padx=16)
    tk.Label(frame,
             text="  Bottom section = Built-in Windows voices (robotic)",
             font=FM8, bg=BG, fg=MUTED).pack(anchor="w", padx=16, pady=(0,4))

    voice_frame = tk.Frame(frame, bg=BG3, highlightthickness=1,
                           highlightbackground=BORDER)
    voice_frame.pack(fill="x", padx=16, pady=4)

    voice_listbox = tk.Listbox(
        voice_frame, font=FM9, bg=BG3, fg=WHITE,
        selectbackground=PURPLE, selectforeground=WHITE,
        highlightthickness=0, relief="flat", height=8
    )
    vsb = tk.Scrollbar(voice_frame, orient="vertical",
                       command=voice_listbox.yview)
    voice_listbox.configure(yscrollcommand=vsb.set)
    vsb.pack(side="right", fill="y")
    voice_listbox.pack(fill="x", expand=True)

    voice_ids = []
    for i, (name, vid) in enumerate(all_voices):
        voice_listbox.insert("end", f"  {name}")
        voice_ids.append(vid)
        if vid == persona.voice_id:
            voice_listbox.selection_set(i)
            voice_listbox.see(i)
    # Default select Prabhat if nothing selected
    if not voice_listbox.curselection():
        voice_listbox.selection_set(0)

    def preview_voice():
        sel = voice_listbox.curselection()
        if not sel:
            return
        vid = voice_ids[sel[0]]
        def _preview():
            try:
                if vid.endswith("Neural"):
                    import tempfile, os as _os, subprocess, asyncio, time as _time
                    import edge_tts
                    tmp = tempfile.mktemp(suffix=".mp3")

                    async def _gen():
                        comm = edge_tts.Communicate(
                            "Hello sir, I am Blaze, your personal AI assistant. How can I help you today?",
                            vid
                        )
                        await comm.save(tmp)

                    # Retry generation up to 2 times — edge-tts occasionally
                    # fails silently for specific voice IDs due to service load
                    last_err = None
                    for attempt in range(2):
                        try:
                            asyncio.run(_gen())
                            if _os.path.exists(tmp) and _os.path.getsize(tmp) > 1000:
                                last_err = None
                                break
                            last_err = "generated file was empty or too small"
                        except Exception as e:
                            last_err = str(e)
                        _time.sleep(0.5)

                    if last_err:
                        gui._append("error", f"Preview failed for this voice: {last_err}. Try again or pick another voice.")
                        return

                    # Small delay to ensure file handle is fully released on Windows
                    _time.sleep(0.3)

                    ps_script = (
                        "$ErrorActionPreference = 'Stop'; "
                        "Add-Type -AssemblyName presentationCore; "
                        "$mp = New-Object system.windows.media.mediaplayer; "
                        f"$mp.open('{tmp}'); "
                        "$mp.Play(); "
                        "$timeout = 0; "
                        "while (-not $mp.NaturalDuration.HasTimeSpan -and $timeout -lt 50) { Start-Sleep -m 100; $timeout++ }; "
                        "if ($mp.NaturalDuration.HasTimeSpan) { "
                        "  $dur = $mp.NaturalDuration.TimeSpan.TotalSeconds + 0.5; "
                        "  Start-Sleep -s $dur "
                        "} else { Start-Sleep -s 4 }; "
                        "$mp.Close()"
                    )
                    proc = subprocess.run(
                        ["powershell", "-NoProfile", "-c", ps_script],
                        capture_output=True, text=True, timeout=15
                    )
                    if proc.returncode != 0 and proc.stderr.strip():
                        gui._append("error", f"Playback error: {proc.stderr.strip()[:150]}")

                    try: _os.remove(tmp)
                    except Exception: pass
                else:
                    import pyttsx3
                    eng = pyttsx3.init()
                    eng.setProperty("voice", vid)
                    eng.setProperty("rate", speed_var.get())
                    eng.say("Hello sir, I am Blaze, your personal AI assistant.")
                    eng.runAndWait()
            except ImportError:
                gui._append("error", "Run: py -3.11 -m pip install edge-tts")
            except Exception as e:
                gui._append("error", f"Preview error: {e}")
        import threading
        threading.Thread(target=_preview, daemon=True).start()

    f = tk.Frame(frame, bg=BG); f.pack(fill="x", padx=16, pady=2)
    tk.Label(f, text="", bg=BG, width=20).pack(side="left")
    _btn(f, "🔊 PREVIEW VOICE", preview_voice, fg=GREEN)

    # ── Security ──────────────────────────────────────────────────────────────
    _section(frame, "// SECURITY")
    _, pin_e = _row(frame, "Set PIN (lock):", _entry, show="*")

    # ── Knowledge base ────────────────────────────────────────────────────────
    _section(frame, "// KNOWLEDGE BASE")
    kb_box = tk.Text(frame, font=FM9, bg=BG3, fg=GREEN, height=3,
                     relief="flat", highlightthickness=1,
                     highlightbackground=BORDER, padx=6, pady=4)
    kb_box.insert("1.0", knowledge.list_all())
    kb_box.config(state="disabled")
    kb_box.pack(fill="x", padx=16, pady=4)

    f = tk.Frame(frame, bg=BG); f.pack(fill="x", padx=16, pady=2)
    tk.Label(f, text="Add fact:", font=FM9, bg=BG, fg=MUTED,
             width=10, anchor="w").pack(side="left")
    fact_e = tk.Entry(f, font=FM, bg=BG3, fg=WHITE,
                      insertbackground=CYAN, relief="flat",
                      highlightthickness=1, highlightbackground=BORDER)
    fact_e.pack(side="left", fill="x", expand=True, ipady=4)
    def add_fact():
        fact = fact_e.get().strip()
        if fact:
            knowledge.add_fact(fact)
            fact_e.delete(0, "end")
            kb_box.config(state="normal")
            kb_box.delete("1.0", "end")
            kb_box.insert("1.0", knowledge.list_all())
            kb_box.config(state="disabled")
            gui._append("system", f"Remembered: {fact}")
    _btn(f, "ADD", add_fact, fg=CYAN)

    # ── Automations ───────────────────────────────────────────────────────────
    _section(frame, "// AUTOMATION RULES")
    auto_box = tk.Text(frame, font=FM9, bg=BG3, fg=CYAN, height=3,
                       relief="flat", highlightthickness=1,
                       highlightbackground=BORDER, padx=6, pady=4)
    auto_box.insert("1.0", automation.list_rules())
    auto_box.config(state="disabled")
    auto_box.pack(fill="x", padx=16, pady=4)

    f = tk.Frame(frame, bg=BG); f.pack(fill="x", padx=16, pady=2)
    tk.Label(f, text="Trigger:", font=FM9, bg=BG, fg=MUTED, width=10).pack(side="left")
    atrig_e = tk.Entry(f, font=FM, bg=BG3, fg=WHITE, insertbackground=CYAN,
                       relief="flat", highlightthickness=1, highlightbackground=BORDER)
    atrig_e.pack(side="left", fill="x", expand=True, ipady=4)
    f2 = tk.Frame(frame, bg=BG); f2.pack(fill="x", padx=16, pady=2)
    tk.Label(f2, text="Actions:", font=FM9, bg=BG, fg=MUTED, width=10).pack(side="left")
    aact_e = tk.Entry(f2, font=FM, bg=BG3, fg=WHITE, insertbackground=CYAN,
                      relief="flat", highlightthickness=1, highlightbackground=BORDER)
    aact_e.insert(0, "open chrome, open spotify")
    aact_e.pack(side="left", fill="x", expand=True, ipady=4)
    f3 = tk.Frame(frame, bg=BG); f3.pack(fill="x", padx=16, pady=2)
    tk.Label(f3, text="Time HH:MM:", font=FM9, bg=BG, fg=MUTED, width=10).pack(side="left")
    atime_e = tk.Entry(f3, font=FM, bg=BG3, fg=WHITE, insertbackground=CYAN,
                       relief="flat", highlightthickness=1, highlightbackground=BORDER, width=8)
    atime_e.pack(side="left", ipady=4)
    def add_rule():
        tr = atrig_e.get().strip()
        ac = [a.strip() for a in aact_e.get().split(",")]
        tm = atime_e.get().strip() or None
        if tr and ac:
            automation.add_rule(tr, tr, ac, tm)
            gui._append("system", f"Automation '{tr}' saved.")
            atrig_e.delete(0, "end"); aact_e.delete(0, "end"); atime_e.delete(0, "end")
            auto_box.config(state="normal")
            auto_box.delete("1.0", "end")
            auto_box.insert("1.0", automation.list_rules())
            auto_box.config(state="disabled")
    f4 = tk.Frame(frame, bg=BG); f4.pack(pady=2)
    _btn(f4, "ADD RULE", add_rule, fg=CYAN)

    # ── Save ──────────────────────────────────────────────────────────────────
    tk.Frame(frame, bg=BORDER, height=1).pack(fill="x", padx=16, pady=10)

    def save():
        changes = []   # track what actually changed for accurate feedback

        # Personal info — save to DB AND .env
        name = name_e.get().strip() or "sir"
        if name != persona.name:
            changes.append("name")
        db.set_pref("user_name", name)
        persona.name = name

        city = city_e.get().strip()
        if city and city != db.get_pref("BLAZE_CITY", ""):
            changes.append("city")
            db.set_pref("BLAZE_CITY", city)
            _update_env("BLAZE_CITY", city)

        wk = wthr_e.get().strip()
        if wk and wk != db.get_pref("WEATHER_API_KEY", ""):
            changes.append("weather key")
            db.set_pref("WEATHER_API_KEY", wk)
            _update_env("WEATHER_API_KEY", wk)

        nk = news_e.get().strip()
        if nk and nk != db.get_pref("NEWS_API_KEY", ""):
            changes.append("news key")
            db.set_pref("NEWS_API_KEY", nk)
            _update_env("NEWS_API_KEY", nk)

        sp_id = sp_id_e.get().strip()
        if sp_id and sp_id != db.get_pref("SPOTIFY_CLIENT_ID", ""):
            changes.append("Spotify ID")
            db.set_pref("SPOTIFY_CLIENT_ID", sp_id)
            _update_env("SPOTIFY_CLIENT_ID", sp_id)

        sp_sec = sp_sec_e.get().strip()
        if sp_sec and sp_sec != db.get_pref("SPOTIFY_CLIENT_SECRET", ""):
            changes.append("Spotify secret")
            db.set_pref("SPOTIFY_CLIENT_SECRET", sp_sec)
            _update_env("SPOTIFY_CLIENT_SECRET", sp_sec)

        gk = groq_e.get().strip()
        if gk and gk != db.get_pref("GROQ_API_KEY", ""):
            changes.append("GROQ key")
            db.set_pref("GROQ_API_KEY", gk)
            _update_env("GROQ_API_KEY", gk)

        # Voice/tone settings — track if actually changed
        if tone_var.get() != persona.tone:
            changes.append("tone")
        if verb_var.get() != persona.verbosity:
            changes.append("verbosity")
        if speed_var.get() != persona.tts_speed:
            changes.append("voice speed")

        persona.tone      = tone_var.get()
        persona.verbosity = verb_var.get()
        persona.tts_speed = speed_var.get()

        # Voice selection — only flag as changed if a different voice was picked
        voice_changed = False
        sel = voice_listbox.curselection()
        if sel and voice_ids:
            new_voice = voice_ids[sel[0]]
            if new_voice != persona.voice_id:
                voice_changed = True
                changes.append("voice")
            persona.voice_id = new_voice

        persona.save()

        # PIN
        pin = pin_e.get().strip()
        if pin:
            db.set_pref("pin_hash", hash_pin(pin))
            changes.append("PIN")

        # Only restart the TTS thread if voice or speed actually changed —
        # avoids unnecessary audio interruption for unrelated setting changes
        if voice_changed or "voice speed" in changes:
            try:
                gui.ai.tts_queue.put(None)
                import time as _t; _t.sleep(0.3)
                gui.ai.tts_queue = __import__("queue").Queue()
                gui.ai.tts_engine = None
                gui.ai._start_tts_thread()
                _t.sleep(0.8)
            except Exception:
                pass

        # Build an accurate confirmation message based on what actually changed
        if not changes:
            msg = "No changes detected, sir."
            gui._append("system", msg)
        else:
            msg = f"Settings saved, sir. Updated: {', '.join(changes)}."
            gui._append("system", msg)
            if voice_changed:
                gui.ai.speak("Settings saved. I am now using the new voice, sir.")
            else:
                gui.ai.speak(f"Settings saved, sir.")

        _on_close()

    tk.Button(frame, text="✓  SAVE ALL SETTINGS",
              font=FB, bg=CYAN, fg=BG, relief="flat",
              padx=24, pady=10, cursor="hand2",
              activebackground=GREEN,
              command=save).pack(pady=12)

    tk.Frame(frame, bg=BG, height=20).pack()
