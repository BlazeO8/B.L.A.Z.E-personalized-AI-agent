"""
B.L.A.Z.E — Main GUI (BlazeGUI)
Tkinter window, chat display, sidebar, and input area.
"""

import re
import time
import datetime
import threading
from collections import deque
import tkinter as tk
from tkinter import scrolledtext, filedialog
from pathlib import Path

from blaze.config import SESSION_TIMEOUT
from blaze.deps import psutil_available, voice_available
from blaze.core.database import db
from blaze.core.security import verify_pin, hash_pin
from blaze.core.logging_audit import log
from blaze.intelligence.nlp import nlp
from blaze.intelligence.emotional import ei
from blaze.ai.engine import BlazeAI
from blaze.ai.voice import voice_engine
from blaze.ai.persona import persona
from blaze.services.system_monitor import monitor, weather, news_module
from blaze.proactive.monitor import ProactiveMonitor
from blaze.services.system_monitor import ReminderEngine
from blaze.plugins.manager import plugins

import platform


class BlazeGUI:
    # ── Colour palette ────────────────────────────────────────────────────────
    BG      = "#06010e"; BG2 = "#0c0319"; BG3 = "#110428"
    PURPLE  = "#b06aff"; PURPLE2 = "#7c3aed"
    PINK    = "#e040fb"; CYAN = "#00e5ff"; AMBER = "#ffb300"
    GREEN   = "#69ff47"; RED = "#ff4444"
    TEXT    = "#d4b8ff"; TEXT2 = "#ecc8ff"; MUTED = "#5a3a8a"; BORDER = "#2a1060"; WHITE = "#f0e6ff"
    FM  = ("Courier", 11); FM9 = ("Courier", 9); FM8 = ("Courier", 8)
    FB  = ("Courier", 11, "bold"); FH = ("Courier", 18, "bold"); FSM = ("Courier", 10)

    def __init__(self, root):
        self.root         = root
        self.ai           = BlazeAI()
        self.is_listening = False
        self._blink       = True
        self._last_action = time.time()
        self._locked      = False
        self._processing  = False
        self._cancel_flag = threading.Event()
        self._cmd_history     = deque(maxlen=50)
        self._cmd_history_idx = -1

        self.reminder_engine  = ReminderEngine(self._on_reminder)
        self.ai._reminder_engine = self.reminder_engine
        self.proactive        = ProactiveMonitor(self._on_proactive)

        self._setup_window()
        self._build_ui()
        self._start_refresh()
        self._startup_sequence()
        self._start_session_timer()

    # ── Window setup ──────────────────────────────────────────────────────────
    def _setup_window(self):
        self.root.title("B.L.A.Z.E — Personal AI Assistant")
        self.root.geometry("1120x780")
        self.root.configure(bg=self.BG)
        self.root.resizable(True, True)
        self.root.minsize(900, 620)
        try:
            self.root.iconbitmap("blaze.ico")
        except Exception:
            pass

    # ── UI construction ───────────────────────────────────────────────────────
    def _build_ui(self):
        self._build_header()
        self._build_main()
        self._build_footer()

    def _build_header(self):
        hdr = tk.Frame(self.root, bg=self.BG2, pady=10, padx=20)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⬡", font=("Courier", 24), bg=self.BG2, fg=self.PURPLE).pack(side="left", padx=(0, 12))
        tf = tk.Frame(hdr, bg=self.BG2); tf.pack(side="left")
        tk.Label(tf, text="B . L . A . Z . E", font=self.FH, bg=self.BG2, fg=self.PURPLE).pack(anchor="w")
        tk.Label(tf, text="PERSONAL AI ASSISTANT  •  BRILLIANTLY LINKED AUTONOMOUS ZONE ENGINE",
                 font=self.FM8, bg=self.BG2, fg=self.MUTED).pack(anchor="w")

        ctrl = tk.Frame(hdr, bg=self.BG2); ctrl.pack(side="right")

        sf = tk.Frame(ctrl, bg=self.BG2); sf.pack(side="right", padx=(8, 0))
        self.status_dot   = tk.Label(sf, text="●", font=self.FM, bg=self.BG2, fg=self.GREEN)
        self.status_dot.pack(side="left")
        self.status_label = tk.Label(sf, text="ONLINE", font=self.FM8, bg=self.BG2, fg=self.MUTED)
        self.status_label.pack(side="left", padx=4)

        self.voice_btn = tk.Button(
            ctrl,
            text="🔊 VOICE ON" if self.ai.voice_enabled else "🔇 VOICE OFF",
            font=self.FM8, bg=self.BG3, fg=self.CYAN, relief="flat", padx=8, pady=3,
            cursor="hand2", command=self._toggle_voice
        )
        self.voice_btn.pack(side="right", padx=4)

        tk.Button(ctrl, text="⚙ SETTINGS", font=self.FM8, bg=self.BG3, fg=self.MUTED,
                  relief="flat", padx=8, pady=3, cursor="hand2",
                  command=self._open_settings).pack(side="right", padx=4)

        tk.Button(ctrl, text="👍", font=self.FM8, bg=self.BG3, fg=self.GREEN,
                  relief="flat", padx=6, pady=3, cursor="hand2",
                  command=lambda: self._rate(5)).pack(side="right", padx=2)
        tk.Button(ctrl, text="👎", font=self.FM8, bg=self.BG3, fg=self.RED,
                  relief="flat", padx=6, pady=3, cursor="hand2",
                  command=lambda: self._rate(1)).pack(side="right", padx=2)

        tk.Frame(self.root, bg=self.BORDER, height=1).pack(fill="x")

    def _build_main(self):
        main = tk.Frame(self.root, bg=self.BG); main.pack(fill="both", expand=True)
        self._build_left(main)
        tk.Frame(main, bg=self.BORDER, width=1).pack(side="left", fill="y")
        self._build_chat(main)

    def _build_left(self, parent):
        left = tk.Frame(parent, bg=self.BG2, width=270)
        left.pack(side="left", fill="y"); left.pack_propagate(False)

        # Clock
        cf = tk.Frame(left, bg=self.BG3, pady=10); cf.pack(fill="x", padx=8, pady=(10, 4))
        tk.Label(cf, text="// CLOCK", font=self.FM8, bg=self.BG3, fg=self.MUTED).pack(anchor="w", padx=8)
        self.clock_label = tk.Label(cf, text="--:--:--", font=("Courier", 28, "bold"), bg=self.BG3, fg=self.CYAN)
        self.clock_label.pack()
        self.date_label  = tk.Label(cf, text="--", font=self.FM9, bg=self.BG3, fg=self.MUTED)
        self.date_label.pack()

        # System vitals
        sf = tk.Frame(left, bg=self.BG3, pady=8); sf.pack(fill="x", padx=8, pady=4)
        tk.Label(sf, text="// SYSTEM VITALS", font=self.FM8, bg=self.BG3, fg=self.MUTED).pack(anchor="w", padx=8)
        self._bars = {}
        for label, color in [("CPU", self.CYAN), ("RAM", self.PURPLE), ("DISK", self.AMBER)]:
            row = tk.Frame(sf, bg=self.BG3); row.pack(fill="x", padx=8, pady=2)
            tk.Label(row, text=f"{label}:", font=self.FM8, bg=self.BG3, fg=self.MUTED, width=5, anchor="w").pack(side="left")
            bg   = tk.Frame(row, bg=self.BORDER, height=8, width=140); bg.pack(side="left", padx=4); bg.pack_propagate(False)
            fill = tk.Frame(bg, bg=color, height=8); fill.place(x=0, y=0, height=8)
            lbl  = tk.Label(row, text="0%", font=self.FM8, bg=self.BG3, fg=color, width=5); lbl.pack(side="left")
            self._bars[label] = {"bg": bg, "fill": fill, "label": lbl, "color": color}
        self.bat_label = tk.Label(sf, text="Battery: --", font=self.FM8, bg=self.BG3, fg=self.GREEN)
        self.bat_label.pack(anchor="w", padx=8, pady=(2, 4))

        # Weather
        wf = tk.Frame(left, bg=self.BG3, pady=8); wf.pack(fill="x", padx=8, pady=4)
        tk.Label(wf, text="// WEATHER", font=self.FM8, bg=self.BG3, fg=self.MUTED).pack(anchor="w", padx=8)
        self.weather_label = tk.Label(wf, text="Fetching...", font=self.FM9, bg=self.BG3,
                                      fg=self.TEXT, wraplength=220, justify="left")
        self.weather_label.pack(anchor="w", padx=8, pady=4)

        # Quick actions
        qa = tk.Frame(left, bg=self.BG3, pady=8); qa.pack(fill="x", padx=8, pady=4)
        tk.Label(qa, text="// QUICK ACTIONS", font=self.FM8, bg=self.BG3, fg=self.MUTED).pack(anchor="w", padx=8)
        quick = [
            ("⏰ MORNING BRIEF",  "Give me a morning briefing with weather, news, and system status"),
            ("📰 NEWS",           "Get me the latest news headlines"),
            ("🗂 ORGANIZE FILES", "Organize my downloads folder"),
            ("💡 CAPABILITIES",   "What are all your capabilities?"),
            ("📝 REMINDERS",      "List all my pending reminders"),
            ("📊 SYSTEM STATS",   "Show me detailed system statistics"),
            ("🔮 PREDICTIONS",    "What patterns have you learned about me?"),
            ("💰 FEEDBACK STATS", "Show me my feedback and satisfaction stats"),
        ]
        for label, cmd in quick:
            btn = tk.Button(qa, text=label, font=self.FM8, bg=self.BG2, fg=self.TEXT,
                            relief="flat", borderwidth=1, highlightbackground=self.BORDER,
                            highlightthickness=1, padx=6, pady=3, cursor="hand2", anchor="w",
                            command=lambda c=cmd: self._quick(c))
            btn.pack(fill="x", padx=8, pady=1)
            btn.bind("<Enter>", lambda e, b=btn: b.config(fg=self.CYAN))
            btn.bind("<Leave>", lambda e, b=btn: b.config(fg=self.TEXT))

        # Reminders panel
        rf = tk.Frame(left, bg=self.BG3, pady=8); rf.pack(fill="x", padx=8, pady=4)
        tk.Label(rf, text="// REMINDERS", font=self.FM8, bg=self.BG3, fg=self.MUTED).pack(anchor="w", padx=8)
        self.rem_label = tk.Label(rf, text="None", font=self.FM8, bg=self.BG3,
                                  fg=self.MUTED, wraplength=220, justify="left")
        self.rem_label.pack(anchor="w", padx=8, pady=4)

    def _build_chat(self, parent):
        right = tk.Frame(parent, bg=self.BG); right.pack(side="left", fill="both", expand=True)

        # Chips
        chips_f = tk.Frame(right, bg=self.BG2, pady=6, padx=12); chips_f.pack(fill="x")
        for label, cmd in [
            ("TIME", "What time is it?"), ("DATE", "What's today's date?"),
            ("WEATHER", "What's the weather?"), ("JOKE", "Tell me a joke"),
            ("GITHUB", "Show me GitHub trending repos"), ("HELP", "What can you do?"),
            ("CLEAR", "Clear conversation history"),
        ]:
            btn = tk.Button(chips_f, text=label, font=self.FM8, bg=self.BG2, fg=self.MUTED,
                            relief="flat", highlightbackground=self.BORDER, highlightthickness=1,
                            padx=8, pady=2, cursor="hand2", command=lambda c=cmd: self._quick(c))
            btn.pack(side="left", padx=(0, 4))
            btn.bind("<Enter>", lambda e, b=btn: b.config(fg=self.PURPLE))
            btn.bind("<Leave>", lambda e, b=btn: b.config(fg=self.MUTED))

        tk.Frame(right, bg=self.BORDER, height=1).pack(fill="x")

        # Emotion bar
        self.emotion_bar = tk.Label(right, text="", font=self.FM8, bg=self.BG2, fg=self.AMBER, pady=2)
        self.emotion_bar.pack(fill="x", padx=12)

        # Chat display
        chat_outer = tk.Frame(right, bg=self.BG); chat_outer.pack(fill="both", expand=True, padx=12, pady=(6, 0))
        self.chat_display = scrolledtext.ScrolledText(
            chat_outer, bg=self.BG, fg=self.TEXT, font=self.FM, wrap=tk.WORD, state="disabled",
            borderwidth=0, highlightthickness=1, highlightbackground=self.BORDER,
            insertbackground=self.PURPLE, selectbackground=self.PURPLE2,
            padx=12, pady=10, spacing3=4,
        )
        self.chat_display.pack(fill="both", expand=True)
        for tag, fg, font in [
            ("user_label",  self.MUTED,  self.FM8),
            ("user_msg",    self.TEXT,   self.FM),
            ("blaze_label", self.PINK,   self.FM8),
            ("blaze_msg",   self.TEXT2,  self.FM),
            ("system_msg",  self.CYAN,   ("Courier", 10, "italic")),
            ("alert_msg",   self.AMBER,  self.FM),
            ("error_msg",   self.RED,    self.FM),
            ("reminder_msg",self.GREEN,  self.FM),
            ("suggestion",  self.PURPLE, ("Courier", 10, "italic")),
            ("thinking_msg",self.PINK,   ("Courier", 10, "italic")),
        ]:
            self.chat_display.tag_config(tag, foreground=fg, font=font)

        self._thinking_visible = False
        self._thinking_anim_id = None
        self._thinking_dots    = 0
        self._thinking_label   = tk.Label(
            right, text="", font=("Courier", 10, "italic"),
            bg=self.BG2, fg=self.PINK, anchor="w", pady=4, padx=16
        )

        # Input area
        tk.Frame(right, bg=self.BORDER, height=1).pack(fill="x", pady=(6, 0))
        inp_f = tk.Frame(right, bg=self.BG2, pady=10, padx=12); inp_f.pack(fill="x")

        tk.Button(inp_f, text="📎", font=("Courier", 14), bg=self.BG2, fg=self.MUTED,
                  relief="flat", width=2, cursor="hand2",
                  command=self._attach_file).pack(side="left", padx=(0, 4))

        self.mic_btn = tk.Button(inp_f, text="🎙", font=("Courier", 14), bg=self.BG2, fg=self.MUTED,
                                 relief="flat", borderwidth=1, highlightbackground=self.BORDER,
                                 highlightthickness=1, width=3, cursor="hand2", command=self._activate_voice)
        self.mic_btn.pack(side="left", padx=(0, 8))

        self.input_var   = tk.StringVar()
        self.input_field = tk.Entry(inp_f, textvariable=self.input_var, font=self.FM, bg=self.BG,
                                    fg=self.PURPLE, insertbackground=self.PURPLE, relief="flat",
                                    highlightthickness=1, highlightbackground=self.BORDER,
                                    highlightcolor=self.PURPLE)
        self.input_field.pack(side="left", fill="x", expand=True, ipady=8, padx=(0, 8))
        self.input_field.bind("<Return>", lambda e: self._send())
        self.input_field.bind("<Up>",     self._history_up)
        self.input_field.bind("<Key>",    lambda e: setattr(self, "_last_action", time.time()))

        self.send_btn = tk.Button(inp_f, text="SEND ›", font=self.FB, bg=self.PURPLE2, fg=self.WHITE,
                                  relief="flat", padx=16, pady=6, cursor="hand2",
                                  activebackground=self.PURPLE, command=self._send)
        self.send_btn.pack(side="right", padx=(4, 0))

        self.cancel_btn = tk.Button(inp_f, text="✕ CANCEL", font=self.FM8, bg=self.BG3, fg=self.RED,
                                    relief="flat", padx=10, pady=6, cursor="hand2",
                                    command=self._cancel_request, state="disabled")
        self.cancel_btn.pack(side="right", padx=(4, 0))

    def _build_footer(self):
        ft = tk.Frame(self.root, bg=self.BG, pady=3); ft.pack(fill="x")
        tk.Label(ft, text="// CREATED BY KARTIK (BLAZEO8)  •  GROQ FREE INFERENCE",
                 font=self.FM8, bg=self.BG, fg=self.MUTED).pack(side="left", padx=12)
        self.footer_sys = tk.Label(ft, text="", font=self.FM8, bg=self.BG, fg=self.MUTED)
        self.footer_sys.pack(side="right", padx=12)

    # ── Dashboard refresh ─────────────────────────────────────────────────────
    def _start_refresh(self):
        self._refresh_dashboard()

    def _refresh_dashboard(self):
        try:
            now = datetime.datetime.now()
            self.clock_label.config(text=now.strftime("%H:%M:%S"))
            self.date_label.config(text=now.strftime("%A, %b %d %Y"))

            if psutil_available:
                for key, val in [("CPU", monitor.cpu()), ("RAM", monitor.ram()), ("DISK", monitor.disk())]:
                    bi = self._bars[key]
                    bi["label"].config(
                        text=f"{val:.0f}%",
                        fg=self.RED if val > 85 else (self.AMBER if val > 70 else bi["color"])
                    )
                    try:
                        w = int(bi["bg"].winfo_width() * val / 100)
                        bi["fill"].place(x=0, y=0, height=8, width=max(0, w))
                    except Exception:
                        pass

                bat = monitor.battery()
                if bat:
                    plug  = "⚡" if bat["plugged"] else "🔋"
                    color = self.RED if bat["percent"] < 15 else (self.AMBER if bat["percent"] < 30 else self.GREEN)
                    self.bat_label.config(text=f"Battery: {bat['percent']}% {plug}", fg=color)
                self.footer_sys.config(text=monitor.summary())

            if now.second < 2 and now.minute % 10 == 0:
                threading.Thread(target=self._refresh_weather, daemon=True).start()

            rows     = db.get_all_reminders()
            rem_text = "\n".join(f"• {m[:26]} @ {f[11:16]}" for _, m, f in rows[:3]) if rows else "None"
            self.rem_label.config(text=rem_text)

            self._blink = not self._blink
            self.status_dot.config(fg=self.GREEN if self._blink else self.BG2)
        except Exception as e:
            log.warning(f"Dashboard: {e}")
        self.root.after(1000, self._refresh_dashboard)

    def _refresh_weather(self):
        weather._cache      = None
        weather._cache_time = 0
        w    = weather.get()
        text = (
            f"{w.get('city', '?')}: {w.get('temp_c', '?')}°C\n"
            f"{w.get('desc', '?')}\nHumidity: {w.get('humidity', '?')}%"
            if "error" not in w else f"Error: {w['error']}"
        )
        self.root.after(0, lambda: self.weather_label.config(text=text))

    # ── Chat ──────────────────────────────────────────────────────────────────
    def _append(self, role, text):
        self.chat_display.config(state="normal")
        if role == "user":
            self.chat_display.insert("end", "// YOU\n", "user_label")
            self.chat_display.insert("end", text + "\n\n", "user_msg")
        elif role == "blaze":
            clean = re.sub(r"\[SYSTEM:[^\]]+\]", "", text)
            clean = re.sub(r"[*_`]", "", clean).strip()
            self.chat_display.insert("end", "// BLAZE\n", "blaze_label")
            self.chat_display.insert("end", clean + "\n\n", "blaze_msg")
        elif role == "system":
            self.chat_display.insert("end", f"  ⟩ {text}\n\n", "system_msg")
        elif role == "alert":
            self.chat_display.insert("end", f"  ⚠ {text}\n\n", "alert_msg")
        elif role == "error":
            self.chat_display.insert("end", f"  ✗ {text}\n\n", "error_msg")
        elif role == "reminder":
            self.chat_display.insert("end", f"  🔔 REMINDER: {text}\n\n", "reminder_msg")
        elif role == "suggestion":
            self.chat_display.insert("end", f"  🔮 {text}\n\n", "suggestion")
        self.chat_display.config(state="disabled")
        self.chat_display.see("end")

    def _set_status(self, text, color=None):
        self.status_label.config(text=text)
        if color:
            self.status_dot.config(fg=color)

    def _send(self):
        text = self.input_var.get().strip()
        if not text or self._locked:
            return
        self._last_action = time.time()
        self._cmd_history.appendleft(text)
        self._cmd_history_idx = -1
        self.input_var.set("")
        self._append("user", text)

        nlp_result = nlp.analyze(text)
        emotion    = nlp_result.get("emotion", "neutral")
        mood_tag   = ei.mood_tag(emotion)
        self.emotion_bar.config(text=f"Mood detected: {emotion} {mood_tag}" if mood_tag else "")

        self._process(text)

    def _quick(self, cmd):
        self.input_var.set(cmd)
        self._send()

    def _history_up(self, event):
        if not self._cmd_history:
            return
        self._cmd_history_idx = min(self._cmd_history_idx + 1, len(self._cmd_history) - 1)
        self.input_var.set(self._cmd_history[self._cmd_history_idx])

    def _process(self, text):
        self._cancel_flag.clear()
        self._processing = True
        self.send_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.input_field.config(state="disabled")
        self._set_status("PROCESSING...", self.PINK)
        self._show_thinking()

        def run():
            try:
                if self._cancel_flag.is_set():
                    self.root.after(0, self._on_cancelled)
                    return
                reply   = self.ai.chat(text)
                results = self.ai.execute_system_commands(reply)
                if self._cancel_flag.is_set():
                    self.root.after(0, self._on_cancelled)
                    return
            except Exception as e:
                log.error(f"_process thread error: {e}")
                reply   = f"Neural core error, sir: {e}"
                results = []
            self.root.after(0, lambda: self._on_reply(reply, results))

        threading.Thread(target=run, daemon=True).start()

    def _cancel_request(self):
        self._cancel_flag.set()
        self._append("system", "Request cancelled, sir.")
        self._restore_input()

    def _on_cancelled(self):
        self._append("system", "Request cancelled, sir.")
        self._restore_input()

    def _restore_input(self):
        self._processing = False
        self.send_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")
        self.input_field.config(state="normal")
        self.input_field.focus()
        self._set_status("ONLINE", self.GREEN)
        self._hide_thinking()

    def _on_reply(self, reply, results):
        try:
            self._append("blaze", reply)
            for r in results:
                self._append("system", r)
            threading.Thread(target=self.ai.speak, args=(reply,), daemon=True).start()
        except Exception as e:
            log.error(f"_on_reply error: {e}")
        finally:
            self._restore_input()

    # ── Thinking animation ────────────────────────────────────────────────────
    def _show_thinking(self):
        if self._thinking_visible:
            return
        self._thinking_visible = True
        self._thinking_dots    = 0
        self._thinking_label.config(text="// BLAZE  thinking", fg=self.PINK)
        self._thinking_label.pack(fill="x", padx=16, pady=(0, 4))
        self._animate_thinking()

    def _animate_thinking(self):
        if not self._thinking_visible:
            return
        self._thinking_dots = (self._thinking_dots + 1) % 4
        dots = "●" * self._thinking_dots + "○" * (3 - self._thinking_dots)
        self._thinking_label.config(text=f"// BLAZE  {dots}")
        self._thinking_anim_id = self.root.after(400, self._animate_thinking)

    def _hide_thinking(self):
        if not self._thinking_visible:
            return
        self._thinking_visible = False
        if self._thinking_anim_id:
            self.root.after_cancel(self._thinking_anim_id)
            self._thinking_anim_id = None
        self._thinking_label.pack_forget()

    # ── File attachment ───────────────────────────────────────────────────────
    def _attach_file(self):
        path = filedialog.askopenfilename(
            title="Attach file to BLAZE",
            filetypes=[("Text files", "*.txt"), ("Markdown", "*.md"), ("All", "*.*")]
        )
        if not path:
            return
        try:
            content = Path(path).read_text(encoding="utf-8", errors="ignore")[:2000]
            fname   = Path(path).name
            prompt  = f"I'm sharing this file with you: '{fname}'\n\nContent:\n{content}\n\nPlease summarize or help me with this."
            self.input_var.set(prompt)
            self._append("system", f"File attached: {fname}")
        except Exception as e:
            self._append("error", f"Could not read file: {e}")

    # ── Voice ─────────────────────────────────────────────────────────────────
    def _activate_voice(self):
        if self.is_listening or self._locked:
            return
        if not voice_available or not voice_engine.microphone:
            self._append("error", "Voice unavailable — install PyAudio for voice input.")
            return
        self.is_listening = True
        self.mic_btn.config(fg=self.RED)
        self._set_status("LISTENING...", self.RED)
        self._append("system", "Listening... speak now, sir.")

        def run():
            text, err = voice_engine.listen()
            self.is_listening = False
            self.root.after(0, lambda: self.mic_btn.config(fg=self.MUTED))
            if text:
                text = voice_engine.strip_wake_word(text)
                self.root.after(0, lambda: self.input_var.set(text))
                self.root.after(0, self._send)
            else:
                self.root.after(0, lambda: self._append("error", err or "No input detected."))
                self.root.after(0, lambda: self._set_status("ONLINE", self.GREEN))

        threading.Thread(target=run, daemon=True).start()

    def _toggle_voice(self):
        self.ai.voice_enabled = not self.ai.voice_enabled
        db.set_pref("voice_enabled", str(self.ai.voice_enabled).lower())
        self.voice_btn.config(text="🔊 VOICE ON" if self.ai.voice_enabled else "🔇 VOICE OFF")
        self._append("system", f"Voice {'enabled' if self.ai.voice_enabled else 'disabled'}, sir.")

    # ── Feedback ──────────────────────────────────────────────────────────────
    def _rate(self, score):
        msg = self.ai.save_feedback(score)
        self._append("system", msg)

    # ── Proactive callbacks ───────────────────────────────────────────────────
    def _on_reminder(self, message):
        self.root.after(0, lambda: self._append("reminder", message))
        self.root.after(0, lambda: self.ai.speak(f"Reminder, sir: {message}"))

    def _on_proactive(self, ptype, data):
        if ptype == "alert":
            self.root.after(0, lambda: self._append("alert", data))
            self.root.after(0, lambda: self.ai.speak(f"Alert, sir. {data}"))
        elif ptype == "briefing":
            self.root.after(0, self._deliver_briefing)
        elif ptype == "suggestion":
            self.root.after(0, lambda: self._append("suggestion", data))

    def _deliver_briefing(self):
        self._append("system", "Generating morning briefing...")
        def run():
            w       = weather.summary_str()
            h       = news_module.get_headlines(3)
            news_str= "; ".join(h[:3]) if h else "News unavailable."
            sys_str = monitor.summary()
            brief   = (
                f"Good morning, sir. Here is your daily briefing. "
                f"Weather: {w}. Top news: {news_str}. System: {sys_str}."
            )
            self.root.after(0, lambda: self._append("blaze", brief))
            threading.Thread(target=self.ai.speak, args=(brief,), daemon=True).start()
        threading.Thread(target=run, daemon=True).start()

    # ── Session lock ──────────────────────────────────────────────────────────
    def _start_session_timer(self):
        def check():
            if time.time() - self._last_action > SESSION_TIMEOUT and not self._locked:
                self._lock_session()
            self.root.after(60000, check)
        self.root.after(60000, check)

    def _lock_session(self):
        pin = db.get_pref("pin_hash", "")
        if not pin:
            return
        self._locked = True
        self._append("alert", "Session locked due to inactivity. Enter PIN to continue.")
        self.input_field.config(state="normal")
        self.input_var.set("")

        def unlock_check(event=None):
            entered = self.input_var.get().strip()
            if verify_pin(entered, pin):
                self._locked = False
                self.input_var.set("")
                self._append("system", "Session unlocked, sir.")
                self.input_field.bind("<Return>", lambda e: self._send())
            else:
                self._append("error", "Incorrect PIN, sir.")
                self.input_var.set("")

        self.input_field.bind("<Return>", unlock_check)

    # ── Settings dialog ───────────────────────────────────────────────────────
    def _open_settings(self):
        from blaze.gui.dialogs import open_settings_dialog
        open_settings_dialog(self)

    # ── Startup ───────────────────────────────────────────────────────────────
    def _startup_sequence(self):
        threading.Thread(target=self._refresh_weather, daemon=True).start()

        def boot():
            msgs = [
                "Initializing neural core...",
                f"Platform: {platform.system()} {platform.release()}",
                f"Model: {__import__('blaze.config', fromlist=['MODEL']).MODEL}",
                "NLP engine: active",
                "Emotional intelligence: active",
                "Pattern learner: active",
                f"Security vault: {'encrypted' if __import__('blaze.deps', fromlist=['crypto_available']).crypto_available else 'plaintext'}",
                f"Plugins: {len(plugins.plugins)} loaded",
                "All systems nominal.",
            ]
            for msg in msgs:
                import time as _t; _t.sleep(0.3)
                self.root.after(0, lambda m=msg: self._append("system", m))
            import time as _t; _t.sleep(0.3)

            hour     = datetime.datetime.now().hour
            greeting = "Good morning" if hour < 12 else ("Good afternoon" if hour < 17 else "Good evening")
            _name    = (persona.name or "").strip()
            address  = _name if _name and _name.lower() != "sir" else "sir"
            intro    = (
                f"{greeting}, {address}. I am B.L.A.Z.E — Brilliantly Linked Autonomous Zone Engine, "
                f"designed and deployed by Kartik. Neural core is online, all 10 intelligence systems are active, "
                f"and I am fully operational. How may I assist you today?"
            )
            self.root.after(0, lambda: self._append("blaze", intro))

            from blaze.config import GROQ_API_KEY as _KEY
            if not _KEY:
                self.root.after(1000, lambda: self._append("error",
                    "No API key detected. Add GROQ_API_KEY to your .env file. Free at console.groq.com"))
            else:
                threading.Thread(target=self.ai.speak, args=(
                    f"{greeting}, {address}. B.L.A.Z.E. online. All systems nominal. How may I assist?",
                ), daemon=True).start()

            from blaze.intelligence.learner import learner as _learner
            sug = _learner.predict_suggestion()
            if sug and not self.proactive._suggestion_shown:
                self.proactive._suggestion_shown = True
                self.root.after(3000, lambda: self._append("suggestion", sug))

        threading.Thread(target=boot, daemon=True).start()
