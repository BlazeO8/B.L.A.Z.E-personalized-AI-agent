"""
B.L.A.Z.E — Dialogs
Settings window and any other pop-up dialogs, extracted from BlazeGUI
to keep the main app module lean.
"""

import tkinter as tk
from blaze.config import CITY, WEATHER_API, NEWS_API
from blaze.core.database import db
from blaze.core.security import hash_pin
from blaze.ai.persona import persona


def open_settings_dialog(gui):
    """Open the BLAZE settings window.  `gui` is the BlazeGUI instance."""
    win = tk.Toplevel(gui.root)
    win.title("BLAZE Settings")
    win.geometry("500x620")
    win.configure(bg=gui.BG)
    win.grab_set()

    tk.Label(win, text="// BLAZE SETTINGS", font=("Courier", 14, "bold"),
             bg=gui.BG, fg=gui.PURPLE).pack(pady=12)

    fields = [
        ("City for weather:",  "BLAZE_CITY",      CITY),
        ("Weather API (opt):", "WEATHER_API_KEY",  WEATHER_API or ""),
        ("News API (opt):",    "NEWS_API_KEY",      NEWS_API or ""),
        ("Your name:",         "user_name",         persona.name),
    ]
    entries = {}
    for label, key, default in fields:
        f = tk.Frame(win, bg=gui.BG); f.pack(fill="x", padx=24, pady=4)
        tk.Label(f, text=label, font=gui.FM9, bg=gui.BG, fg=gui.MUTED,
                 width=22, anchor="w").pack(side="left")
        e = tk.Entry(f, font=gui.FM, bg=gui.BG3, fg=gui.TEXT,
                     insertbackground=gui.PURPLE, relief="flat",
                     highlightthickness=1, highlightbackground=gui.BORDER)
        e.insert(0, default); e.pack(side="left", fill="x", expand=True, ipady=4)
        entries[key] = e

    # Tone
    f = tk.Frame(win, bg=gui.BG); f.pack(fill="x", padx=24, pady=4)
    tk.Label(f, text="Tone:", font=gui.FM9, bg=gui.BG, fg=gui.MUTED,
             width=22, anchor="w").pack(side="left")
    tone_var = tk.StringVar(value=persona.tone)
    for t in ["professional", "casual", "minimal"]:
        tk.Radiobutton(f, text=t, variable=tone_var, value=t, font=gui.FM9,
                       bg=gui.BG, fg=gui.TEXT, selectcolor=gui.PURPLE2,
                       activebackground=gui.BG).pack(side="left", padx=4)

    # Verbosity
    f = tk.Frame(win, bg=gui.BG); f.pack(fill="x", padx=24, pady=4)
    tk.Label(f, text="Verbosity:", font=gui.FM9, bg=gui.BG, fg=gui.MUTED,
             width=22, anchor="w").pack(side="left")
    verb_var = tk.StringVar(value=persona.verbosity)
    for v in ["brief", "normal", "detailed"]:
        tk.Radiobutton(f, text=v, variable=verb_var, value=v, font=gui.FM9,
                       bg=gui.BG, fg=gui.TEXT, selectcolor=gui.PURPLE2,
                       activebackground=gui.BG).pack(side="left", padx=4)

    # TTS speed
    f = tk.Frame(win, bg=gui.BG); f.pack(fill="x", padx=24, pady=4)
    tk.Label(f, text="TTS Speed:", font=gui.FM9, bg=gui.BG, fg=gui.MUTED,
             width=22, anchor="w").pack(side="left")
    speed_var = tk.IntVar(value=persona.tts_speed)
    tk.Scale(f, from_=100, to=250, orient="horizontal", variable=speed_var,
             bg=gui.BG, fg=gui.TEXT, troughcolor=gui.BG3,
             highlightthickness=0).pack(side="left", fill="x", expand=True)

    # PIN
    f = tk.Frame(win, bg=gui.BG); f.pack(fill="x", padx=24, pady=4)
    tk.Label(f, text="Set PIN (optional):", font=gui.FM9, bg=gui.BG, fg=gui.MUTED,
             width=22, anchor="w").pack(side="left")
    pin_e = tk.Entry(f, font=gui.FM, bg=gui.BG3, fg=gui.TEXT, show="*",
                     insertbackground=gui.PURPLE, relief="flat",
                     highlightthickness=1, highlightbackground=gui.BORDER)
    pin_e.pack(side="left", fill="x", expand=True, ipady=4)

    # Custom command
    tk.Frame(win, bg=gui.BORDER, height=1).pack(fill="x", padx=24, pady=8)
    tk.Label(win, text="// ADD CUSTOM COMMAND", font=gui.FM8,
             bg=gui.BG, fg=gui.MUTED).pack(anchor="w", padx=24)
    cf = tk.Frame(win, bg=gui.BG); cf.pack(fill="x", padx=24, pady=3)
    tk.Label(cf, text="Trigger:", font=gui.FM9, bg=gui.BG, fg=gui.MUTED, width=10).pack(side="left")
    trig_e = tk.Entry(cf, font=gui.FM9, bg=gui.BG3, fg=gui.TEXT,
                      insertbackground=gui.PURPLE, relief="flat",
                      highlightthickness=1, highlightbackground=gui.BORDER)
    trig_e.pack(side="left", fill="x", expand=True, ipady=3)
    rf = tk.Frame(win, bg=gui.BG); rf.pack(fill="x", padx=24, pady=3)
    tk.Label(rf, text="Response:", font=gui.FM9, bg=gui.BG, fg=gui.MUTED, width=10).pack(side="left")
    resp_e = tk.Entry(rf, font=gui.FM9, bg=gui.BG3, fg=gui.TEXT,
                      insertbackground=gui.PURPLE, relief="flat",
                      highlightthickness=1, highlightbackground=gui.BORDER)
    resp_e.pack(side="left", fill="x", expand=True, ipady=3)

    def add_cmd():
        t, r = trig_e.get().strip(), resp_e.get().strip()
        if t and r:
            db.add_custom_command(t, r)
            gui._append("system", f"Custom command added: '{t}' → '{r}'")
            trig_e.delete(0, "end"); resp_e.delete(0, "end")

    tk.Button(win, text="ADD COMMAND", font=gui.FM8, bg=gui.BG3, fg=gui.CYAN,
              relief="flat", padx=10, pady=4, cursor="hand2",
              command=add_cmd).pack(pady=4)

    # Automation rule
    tk.Frame(win, bg=gui.BORDER, height=1).pack(fill="x", padx=24, pady=4)
    tk.Label(win, text="// ADD AUTOMATION RULE", font=gui.FM8,
             bg=gui.BG, fg=gui.MUTED).pack(anchor="w", padx=24)
    af = tk.Frame(win, bg=gui.BG); af.pack(fill="x", padx=24, pady=3)
    tk.Label(af, text="Trigger:", font=gui.FM9, bg=gui.BG, fg=gui.MUTED, width=10).pack(side="left")
    atrig_e = tk.Entry(af, font=gui.FM9, bg=gui.BG3, fg=gui.TEXT,
                       insertbackground=gui.PURPLE, relief="flat",
                       highlightthickness=1, highlightbackground=gui.BORDER)
    atrig_e.pack(side="left", fill="x", expand=True, ipady=3)
    bf = tk.Frame(win, bg=gui.BG); bf.pack(fill="x", padx=24, pady=3)
    tk.Label(bf, text="Action:", font=gui.FM9, bg=gui.BG, fg=gui.MUTED, width=10).pack(side="left")
    aact_e = tk.Entry(bf, font=gui.FM9, bg=gui.BG3, fg=gui.TEXT,
                      insertbackground=gui.PURPLE, relief="flat",
                      highlightthickness=1, highlightbackground=gui.BORDER)
    aact_e.pack(side="left", fill="x", expand=True, ipady=3)

    def add_rule():
        t, a = atrig_e.get().strip(), aact_e.get().strip()
        if t and a:
            db.add_rule(t, a)
            gui._append("system", f"Rule added: '{t}' → '{a}'")
            atrig_e.delete(0, "end"); aact_e.delete(0, "end")

    tk.Button(win, text="ADD RULE", font=gui.FM8, bg=gui.BG3, fg=gui.CYAN,
              relief="flat", padx=10, pady=4, cursor="hand2",
              command=add_rule).pack(pady=4)

    def save():
        for key, e in entries.items():
            v = e.get().strip()
            if v:
                db.set_pref(key, v)
        persona.tone      = tone_var.get()
        persona.verbosity = verb_var.get()
        persona.tts_speed = speed_var.get()
        persona.name      = entries["user_name"].get().strip() or "sir"
        persona.save()
        if gui.ai.tts_engine:
            try:
                gui.ai.tts_engine.setProperty("rate", persona.tts_speed)
            except Exception:
                pass
        pin = pin_e.get().strip()
        if pin:
            db.set_pref("pin_hash", hash_pin(pin))
            gui._append("system", "PIN set successfully, sir.")
        gui._append("system", "Settings saved, sir.")
        win.destroy()

    tk.Button(win, text="SAVE SETTINGS", font=gui.FB, bg=gui.PURPLE2, fg=gui.WHITE,
              relief="flat", padx=20, pady=8, cursor="hand2",
              command=save).pack(pady=12)
