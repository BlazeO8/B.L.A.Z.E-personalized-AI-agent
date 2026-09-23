"""
B.L.A.Z.E — Main GUI (BlazeGUI)
Redesigned: Animated orb, neon theme (black / neon-blue / neon-white / neon-purple),
sidebar vitals, chat panel. Built for desktop use from VS Code / terminal.
"""

import re
import math
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
from blaze.intelligence.automations import automation
from blaze.intelligence.knowledge import knowledge
from blaze.services.calendar import calendar_manager
from blaze.ai.voice import voice_engine
from blaze.ai.persona import persona
from blaze.services.system_monitor import monitor, weather, news_module
from blaze.proactive.monitor import ProactiveMonitor
from blaze.services.system_monitor import ReminderEngine
from blaze.plugins.manager import plugins

import platform


# ══════════════════════════════════════════════════════════════════════════════
#  Colour palette  —  black / neon-blue / neon-white / neon-purple
# ══════════════════════════════════════════════════════════════════════════════
class _C:
    BG          = "#000000"
    BG2         = "#050510"
    BG3         = "#0a0a1a"
    PANEL       = "#080818"

    NEON_BLUE   = "#00c8ff"   # primary neon blue
    NEON_BLUE2  = "#0080ff"   # deeper blue
    NEON_PURPLE = "#bf00ff"   # neon purple
    NEON_PURPLE2= "#7700cc"
    NEON_WHITE  = "#e8f4ff"   # neon white
    NEON_GREEN  = "#00ff9f"
    NEON_AMBER  = "#ffaa00"
    NEON_RED    = "#ff2244"
    NEON_PINK   = "#ff00aa"

    TEXT        = "#c0d8ff"
    TEXT2       = "#e8f4ff"
    MUTED       = "#334466"
    BORDER      = "#0d1a33"

    # fonts
    F_MONO      = ("Courier", 11)
    F_MONO9     = ("Courier", 9)
    F_MONO8     = ("Courier", 8)
    F_BOLD      = ("Courier", 11, "bold")
    F_HEAD      = ("Courier", 20, "bold")
    F_TITLE     = ("Courier", 13, "bold")
    F_SM        = ("Courier", 10)
    F_ITALIC    = ("Courier", 10, "italic")


C = _C()


# ══════════════════════════════════════════════════════════════════════════════
#  Animated ORB — pure Tkinter canvas, Jarvis-inspired
# ══════════════════════════════════════════════════════════════════════════════
class BlazeOrb(tk.Canvas):
    """
    Animated energy orb. Concentric rotating rings, pulsing core glow,
    particle sparks, and the BLAZE wordmark at the centre.
    """
    SIZE = 220

    def __init__(self, parent, **kwargs):
        super().__init__(
            parent,
            width=self.SIZE, height=self.SIZE,
            bg=C.BG, highlightthickness=0, **kwargs
        )
        self.cx = self.SIZE / 2
        self.cy = self.SIZE / 2

        self._angle       = 0.0
        self._pulse       = 0.0
        self._state       = "idle"     # idle | thinking | speaking | alert
        self._particles   = []
        self._frame       = 0

        self._init_particles()
        self._draw()

    def _init_particles(self):
        import random
        self._particles = []
        for _ in range(18):
            angle  = __import__('random').uniform(0, 2 * math.pi)
            radius = __import__('random').uniform(55, 90)
            speed  = __import__('random').uniform(0.008, 0.025)
            size   = __import__('random').randint(1, 3)
            self._particles.append({
                "angle": angle, "radius": radius,
                "speed": speed, "size": size,
                "alpha": __import__('random').uniform(0.3, 1.0)
            })

    def set_state(self, state: str):
        """idle | thinking | speaking | alert"""
        self._state = state

    def _draw(self):
        self.delete("all")
        self._angle  += 0.018 if self._state == "idle" else 0.038
        self._pulse   = (math.sin(self._frame * 0.07) + 1) / 2  # 0..1
        self._frame  += 1

        cx, cy = self.cx, self.cy

        # ── Outer diffuse glow rings ──────────────────────────────────────────
        glow_colors = {
            "idle":     [("#001833", 100), ("#002244", 85), ("#003366", 70)],
            "thinking": [("#1a0033", 100), ("#330066", 85), ("#4400aa", 70)],
            "speaking": [("#001a00", 100), ("#002200", 85), ("#003300", 70)],
            "alert":    [("#330010", 100), ("#550022", 85), ("#880033", 70)],
        }
        for color, r in glow_colors.get(self._state, glow_colors["idle"]):
            self.create_oval(cx-r, cy-r, cx+r, cy+r, fill=color, outline="")

        # ── Rotating outer ring (dashes) ──────────────────────────────────────
        ring_color = {
            "idle":     C.NEON_BLUE,
            "thinking": C.NEON_PURPLE,
            "speaking": C.NEON_GREEN,
            "alert":    C.NEON_RED,
        }.get(self._state, C.NEON_BLUE)

        r_outer = 95
        for i in range(12):
            a = self._angle + i * (2 * math.pi / 12)
            x1 = cx + (r_outer - 6) * math.cos(a)
            y1 = cy + (r_outer - 6) * math.sin(a)
            x2 = cx + r_outer * math.cos(a)
            y2 = cy + r_outer * math.sin(a)
            alpha = 0.4 + 0.6 * abs(math.sin(a + self._frame * 0.05))
            color = self._blend(ring_color, C.BG, alpha)
            self.create_line(x1, y1, x2, y2, fill=color, width=2)

        # ── Counter-rotating middle ring ──────────────────────────────────────
        r_mid = 76
        for i in range(8):
            a = -self._angle * 0.7 + i * (2 * math.pi / 8)
            x1 = cx + (r_mid - 5) * math.cos(a)
            y1 = cy + (r_mid - 5) * math.sin(a)
            x2 = cx + r_mid * math.cos(a)
            y2 = cy + r_mid * math.sin(a)
            self.create_line(x1, y1, x2, y2, fill=C.NEON_PURPLE, width=1)

        # ── Hex accent ring ───────────────────────────────────────────────────
        r_hex = 64
        pts = []
        for i in range(6):
            a = self._angle * 0.3 + i * (math.pi / 3)
            pts.extend([cx + r_hex * math.cos(a), cy + r_hex * math.sin(a)])
        self.create_polygon(pts, outline=C.NEON_BLUE2, fill="", width=1)

        # ── Inner glow core ───────────────────────────────────────────────────
        core_r  = 38 + 8 * self._pulse
        inner_r = 24 + 5 * self._pulse

        core_c  = (C.NEON_GREEN if self._state == "speaking"
                   else C.NEON_PURPLE if self._state == "thinking"
                   else C.NEON_BLUE)
        self.create_oval(cx - core_r, cy - core_r, cx + core_r, cy + core_r,
                         fill="#001122" if self._state == "idle" else "#0a0022",
                         outline=core_c, width=2)
        self.create_oval(cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r,
                         fill="#001a33" if self._state == "idle" else "#110033",
                         outline=C.NEON_WHITE, width=1)

        # ── Particles ─────────────────────────────────────────────────────────
        for p in self._particles:
            p["angle"] += p["speed"] * (1.5 if self._state == "thinking" else 1.0)
            px = cx + p["radius"] * math.cos(p["angle"])
            py = cy + p["radius"] * math.sin(p["angle"])
            s  = p["size"]
            self.create_oval(px-s, py-s, px+s, py+s,
                             fill=ring_color, outline="")

        # ── Scanning sweep line ───────────────────────────────────────────────
        sweep_a = self._angle * 1.5
        sx = cx + 90 * math.cos(sweep_a)
        sy = cy + 90 * math.sin(sweep_a)
        self.create_line(cx, cy, sx, sy, fill=C.NEON_BLUE, width=1,
                         dash=(4, 6))

        # ── Centre text: BLAZE ────────────────────────────────────────────────
        glow_intensity = int(80 + 60 * self._pulse)
        text_color = f"#{glow_intensity:02x}e8ff" if self._state != "thinking" else f"#cc{glow_intensity:02x}ff"
        self.create_text(cx, cy - 2, text="BLAZE",
                         font=("Courier", 14, "bold"),
                         fill=text_color)

        # State indicator dot below text
        dot_color = {
            "idle":     C.NEON_GREEN,
            "thinking": C.NEON_AMBER,
            "speaking": C.NEON_BLUE,
            "alert":    C.NEON_RED,
        }.get(self._state, C.NEON_GREEN)
        dot_r = 3 + int(2 * self._pulse)
        self.create_oval(cx - dot_r, cy + 14 - dot_r,
                         cx + dot_r, cy + 14 + dot_r,
                         fill=dot_color, outline="")

        # ── State label ───────────────────────────────────────────────────────
        label = {
            "idle":     "STANDBY",
            "thinking": "PROCESSING",
            "speaking": "RESPONDING",
            "alert":    "ALERT",
        }.get(self._state, "STANDBY")
        self.create_text(cx, cy + 32, text=label,
                         font=("Courier", 7), fill=C.MUTED)

        self.after(33, self._draw)  # ~30 fps

    @staticmethod
    def _blend(hex_color: str, _bg: str, alpha: float) -> str:
        """Blend a hex colour toward bg by alpha (0=bg, 1=full colour)."""
        try:
            r = int(hex_color[1:3], 16)
            g = int(hex_color[3:5], 16)
            b = int(hex_color[5:7], 16)
            r = int(r * alpha)
            g = int(g * alpha)
            b = int(b * alpha)
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return hex_color


# ══════════════════════════════════════════════════════════════════════════════
#  Main GUI
# ══════════════════════════════════════════════════════════════════════════════
class BlazeGUI:

    def __init__(self, root):
        self.root          = root
        self.ai            = BlazeAI()
        self.is_listening  = False
        self._blink        = True
        self._last_action  = time.time()
        self._locked       = False
        self._processing   = False
        self._cancel_flag  = threading.Event()
        self._cmd_history      = deque(maxlen=50)
        self._cmd_history_idx  = -1

        self.reminder_engine      = ReminderEngine(self._on_reminder)
        self.ai._reminder_engine  = self.reminder_engine
        self.proactive            = ProactiveMonitor(self._on_proactive)

        self._setup_window()
        self._build_ui()
        self._start_refresh()
        self._startup_sequence()
        self._start_session_timer()

    # ── Window ────────────────────────────────────────────────────────────────
    def _setup_window(self):
        self.root.title("B.L.A.Z.E — Personal AI Assistant")
        self.root.geometry("1280x820")
        self.root.configure(bg=C.BG)
        self.root.resizable(True, True)
        self.root.minsize(1000, 680)
        try:
            self.root.iconbitmap("blaze.ico")
        except Exception:
            pass

    # ── UI construction ───────────────────────────────────────────────────────
    def _build_ui(self):
        self._build_header()
        self._build_body()
        self._build_footer()

    # ── HEADER ────────────────────────────────────────────────────────────────
    def _build_header(self):
        hdr = tk.Frame(self.root, bg=C.BG2, pady=0)
        hdr.pack(fill="x")

        # Top neon separator line
        tk.Frame(hdr, bg=C.NEON_BLUE, height=2).pack(fill="x")

        inner = tk.Frame(hdr, bg=C.BG2, padx=20, pady=10)
        inner.pack(fill="x")

        # Left: logo + title
        logo_f = tk.Frame(inner, bg=C.BG2)
        logo_f.pack(side="left")

        tk.Label(logo_f,
                 text="◈",
                 font=("Courier", 28), bg=C.BG2,
                 fg=C.NEON_BLUE).pack(side="left", padx=(0, 14))

        title_f = tk.Frame(logo_f, bg=C.BG2)
        title_f.pack(side="left")
        tk.Label(title_f, text="B . L . A . Z . E",
                 font=C.F_HEAD, bg=C.BG2, fg=C.NEON_WHITE).pack(anchor="w")
        tk.Label(title_f,
                 text="BRILLIANTLY LINKED AUTONOMOUS ZONE ENGINE  ·  PERSONAL AI SYSTEM",
                 font=C.F_MONO8, bg=C.BG2, fg=C.MUTED).pack(anchor="w")

        # Right: controls
        ctrl = tk.Frame(inner, bg=C.BG2)
        ctrl.pack(side="right")

        # Status pill
        sf = tk.Frame(ctrl, bg=C.BG3, padx=10, pady=4)
        sf.pack(side="right", padx=(8, 0))
        self.status_dot   = tk.Label(sf, text="●", font=C.F_MONO8, bg=C.BG3, fg=C.NEON_GREEN)
        self.status_dot.pack(side="left")
        self.status_label = tk.Label(sf, text="ONLINE", font=C.F_MONO8, bg=C.BG3, fg=C.NEON_WHITE)
        self.status_label.pack(side="left", padx=4)

        self.voice_btn = self._hdr_btn(
            ctrl,
            "🔊 VOICE" if self.ai.voice_enabled else "🔇 MUTE",
            C.NEON_BLUE, self._toggle_voice
        )
        self.voice_btn.pack(side="right", padx=4)
        self._hdr_btn(ctrl, "⚙ SETTINGS", C.MUTED, self._open_settings).pack(side="right", padx=4)
        self._hdr_btn(ctrl, "👍", C.NEON_GREEN, lambda: self._rate(5)).pack(side="right", padx=2)
        self._hdr_btn(ctrl, "👎", C.NEON_RED,   lambda: self._rate(1)).pack(side="right", padx=2)

        # Bottom neon separator
        tk.Frame(hdr, bg=C.BORDER, height=1).pack(fill="x")

    def _hdr_btn(self, parent, text, fg, cmd):
        b = tk.Button(parent, text=text, font=C.F_MONO8, bg=C.BG3, fg=fg,
                      relief="flat", padx=10, pady=4, cursor="hand2", command=cmd,
                      activebackground=C.BG2, activeforeground=C.NEON_WHITE)
        b.bind("<Enter>", lambda e: b.config(fg=C.NEON_WHITE))
        b.bind("<Leave>", lambda e: b.config(fg=fg))
        return b

    # ── BODY ──────────────────────────────────────────────────────────────────
    def _build_body(self):
        body = tk.Frame(self.root, bg=C.BG)
        body.pack(fill="both", expand=True)

        self._build_left_panel(body)
        tk.Frame(body, bg=C.BORDER, width=1).pack(side="left", fill="y")
        self._build_centre_panel(body)
        tk.Frame(body, bg=C.BORDER, width=1).pack(side="left", fill="y")
        self._build_right_panel(body)

    # ── LEFT PANEL: orb + system vitals ──────────────────────────────────────
    def _build_left_panel(self, parent):
        left = tk.Frame(parent, bg=C.BG2, width=260)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        # Orb section
        orb_f = tk.Frame(left, bg=C.BG2, pady=16)
        orb_f.pack(fill="x")
        self.orb = BlazeOrb(orb_f)
        self.orb.pack()

        # State label under orb
        self.orb_state_lbl = tk.Label(
            orb_f, text="", font=C.F_MONO8, bg=C.BG2, fg=C.MUTED
        )
        self.orb_state_lbl.pack()

        self._sep(left)

        # Clock
        cf = tk.Frame(left, bg=C.PANEL, pady=10); cf.pack(fill="x", padx=8, pady=4)
        self._section_label(cf, "// CLOCK")
        self.clock_label = tk.Label(cf, text="--:--:--",
                                    font=("Courier", 26, "bold"),
                                    bg=C.PANEL, fg=C.NEON_BLUE)
        self.clock_label.pack()
        self.date_label = tk.Label(cf, text="--", font=C.F_MONO8,
                                   bg=C.PANEL, fg=C.MUTED)
        self.date_label.pack()

        # System vitals
        sf = tk.Frame(left, bg=C.PANEL, pady=8); sf.pack(fill="x", padx=8, pady=4)
        self._section_label(sf, "// SYSTEM VITALS")
        self._bars = {}
        for label, bar_color in [
            ("CPU",  C.NEON_BLUE),
            ("RAM",  C.NEON_PURPLE),
            ("DISK", C.NEON_AMBER),
        ]:
            row = tk.Frame(sf, bg=C.PANEL); row.pack(fill="x", padx=8, pady=3)
            tk.Label(row, text=f"{label}:", font=C.F_MONO8, bg=C.PANEL,
                     fg=C.MUTED, width=5, anchor="w").pack(side="left")
            bg_bar = tk.Frame(row, bg=C.BORDER, height=6, width=130)
            bg_bar.pack(side="left", padx=4); bg_bar.pack_propagate(False)
            fill   = tk.Frame(bg_bar, bg=bar_color, height=6)
            fill.place(x=0, y=0, height=6)
            lbl    = tk.Label(row, text="0%", font=C.F_MONO8,
                              bg=C.PANEL, fg=bar_color, width=5)
            lbl.pack(side="left")
            self._bars[label] = {"bg": bg_bar, "fill": fill, "label": lbl, "color": bar_color}

        self.bat_label = tk.Label(sf, text="Battery: --", font=C.F_MONO8,
                                  bg=C.PANEL, fg=C.NEON_GREEN)
        self.bat_label.pack(anchor="w", padx=8, pady=(2, 4))

        # Weather
        wf = tk.Frame(left, bg=C.PANEL, pady=8); wf.pack(fill="x", padx=8, pady=4)
        self._section_label(wf, "// WEATHER")
        self.weather_label = tk.Label(wf, text="Fetching...", font=C.F_MONO8,
                                      bg=C.PANEL, fg=C.TEXT,
                                      wraplength=220, justify="left")
        self.weather_label.pack(anchor="w", padx=8, pady=4)

        # Reminders
        rf = tk.Frame(left, bg=C.PANEL, pady=8); rf.pack(fill="x", padx=8, pady=4)
        self._section_label(rf, "// REMINDERS")
        self.rem_label = tk.Label(rf, text="None", font=C.F_MONO8,
                                  bg=C.PANEL, fg=C.MUTED,
                                  wraplength=220, justify="left")
        self.rem_label.pack(anchor="w", padx=8, pady=4)

    # ── CENTRE PANEL: chat ───────────────────────────────────────────────────
    def _build_centre_panel(self, parent):
        centre = tk.Frame(parent, bg=C.BG)
        centre.pack(side="left", fill="both", expand=True)

        # Chip bar
        chips_f = tk.Frame(centre, bg=C.BG2, pady=6, padx=12)
        chips_f.pack(fill="x")
        for label, cmd in [
            ("TIME",    "What time is it?"),
            ("DATE",    "What's today's date?"),
            ("WEATHER", "What's the weather in my city?"),
            ("JOKE",    "Tell me a good joke"),
            ("NEWS",    "Get me the latest news headlines"),
            ("GITHUB",  "Show GitHub trending repos"),
            ("HELP",    "What are all your capabilities?"),
            ("IMAGE",   "Generate an image of a futuristic city at night"),
            ("CLEAR",   "Clear conversation history"),
        ]:
            self._chip(chips_f, label, cmd).pack(side="left", padx=(0, 4))

        tk.Frame(centre, bg=C.BORDER, height=1).pack(fill="x")

        # Emotion bar
        self.emotion_bar = tk.Label(centre, text="", font=C.F_MONO8,
                                    bg=C.BG2, fg=C.NEON_AMBER, pady=3)
        self.emotion_bar.pack(fill="x", padx=12)

        # Chat display
        chat_outer = tk.Frame(centre, bg=C.BG)
        chat_outer.pack(fill="both", expand=True, padx=10, pady=(4, 0))

        self.chat_display = scrolledtext.ScrolledText(
            chat_outer, bg=C.BG, fg=C.TEXT, font=C.F_MONO, wrap=tk.WORD,
            state="disabled", borderwidth=0,
            highlightthickness=1, highlightbackground=C.BORDER,
            insertbackground=C.NEON_BLUE,
            selectbackground=C.NEON_BLUE2,
            padx=14, pady=12, spacing3=5,
        )
        self.chat_display.pack(fill="both", expand=True)

        for tag, fg, font in [
            ("user_label",   C.MUTED,       C.F_MONO8),
            ("user_msg",     C.NEON_WHITE,  C.F_MONO),
            ("blaze_label",  C.NEON_BLUE,   C.F_MONO8),
            ("blaze_msg",    C.TEXT,        C.F_MONO),
            ("system_msg",   C.NEON_BLUE,   C.F_ITALIC),
            ("alert_msg",    C.NEON_AMBER,  C.F_MONO),
            ("error_msg",    C.NEON_RED,    C.F_MONO),
            ("reminder_msg", C.NEON_GREEN,  C.F_MONO),
            ("suggestion",   C.NEON_PURPLE, C.F_ITALIC),
            ("thinking_msg", C.NEON_PURPLE, C.F_ITALIC),
        ]:
            self.chat_display.tag_config(tag, foreground=fg, font=font)

        # Thinking label
        self._thinking_visible = False
        self._thinking_anim_id = None
        self._thinking_dots    = 0
        self._thinking_label   = tk.Label(
            centre, text="", font=C.F_ITALIC,
            bg=C.BG2, fg=C.NEON_PURPLE, anchor="w", pady=4, padx=16
        )

        # Input area
        tk.Frame(centre, bg=C.NEON_BLUE, height=1).pack(fill="x", pady=(6, 0))
        inp_f = tk.Frame(centre, bg=C.BG2, pady=10, padx=12)
        inp_f.pack(fill="x")

        # Attach button
        tk.Button(inp_f, text="📎", font=("Courier", 14), bg=C.BG2,
                  fg=C.MUTED, relief="flat", width=2, cursor="hand2",
                  command=self._attach_file).pack(side="left", padx=(0, 4))

        # Mic button
        self.mic_btn = tk.Button(
            inp_f, text="🎙", font=("Courier", 14), bg=C.BG2, fg=C.MUTED,
            relief="flat", highlightthickness=1, highlightbackground=C.BORDER,
            width=3, cursor="hand2", command=self._activate_voice
        )
        self.mic_btn.pack(side="left", padx=(0, 8))

        # Input entry
        self.input_var   = tk.StringVar()
        self.input_field = tk.Entry(
            inp_f, textvariable=self.input_var, font=C.F_MONO,
            bg=C.BG3, fg=C.NEON_WHITE, insertbackground=C.NEON_BLUE,
            relief="flat", highlightthickness=1,
            highlightbackground=C.BORDER, highlightcolor=C.NEON_BLUE
        )
        self.input_field.pack(side="left", fill="x", expand=True, ipady=9, padx=(0, 8))
        self.input_field.bind("<Return>", lambda e: self._send())
        self.input_field.bind("<Up>",     self._history_up)
        self.input_field.bind("<Key>",    lambda e: setattr(self, "_last_action", time.time()))

        # Cancel button
        self.cancel_btn = tk.Button(
            inp_f, text="✕", font=C.F_MONO8, bg=C.BG3, fg=C.NEON_RED,
            relief="flat", padx=10, pady=7, cursor="hand2",
            command=self._cancel_request, state="disabled"
        )
        self.cancel_btn.pack(side="right", padx=(4, 0))

        # Send button
        self.send_btn = tk.Button(
            inp_f, text="SEND  ›", font=C.F_BOLD,
            bg=C.NEON_BLUE2, fg=C.NEON_WHITE,
            relief="flat", padx=18, pady=7, cursor="hand2",
            activebackground=C.NEON_BLUE, command=self._send
        )
        self.send_btn.pack(side="right", padx=(4, 0))

    # ── RIGHT PANEL: quick actions ────────────────────────────────────────────
    def _build_right_panel(self, parent):
        right = tk.Frame(parent, bg=C.BG2, width=220)
        right.pack(side="left", fill="y")
        right.pack_propagate(False)

        qa = tk.Frame(right, bg=C.BG2, pady=12); qa.pack(fill="x", padx=8)
        self._section_label(qa, "// QUICK ACTIONS")

        quick = [
            ("🌅  MORNING BRIEF",   "Give me a full morning briefing with weather, news, and system status"),
            ("📰  TOP NEWS",         "Get me the latest news headlines"),
            ("💻  SYSTEM STATS",     "Show me detailed system statistics including CPU, RAM, disk and battery"),
            ("📂  ORGANIZE FILES",   "Organize my downloads folder"),
            ("⏰  MY REMINDERS",     "List all my pending reminders"),
            ("🔮  MY PATTERNS",      "What patterns have you learned about me?"),
            ("💰  FEEDBACK STATS",   "Show me my feedback and satisfaction stats"),
            ("🌐  MY IP INFO",       "Show my IP address and location info"),
            ("💱  USD → INR",        "Convert 100 USD to INR"),
            ("📖  WIKIPEDIA",        "Give me a Wikipedia summary on artificial intelligence"),
            ("📚  DEFINE WORD",      "Define the word: serendipity"),
            ("🔒  VAULT KEYS",       "List all keys in my secure vault"),
            ("📅  MY MEETINGS",      "List my upcoming meetings"),
            ("📧  CHECK EMAIL",      "Check my email"),
            ("✅  MY TASKS",         "List my tasks"),
            ("📁  DRIVE FILES",      "Show my recent drive files"),
        ]
        for label, cmd in quick:
            b = tk.Button(qa, text=label, font=C.F_MONO8, bg=C.BG3, fg=C.TEXT,
                          relief="flat", borderwidth=0,
                          highlightbackground=C.BORDER, highlightthickness=1,
                          padx=8, pady=5, cursor="hand2", anchor="w",
                          command=lambda c=cmd: self._quick(c))
            b.pack(fill="x", pady=1)
            b.bind("<Enter>", lambda e, btn=b: btn.config(fg=C.NEON_BLUE, bg=C.PANEL))
            b.bind("<Leave>", lambda e, btn=b: btn.config(fg=C.TEXT, bg=C.BG3))

        self._sep(right)

        # Mini info panel
        info_f = tk.Frame(right, bg=C.PANEL, pady=8); info_f.pack(fill="x", padx=8, pady=4)
        self._section_label(info_f, "// NEURAL CORE")
        self.core_status = tk.Label(info_f, text="● GROQ LLM ACTIVE\n● NLP ENGINE ONLINE\n● VOICE READY\n● MEMORY LINKED",
                                    font=C.F_MONO8, bg=C.PANEL, fg=C.NEON_GREEN,
                                    justify="left")
        self.core_status.pack(anchor="w", padx=8, pady=4)

    # ── FOOTER ────────────────────────────────────────────────────────────────
    def _build_footer(self):
        ft = tk.Frame(self.root, bg=C.BG3, pady=4)
        ft.pack(fill="x")
        tk.Frame(ft, bg=C.BORDER, height=1).pack(fill="x")
        inner = tk.Frame(ft, bg=C.BG3); inner.pack(fill="x", padx=12, pady=2)
        tk.Label(inner,
                 text="// CREATED BY KARTIK (BLAZEO8)  ·  GROQ FREE INFERENCE  ·  NASA DISPLAY READY",
                 font=C.F_MONO8, bg=C.BG3, fg=C.MUTED).pack(side="left")
        self.footer_sys = tk.Label(inner, text="", font=C.F_MONO8, bg=C.BG3, fg=C.MUTED)
        self.footer_sys.pack(side="right")

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _section_label(self, parent, text):
        tk.Label(parent, text=text, font=C.F_MONO8,
                 bg=parent.cget("bg"), fg=C.MUTED).pack(anchor="w", padx=8, pady=(0, 2))

    def _sep(self, parent):
        tk.Frame(parent, bg=C.BORDER, height=1).pack(fill="x", padx=8, pady=2)

    def _chip(self, parent, label, cmd):
        b = tk.Button(parent, text=label, font=C.F_MONO8, bg=C.BG3, fg=C.MUTED,
                      relief="flat", highlightbackground=C.BORDER, highlightthickness=1,
                      padx=10, pady=3, cursor="hand2",
                      command=lambda: self._quick(cmd))
        b.bind("<Enter>", lambda e: b.config(fg=C.NEON_BLUE))
        b.bind("<Leave>", lambda e: b.config(fg=C.MUTED))
        return b

    # ── Dashboard refresh ─────────────────────────────────────────────────────
    def _start_refresh(self):
        self._refresh_dashboard()

    def _refresh_dashboard(self):
        try:
            now = datetime.datetime.now()
            self.clock_label.config(text=now.strftime("%H:%M:%S"))
            self.date_label.config(text=now.strftime("%A, %b %d  %Y"))

            if psutil_available:
                for key, val in [("CPU", monitor.cpu()), ("RAM", monitor.ram()), ("DISK", monitor.disk())]:
                    bi = self._bars[key]
                    color = C.NEON_RED if val > 85 else (C.NEON_AMBER if val > 70 else bi["color"])
                    bi["label"].config(text=f"{val:.0f}%", fg=color)
                    try:
                        w = int(bi["bg"].winfo_width() * val / 100)
                        bi["fill"].place(x=0, y=0, height=6, width=max(0, w))
                        bi["fill"].config(bg=color)
                    except Exception:
                        pass

                bat = monitor.battery()
                if bat:
                    plug  = "⚡" if bat["plugged"] else "🔋"
                    color = C.NEON_RED if bat["percent"] < 15 else (C.NEON_AMBER if bat["percent"] < 30 else C.NEON_GREEN)
                    self.bat_label.config(text=f"Battery: {bat['percent']}% {plug}", fg=color)
                self.footer_sys.config(text=monitor.summary())

            if now.second < 2 and now.minute % 10 == 0:
                threading.Thread(target=self._refresh_weather, daemon=True).start()

            rows     = db.get_all_reminders()
            rem_text = "\n".join(f"• {m[:26]} @ {f[11:16]}" for _, m, f in rows[:3]) if rows else "None"
            self.rem_label.config(text=rem_text)

            self._blink = not self._blink
            self.status_dot.config(fg=C.NEON_GREEN if self._blink else C.BG2)
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

    def _set_orb(self, state: str):
        self.orb.set_state(state)
        labels = {
            "idle":     "",
            "thinking": "● Processing neural query...",
            "speaking": "● Transmitting response...",
            "alert":    "● Alert active",
        }
        self.orb_state_lbl.config(text=labels.get(state, ""))

    def _send(self):
        text = self.input_var.get().strip()
        if not text or self._locked:
            return
        self._last_action = time.time()
        self._cmd_history.appendleft(text)
        self._cmd_history_idx = -1
        self.input_var.set("")
        self._append("user", text)

        # Morning brief uses dedicated method with real data — bypasses GROQ
        # to avoid template-placeholder hallucination. Catches typed/voice too.
        low = text.lower()
        if "morning brief" in low or "morning briefing" in low or "daily briefing" in low:
            self._deliver_briefing()
            return

        nlp_result = nlp.analyze(text)
        emotion    = nlp_result.get("emotion", "neutral")
        mood_tag   = ei.mood_tag(emotion)
        self.emotion_bar.config(text=f"Mood detected: {emotion} {mood_tag}" if mood_tag else "")

        self._process(text)

    def _quick(self, cmd):
        # Morning brief uses dedicated method with real data — bypasses GROQ
        # to avoid template-placeholder hallucination
        if "morning briefing" in cmd.lower() or "morning brief" in cmd.lower():
            self._deliver_briefing()
            return
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
        self._set_status("PROCESSING...", C.NEON_PURPLE)
        self._set_orb("thinking")
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
                reply   = f"Neural core error: {e}"
                results = []
            self.root.after(0, lambda: self._on_reply(reply, results))

        threading.Thread(target=run, daemon=True).start()

    def _cancel_request(self):
        self._cancel_flag.set()
        self._append("system", "Request cancelled.")
        self._restore_input()

    def _on_cancelled(self):
        self._append("system", "Request cancelled.")
        self._restore_input()

    def _restore_input(self):
        self._processing = False
        self.send_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")
        self.input_field.config(state="normal")
        self.input_field.focus()
        self._set_status("ONLINE", C.NEON_GREEN)
        self._set_orb("idle")
        self._hide_thinking()

    def _on_reply(self, reply, results):
        try:
            self._append("blaze", reply)
            for r in results:
                self._append("system", r)
            self._set_orb("speaking")
            # Always speak the response — voice_enabled checked inside speak()
            threading.Thread(target=self._speak_then_idle, args=(reply,), daemon=True).start()
        except Exception as e:
            log.error(f"_on_reply error: {e}")
        finally:
            self._restore_input()

    def _speak_then_idle(self, reply):
        # Set orb green = speaking
        self.root.after(0, lambda: self._set_orb("speaking"))
        self.root.after(0, lambda: self._set_status("SPEAKING", C.NEON_GREEN))
        voice_engine.set_responding(True)   # pause hotword so BLAZE doesn't hear itself
        self.ai.speak(reply)
        voice_engine.set_responding(False)  # resume listening
        voice_engine._resume_spotify()      # resume Spotify after BLAZE finishes
        self.root.after(0, lambda: self._set_orb("idle"))
        self.root.after(0, lambda: self._set_status("ONLINE", C.NEON_GREEN))

    # ── Thinking animation ────────────────────────────────────────────────────
    def _show_thinking(self):
        if self._thinking_visible:
            return
        self._thinking_visible = True
        self._thinking_dots    = 0
        self._thinking_label.pack(fill="x", padx=16, pady=(0, 4))
        self._animate_thinking()

    def _animate_thinking(self):
        if not self._thinking_visible:
            return
        self._thinking_dots = (self._thinking_dots + 1) % 4
        dots = "●" * self._thinking_dots + "○" * (3 - self._thinking_dots)
        self._thinking_label.config(text=f"  // BLAZE  {dots}  processing...")
        self._thinking_anim_id = self.root.after(350, self._animate_thinking)

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
        if not voice_engine._hotword_active:
            self._append("error", "Hotword loop not running. Restart BLAZE.")
            return
        self.is_listening = True
        self.mic_btn.config(fg=C.NEON_RED)
        self._set_status("LISTENING...", C.NEON_RED)
        self._set_orb("thinking")   # purple = listening
        self._append("system", "🎙 Listening... speak now.")

        def on_result(text, err):
            self.is_listening = False
            self.root.after(0, lambda: self.mic_btn.config(fg=C.MUTED))
            if text:
                t = voice_engine.strip_wake_word(text)
                self.root.after(0, lambda: self.input_var.set(t))
                self.root.after(0, self._send)
            else:
                self.root.after(0, lambda: self._append("error", err or "No input detected."))
                self.root.after(0, lambda: self._set_status("ONLINE", C.NEON_GREEN))
                self.root.after(0, lambda: self._set_orb("idle"))

        voice_engine.trigger_manual_listen(on_result)

    def _toggle_voice(self):
        self.ai.voice_enabled = not self.ai.voice_enabled
        db.set_pref("voice_enabled", str(self.ai.voice_enabled).lower())
        self.voice_btn.config(text="🔊 VOICE" if self.ai.voice_enabled else "🔇 MUTE")
        self._append("system", f"Voice {'enabled' if self.ai.voice_enabled else 'disabled'}.")

    # ── Feedback ──────────────────────────────────────────────────────────────
    def _rate(self, score):
        msg = self.ai.save_feedback(score)
        self._append("system", msg)

    # ── Proactive callbacks ───────────────────────────────────────────────────
    def _on_reminder(self, message):
        self.root.after(0, lambda: self._append("reminder", message))
        self.root.after(0, lambda: self._set_orb("alert"))
        self.root.after(0, lambda: self.ai.speak(f"Reminder: {message}"))
        self.root.after(3000, lambda: self._set_orb("idle"))

    def _on_proactive(self, ptype, data):
        if ptype == "alert":
            self.root.after(0, lambda: self._append("alert", data))
            self.root.after(0, lambda: self._set_orb("alert"))
            self.root.after(0, lambda: self.ai.speak(f"Alert. {data}"))
            self.root.after(4000, lambda: self._set_orb("idle"))
        elif ptype == "briefing":
            self.root.after(0, self._deliver_briefing)
        elif ptype == "suggestion":
            self.root.after(0, lambda: self._append("suggestion", data))

    def _deliver_briefing(self):
        self._append("system", "Generating morning briefing...")
        def run():
            w        = weather.summary_str()
            h        = news_module.get_headlines(3)
            news_str = "; ".join(h[:3]) if h else "News unavailable."
            sys_str  = monitor.summary()
            brief    = (
                f"Good morning. Here is your daily briefing. "
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
                self._append("system", "Session unlocked.")
                self.input_field.bind("<Return>", lambda e: self._send())
            else:
                self._append("error", "Incorrect PIN.")
                self.input_var.set("")

        self.input_field.bind("<Return>", unlock_check)

    # ── Settings dialog ───────────────────────────────────────────────────────
    def _open_settings(self):
        from blaze.gui.dialogs import open_settings_dialog
        open_settings_dialog(self)

    # ── Startup ───────────────────────────────────────────────────────────────
    def _on_wake_word(self, command: str):
        """Called from background thread when wake word + command detected."""
        if self._locked:
            return
        # If already processing, wait up to 5s for it to finish
        import time as _t
        waited = 0
        while self._processing and waited < 5:
            _t.sleep(0.2)
            waited += 0.2
        if self._processing:
            return  # still busy after 5s — skip

        log.info(f"Wake word GUI received: '{command}'")
        self.root.after(0, lambda: self._set_orb("thinking"))
        self.root.after(0, lambda: self._set_status("WAKE WORD DETECTED", C.NEON_PURPLE))
        self.root.after(0, lambda c=command: self._append("system", f"🎙 Heard: '{c}'"))
        self.root.after(0, lambda c=command: self.input_var.set(c))
        self.root.after(100, self._send)

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
                import time as _t; _t.sleep(0.25)
                self.root.after(0, lambda m=msg: self._append("system", m))
            import time as _t; _t.sleep(0.25)

            hour     = datetime.datetime.now().hour
            greeting = "Good morning" if hour < 12 else ("Good afternoon" if hour < 17 else "Good evening")
            _name    = (persona.name or "").strip()
            address  = _name if _name and _name.lower() != "sir" else "sir"
            intro    = (
                f"{greeting}, {address}. I am B.L.A.Z.E — Brilliantly Linked Autonomous Zone Engine, "
                f"created by Kartik. Neural core online. All intelligence systems active. "
                f"How may I assist you today?"
            )
            self.root.after(0, lambda: self._append("blaze", intro))

            from blaze.config import GROQ_API_KEY as _KEY
            if not _KEY:
                self.root.after(1000, lambda: self._append("error",
                    "No API key detected. Add GROQ_API_KEY to your .env file. Free at console.groq.com"))
            # Wait for TTS engine to actually be ready (not a blind sleep) — up to 5s
            import time as _t2
            waited = 0.0
            while not self.ai.tts_engine and waited < 5.0:
                _t2.sleep(0.2)
                waited += 0.2
            self.ai.speak(
                f"{greeting}, {address}. I am B.L.A.Z.E., your personal AI assistant. All systems are online. How may I assist you today?"
            )

            from blaze.intelligence.learner import learner as _learner
            sug = _learner.predict_suggestion()
            if sug and not self.proactive._suggestion_shown:
                self.proactive._suggestion_shown = True
                self.root.after(3000, lambda: self._append("suggestion", sug))

        threading.Thread(target=boot, daemon=True).start()

        # Start Google Calendar meeting notifier
        def _on_meeting_alert(title, minutes, meet_link):
            msg = f"Reminder: '{title}' starts in {minutes} minute{'s' if minutes != 1 else ''}, sir."
            if meet_link:
                msg += f" Meet link: {meet_link}"
            self.root.after(0, lambda: self._append("alert", msg))
            self.root.after(0, lambda: self._set_orb("alert"))
            self.ai.speak(f"Reminder. {title} starts in {minutes} minutes.")
            try:
                from plyer import notification as _notif
                _notif.notify(
                    title=f"BLAZE — Meeting in {minutes} min",
                    message=title,
                    timeout=10
                )
            except Exception:
                pass
            self.root.after(4000, lambda: self._set_orb("idle"))
        try:
            calendar_manager.start_notifier(_on_meeting_alert)
        except Exception as e:
            log.warning(f"Calendar notifier failed to start: {e}")

        # Start automation scheduler
        def _run_automation_actions(actions):
            for action in actions:
                self.root.after(0, lambda a=action: self._quick(a))
        automation.start_scheduler(_run_automation_actions)

        # Start always-on wake word listener (like Alexa)
        if voice_available:
            # Wire orb to voice state changes
            def _voice_state(state):
                orb_map = {
                    "idle":     "idle",
                    "listening":"thinking",   # purple = listening
                    "speaking": "speaking",   # blue   = speaking
                }
                self.root.after(0, lambda s=orb_map.get(state, "idle"): self._set_orb(s))
                status_map = {
                    "idle":      ("ONLINE",     C.NEON_GREEN),
                    "listening": ("LISTENING",  C.NEON_PURPLE),
                    "speaking":  ("SPEAKING",   C.NEON_GREEN),
                }
                st, col = status_map.get(state, ("ONLINE", C.NEON_GREEN))
                self.root.after(0, lambda: self._set_status(st, col))
            voice_engine.set_state_callback(_voice_state)

            # Acknowledgement — spoken + displayed when wake word heard alone
            import datetime as _dt
            def _ack():
                hour     = _dt.datetime.now().hour
                greeting = "Good morning" if hour < 12 else ("Good afternoon" if hour < 17 else "Good evening")
                ack_text = f"Yes sir, {greeting}. How can I help you?"
                self.root.after(0, lambda: self._set_orb("speaking"))
                self.root.after(0, lambda: self._append("blaze", ack_text))
                self.root.after(0, lambda: self._set_status("LISTENING", C.NEON_GREEN))
                self.ai.speak(ack_text)

            voice_engine.set_ack_callback(_ack)
            voice_engine.start_hotword_loop(self._on_wake_word)
