"""
chat_window.py — "chatbot mode", rebuilt to match your actual blaze_ui.html
palette and panel layout (left: clock/vitals/weather/quick actions, right:
model/capabilities/session, chip bar + input at bottom) but with clean
rounded message bubbles instead of a raw terminal-log dump — the "mixture
of the two references" you asked for.

Colors below are lifted directly from blaze_ui.html's :root block, not
guessed, so this should actually feel like the same product as your web
dashboard rather than a new skin.

Fonts: your web UI uses 'JetBrains Mono' (mono() below) and 'Syne' (sans()
below). If those aren't installed as system fonts on your machine, Qt
silently substitutes a default and the letterforms will look a little
different than your browser — install them if you want an exact match.

Batch 1 feature port from blaze/gui/app.py (this session): thinking
animation, cancel button, command history (up/down arrow), mic
push-to-talk, and thumbs up/down feedback. Ported to match the original's
exact behavior, not reimagined — see app_shell.py for how the controller
drives these (this widget only emits signals/exposes state methods, it
doesn't own the AI/voice logic itself, same separation as before).

Public API additions this session: cancel_requested, mic_requested,
feedback_given signals; show_thinking()/hide_thinking(), set_cancel_enabled(),
set_mic_listening() methods.
"""

from __future__ import annotations
from collections import deque
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QTimer, QEvent
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QFrame, QSizePolicy, QSpacerItem, QProgressBar, QFileDialog,
)

from blaze.services import hw_stats
from blaze.core.database import db
from blaze.gui.phone_mirror import PhoneMirrorPanel

# --- exact palette from blaze_ui.html :root --------------------------------
BG = "#0a0a0f"
BG2 = "#0f0f1a"
BG3 = "#141422"
BG4 = "#1c1c30"
ACC = "#7c6af7"
ACC2 = "#5b4de0"
GLOW = "#a78bfa"
CYAN = "#22d3ee"
GREEN = "#4ade80"
AMBER = "#fbbf24"
RED = "#f87171"
PINK = "#f472b6"
TXT = "#e2e8f0"
TXT2 = "#94a3b8"
MUTED = "#334155"
BDR = "#1e1e35"
BDR2 = "#2a2a48"


def mono(size=10, weight=QFont.Normal):
    f = QFont("JetBrains Mono", size)
    f.setStyleHint(QFont.Monospace)
    f.setWeight(weight)
    return f


def sans(size=13, weight=QFont.Normal):
    f = QFont("Syne", size)
    f.setWeight(weight)
    return f


CHIPS = [
    ("TIME", "What time is it?"),
    ("DATE", "What's today's date?"),
    ("WEATHER", "What's the weather?"),
    ("JOKE", "Tell me a joke"),
    ("GITHUB", "Show me GitHub trending repos"),
    ("HELP", "What can you do?"),
    ("CLEAR", "__clear__"),
]

CAPABILITIES = [
    ("NLP Engine", CYAN),
    ("Voice I/O", GREEN),
    ("Pattern Learner", ACC),
    ("Secure Vault", AMBER),
    ("File Manager", TXT2),
    ("Emotional IQ", PINK),
]


class _Bubble(QLabel):
    def __init__(self, text: str, is_user: bool):
        super().__init__(text)
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)
        if is_user:
            bg, border = f"{ACC}26", ACC
        else:
            bg, border = BG3, BDR2
        self.setStyleSheet(
            f"QLabel {{ background:{bg}; color:{TXT}; border-radius:10px;"
            f" padding:9px 13px; border:1px solid {border}; }}"
        )
        self.setMaximumWidth(440)
        self.setFont(mono(10))


class _SystemLine(QLabel):
    """Plain terminal-log style line for boot messages / system notices —
    no bubble, matches the original app's '// SYSTEM' log aesthetic rather
    than looking like something BLAZE 'said'."""

    def __init__(self, text: str):
        super().__init__(f"▸ {text}")
        self.setWordWrap(True)
        self.setFont(mono(9))
        self.setStyleSheet(f"color:{TXT2}; padding:2px 4px;")


class _HistoryLineEdit(QLineEdit):
    """Up/down arrow recalls previous submissions, same as the original
    tkinter app's _history_up. History is newest-first, same as its
    deque(maxlen=...) with appendleft()."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._history: deque[str] = deque(maxlen=50)
        self._history_idx = -1

    def remember(self, text: str):
        self._history.appendleft(text)
        self._history_idx = -1

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Up and self._history:
            self._history_idx = min(self._history_idx + 1, len(self._history) - 1)
            self.setText(self._history[self._history_idx])
            return
        if event.key() == Qt.Key_Down and self._history:
            self._history_idx = max(self._history_idx - 1, -1)
            self.setText(self._history[self._history_idx] if self._history_idx >= 0 else "")
            return
        super().keyPressEvent(event)


class ChatWindow(QWidget):
    switch_to_talk_mode = Signal()
    message_submitted = Signal(str)
    cancel_requested = Signal()
    mic_requested = Signal()
    feedback_given = Signal(int)
    settings_requested = Signal()
    unlock_attempted = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{BG};")
        self._build_ui()

        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

        self._vitals_timer = QTimer(self)
        self._vitals_timer.timeout.connect(self._update_vitals)
        self._vitals_timer.start(1000)

    # --- UI construction --------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_titlebar())

        body = QHBoxLayout()
        body.setSpacing(0)
        body.addWidget(self._build_left_panel())
        body.addLayout(self._build_center(), stretch=1)
        body.addWidget(self._build_right_panel())
        root.addLayout(body, stretch=1)

        root.addWidget(self._build_footer())

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text.upper())
        lbl.setFont(mono(8, QFont.DemiBold))
        lbl.setStyleSheet(f"color:{TXT2}; letter-spacing:1px; margin-top:10px;")
        return lbl

    def _build_titlebar(self) -> QWidget:
        bar = QFrame()
        bar.setStyleSheet(f"background:{BG2}; border-bottom:1px solid {BDR};")
        bar.setFixedHeight(52)
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 0, 12, 0)
        row.setSpacing(10)

        logo = QLabel("◆")
        logo.setStyleSheet(f"color:{CYAN}; font-size:16px;")
        row.addWidget(logo)

        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        title = QLabel("B . L . A . Z . E")
        title.setFont(sans(14, QFont.Bold))
        title.setStyleSheet(f"color:{TXT};")
        subtitle = QLabel("BRILLIANTLY LINKED AUTONOMOUS ZONE ENGINE · PERSONAL AI SYSTEM")
        subtitle.setFont(mono(7))
        subtitle.setStyleSheet(f"color:{MUTED}; letter-spacing:1px;")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        row.addLayout(title_col)

        row.addItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))

        settings_btn = QPushButton("⚙ SETTINGS")
        settings_btn.setFont(mono(9))
        settings_btn.setStyleSheet(
            f"QPushButton {{ background:{BG3}; color:{TXT2}; border:1px solid {BDR2};"
            f" border-radius:6px; padding:6px 10px; }}"
            f"QPushButton:hover {{ background:{BG4}; }}"
        )
        settings_btn.clicked.connect(self.settings_requested.emit)
        row.addWidget(settings_btn)

        thumbs_up = QPushButton("👍")
        thumbs_up.setToolTip("Rate the last response highly")
        thumbs_up.setFixedSize(28, 28)
        thumbs_up.setStyleSheet(
            f"QPushButton {{ background:{BG3}; border:1px solid {BDR2}; border-radius:6px; }}"
            f"QPushButton:hover {{ background:{GREEN}22; }}"
        )
        thumbs_up.clicked.connect(lambda: self.feedback_given.emit(5))
        row.addWidget(thumbs_up)

        thumbs_down = QPushButton("👎")
        thumbs_down.setToolTip("Rate the last response poorly")
        thumbs_down.setFixedSize(28, 28)
        thumbs_down.setStyleSheet(
            f"QPushButton {{ background:{BG3}; border:1px solid {BDR2}; border-radius:6px; }}"
            f"QPushButton:hover {{ background:{RED}22; }}"
        )
        thumbs_down.clicked.connect(lambda: self.feedback_given.emit(1))
        row.addWidget(thumbs_down)

        voice_btn = QPushButton("🎙 VOICE")
        voice_btn.setFont(mono(9))
        voice_btn.setStyleSheet(
            f"QPushButton {{ background:{BG3}; color:{CYAN}; border:1px solid {BDR2};"
            f" border-radius:6px; padding:6px 12px; }}"
            f"QPushButton:hover {{ background:{BG4}; }}"
        )
        voice_btn.setToolTip("Switch to talk mode")
        voice_btn.clicked.connect(self.switch_to_talk_mode.emit)
        row.addWidget(voice_btn)

        status = QLabel("●  ONLINE")
        status.setFont(mono(9))
        status.setStyleSheet(f"color:{GREEN};")
        row.addWidget(status)
        return bar

    def _build_left_panel(self) -> QWidget:
        outer = QScrollArea()
        outer.setFixedWidth(230)
        outer.setWidgetResizable(True)
        outer.setStyleSheet(
            f"QScrollArea {{ background:{BG2}; border:none; border-right:1px solid {BDR}; }}"
        )
        panel = QFrame()
        panel.setStyleSheet(f"background:{BG2};")
        col = QVBoxLayout(panel)
        col.setContentsMargins(14, 10, 14, 10)
        col.setAlignment(Qt.AlignTop)

        col.addWidget(self._section_label("Clock"))
        self._clock_lbl = QLabel("--:--:--")
        self._clock_lbl.setFont(mono(20, QFont.Bold))
        self._clock_lbl.setStyleSheet(f"color:{CYAN};")
        self._date_lbl = QLabel("---")
        self._date_lbl.setFont(mono(8))
        self._date_lbl.setStyleSheet(f"color:{TXT2};")
        col.addWidget(self._clock_lbl)
        col.addWidget(self._date_lbl)

        col.addWidget(self._section_label("System Vitals"))
        self._cpu_bar, self._cpu_val = self._vital_row(col, "CPU", CYAN)
        self._ram_bar, self._ram_val = self._vital_row(col, "RAM", ACC)
        self._disk_bar, self._disk_val = self._vital_row(col, "DISK", AMBER)
        self._battery_lbl = QLabel("Battery: --")
        self._battery_lbl.setFont(mono(8))
        self._battery_lbl.setStyleSheet(f"color:{TXT2}; margin-top:4px;")
        col.addWidget(self._battery_lbl)

        col.addWidget(self._section_label("Weather"))
        self._weather_lbl = QLabel("Fetching...")
        self._weather_lbl.setFont(mono(8))
        self._weather_lbl.setStyleSheet(f"color:{TXT2};")
        self._weather_lbl.setWordWrap(True)
        col.addWidget(self._weather_lbl)

        col.addWidget(self._section_label("Reminders"))
        self._reminders_lbl = QLabel("None")
        self._reminders_lbl.setFont(mono(8))
        self._reminders_lbl.setStyleSheet(f"color:{TXT2};")
        self._reminders_lbl.setWordWrap(True)
        col.addWidget(self._reminders_lbl)

        col.addWidget(self._section_label("Phone Mirror"))
        self._phone_mirror = PhoneMirrorPanel()
        col.addWidget(self._phone_mirror)

        col.addStretch()
        outer.setWidget(panel)
        return outer

    def _vital_row(self, col: QVBoxLayout, label: str, color: str):
        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setFont(mono(8))
        lbl.setFixedWidth(30)
        lbl.setStyleSheet(f"color:{TXT2};")
        bar = QProgressBar()
        bar.setFixedHeight(6)
        bar.setTextVisible(False)
        bar.setRange(0, 100)
        bar.setStyleSheet(
            f"QProgressBar {{ background:{BG4}; border:none; border-radius:3px; }}"
            f"QProgressBar::chunk {{ background:{color}; border-radius:3px; }}"
        )
        val = QLabel("0%")
        val.setFont(mono(8))
        val.setFixedWidth(32)
        val.setStyleSheet(f"color:{color};")
        row.addWidget(lbl)
        row.addWidget(bar, stretch=1)
        row.addWidget(val)
        col.addLayout(row)
        return bar, val

    def _build_center(self) -> QVBoxLayout:
        center = QVBoxLayout()
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(0)

        chip_bar = QFrame()
        chip_bar.setStyleSheet(f"background:{BG}; border-bottom:1px solid {BDR};")
        chip_row = QHBoxLayout(chip_bar)
        chip_row.setContentsMargins(12, 8, 12, 8)
        for label, phrase in CHIPS:
            chip = QPushButton(label)
            chip.setFont(mono(8, QFont.DemiBold))
            chip.setStyleSheet(
                f"QPushButton {{ background:{BG3}; color:{TXT2}; border:1px solid {BDR2};"
                f" border-radius:12px; padding:5px 12px; }}"
                f"QPushButton:hover {{ background:{BG4}; color:{TXT}; }}"
            )
            chip.clicked.connect(lambda checked=False, p=phrase: self._on_chip(p))
            chip_row.addWidget(chip)
        chip_row.addItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))
        center.addWidget(chip_bar)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(f"QScrollArea {{ background:{BG}; border:none; }}")
        self._msg_container = QWidget()
        self._msg_container.setStyleSheet(f"background:{BG};")
        self._msg_layout = QVBoxLayout(self._msg_container)
        self._msg_layout.setAlignment(Qt.AlignTop)
        self._msg_layout.setContentsMargins(16, 12, 16, 12)
        self._msg_layout.setSpacing(8)
        self._scroll.setWidget(self._msg_container)
        center.addWidget(self._scroll, stretch=1)

        self._thinking_lbl = QLabel("")
        self._thinking_lbl.setFont(mono(9))
        self._thinking_lbl.setStyleSheet(f"color:{ACC}; padding:4px 16px; background:{BG};")
        self._thinking_lbl.setVisible(False)
        center.addWidget(self._thinking_lbl)

        center.addWidget(self._build_input_row())
        return center

    def _build_input_row(self) -> QWidget:
        wrap = QFrame()
        wrap.setStyleSheet(f"background:{BG2}; border-top:1px solid {BDR};")
        row = QHBoxLayout(wrap)
        row.setContentsMargins(12, 10, 12, 10)

        self._mic_btn = QPushButton("🎙")
        self._mic_btn.setFixedSize(34, 34)
        self._mic_btn.setToolTip("Push to talk")
        self._mic_btn.setStyleSheet(self._mic_btn_style(listening=False))
        self._mic_btn.clicked.connect(self.mic_requested.emit)
        row.addWidget(self._mic_btn)

        attach_btn = QPushButton("📎")
        attach_btn.setFixedSize(34, 34)
        attach_btn.setToolTip("Attach a file")
        attach_btn.setStyleSheet(
            f"QPushButton {{ background:{BG3}; border:1px solid {BDR2}; border-radius:17px;"
            f" color:{TXT2}; }}"
            f"QPushButton:hover {{ background:{BG4}; }}"
        )
        attach_btn.clicked.connect(self._attach_file)
        row.addWidget(attach_btn)

        self._input = _HistoryLineEdit()
        self._input.setPlaceholderText("Ask anything, sir...")
        self._input.setFont(mono(10))
        self._input.setStyleSheet(
            f"QLineEdit {{ background:{BG3}; color:{TXT}; border:1px solid {BDR2};"
            f" border-radius:8px; padding:9px 12px; }}"
            f"QLineEdit:focus {{ border-color:{ACC}; }}"
        )
        self._input.returnPressed.connect(self._on_submit)
        row.addWidget(self._input, stretch=1)

        self._cancel_btn = QPushButton("✕")
        self._cancel_btn.setFixedSize(34, 34)
        self._cancel_btn.setToolTip("Cancel request")
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setStyleSheet(
            f"QPushButton {{ background:{BG3}; border:1px solid {BDR2}; border-radius:17px;"
            f" color:{RED}; }}"
            f"QPushButton:hover:enabled {{ background:{RED}22; }}"
            f"QPushButton:disabled {{ color:{MUTED}; }}"
        )
        self._cancel_btn.clicked.connect(self.cancel_requested.emit)
        row.addWidget(self._cancel_btn)

        send_btn = QPushButton("SEND ›")
        send_btn.setFont(mono(9, QFont.DemiBold))
        send_btn.setStyleSheet(
            f"QPushButton {{ background:{ACC}; color:white; border:none;"
            f" border-radius:8px; padding:9px 18px; }}"
            f"QPushButton:hover {{ background:{ACC2}; }}"
        )
        send_btn.clicked.connect(self._on_submit)
        row.addWidget(send_btn)
        return wrap

    def _mic_btn_style(self, listening: bool) -> str:
        color = RED if listening else TXT2
        return (
            f"QPushButton {{ background:{BG3}; border:1px solid {BDR2}; border-radius:17px;"
            f" color:{color}; }}"
            f"QPushButton:hover {{ background:{BG4}; }}"
        )

    def _build_right_panel(self) -> QWidget:
        panel = QFrame()
        panel.setFixedWidth(190)
        panel.setStyleSheet(f"background:{BG2}; border-left:1px solid {BDR};")
        col = QVBoxLayout(panel)
        col.setContentsMargins(14, 10, 14, 10)
        col.setAlignment(Qt.AlignTop)

        col.addWidget(self._section_label("Model"))
        model = QLabel("gpt-oss-120b")
        model.setFont(mono(10, QFont.DemiBold))
        model.setStyleSheet(f"color:{TXT};")
        provider = QLabel("Groq Free Inference")
        provider.setFont(mono(7))
        provider.setStyleSheet(f"color:{MUTED};")
        col.addWidget(model)
        col.addWidget(provider)

        col.addWidget(self._section_label("Capabilities"))
        for label, color in CAPABILITIES:
            item = QHBoxLayout()
            dot = QLabel("●")
            dot.setStyleSheet(f"color:{color}; font-size:8px;")
            dot.setFixedWidth(14)
            txt = QLabel(label)
            txt.setFont(mono(8))
            txt.setStyleSheet(f"color:{TXT2};")
            item.addWidget(dot)
            item.addWidget(txt)
            item.addStretch()
            col.addLayout(item)

        col.addWidget(self._section_label("Session"))
        session = QLabel("Active")
        session.setFont(mono(9))
        session.setStyleSheet(f"color:{GREEN};")
        col.addWidget(session)

        col.addStretch()
        return panel

    def _build_footer(self) -> QWidget:
        bar = QFrame()
        bar.setFixedHeight(24)
        bar.setStyleSheet(f"background:{BG2}; border-top:1px solid {BDR};")
        row = QHBoxLayout(bar)
        row.setContentsMargins(14, 0, 14, 0)
        left = QLabel("B.L.A.Z.E  ·  BY KARTIK (BLAZE08)  ·  GROQ FREE INFERENCE")
        left.setFont(mono(7))
        left.setStyleSheet(f"color:{MUTED};")
        row.addWidget(left)
        row.addItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))
        self._footer_sys = QLabel("—")
        self._footer_sys.setFont(mono(7))
        self._footer_sys.setStyleSheet(f"color:{MUTED};")
        row.addWidget(self._footer_sys)
        return bar

    def closeEvent(self, event):
        if hasattr(self, "_phone_mirror"):
            self._phone_mirror.shutdown()
        super().closeEvent(event)

    # --- public API ---------------------------------------------------

    def add_message(self, text: str, sender: str = "assistant"):
        if sender == "system":
            row = QHBoxLayout()
            row.addWidget(_SystemLine(text))
            row.addItem(QSpacerItem(40, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))
            self._msg_layout.addLayout(row)
            self._scroll_to_bottom()
            return

        is_user = sender == "user"
        row = QHBoxLayout()
        bubble = _Bubble(text, is_user)
        if is_user:
            row.addItem(QSpacerItem(40, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))
            row.addWidget(bubble)
        else:
            row.addWidget(bubble)
            row.addItem(QSpacerItem(40, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))
        self._msg_layout.addLayout(row)
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def set_weather(self, text: str):
        self._weather_lbl.setText(text)

    def set_reminders(self, text: str):
        self._reminders_lbl.setText(text)

    def clear_messages(self):
        while self._msg_layout.count():
            item = self._msg_layout.takeAt(0)
            layout = item.layout()
            if layout is not None:
                while layout.count():
                    w = layout.takeAt(0).widget()
                    if w:
                        w.deleteLater()

    # --- internal ---------------------------------------------------------

    def _on_submit(self):
        text = self._input.text().strip()
        if not text:
            return
        if self.is_locked():
            self.unlock_attempted.emit(text)
            self._input.clear()
            return
        self._input.remember(text)
        self._submit_text(text)
        self._input.clear()

    def _on_chip(self, phrase: str):
        if phrase == "__clear__":
            self.clear_messages()
            return
        self._submit_text(phrase)

    def _submit_text(self, text: str):
        self.add_message(text, sender="user")
        self.message_submitted.emit(text)

    # --- Batch 1 feature methods (driven by app_shell.py) ------------------

    def show_thinking(self):
        self._thinking_dots = 0
        self._thinking_lbl.setVisible(True)
        self._thinking_lbl.setText("// BLAZE  ●○○  processing...")
        self._thinking_timer = QTimer(self)
        self._thinking_timer.timeout.connect(self._animate_thinking)
        self._thinking_timer.start(350)

    def _animate_thinking(self):
        self._thinking_dots = (self._thinking_dots + 1) % 4
        dots = "●" * self._thinking_dots + "○" * (3 - self._thinking_dots)
        self._thinking_lbl.setText(f"// BLAZE  {dots}  processing...")

    def hide_thinking(self):
        if hasattr(self, "_thinking_timer"):
            self._thinking_timer.stop()
        self._thinking_lbl.setVisible(False)

    def set_cancel_enabled(self, enabled: bool):
        self._cancel_btn.setEnabled(enabled)

    def set_mic_listening(self, listening: bool):
        self._mic_btn.setStyleSheet(self._mic_btn_style(listening))

    def _attach_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Attach file to BLAZE", "", "Text files (*.txt);;Markdown (*.md);;All files (*.*)"
        )
        if not path:
            return
        try:
            content = Path(path).read_text(encoding="utf-8", errors="ignore")[:2000]
            fname = Path(path).name
            prompt = f"I'm sharing this file with you: '{fname}'\n\nContent:\n{content}\n\nPlease summarize or help me with this."
            self._input.setText(prompt)
            self.add_message(f"File attached: {fname}", sender="system")
        except Exception as e:
            self.add_message(f"Could not read file: {e}", sender="system")

    # --- session lock (ported from app.py's _lock_session) -----------------
    # PIN verification itself lives in app_shell.py (has db/security access,
    # same separation as everywhere else in this codebase) — this widget
    # only tracks whether it's locked and redirects Enter-key submissions
    # to unlock_attempted instead of message_submitted while locked.

    def lock_session(self):
        self._locked = True
        self.add_message("Session locked due to inactivity. Enter PIN to continue.", sender="system")
        self._input.clear()

    def unlock(self):
        self._locked = False
        self._input.clear()
        self.add_message("Session unlocked.", sender="system")

    def is_locked(self) -> bool:
        return getattr(self, "_locked", False)

    def _update_clock(self):
        from datetime import datetime
        now = datetime.now()
        self._clock_lbl.setText(now.strftime("%H:%M:%S"))
        self._date_lbl.setText(now.strftime("%A, %b %d %Y"))

    def _update_vitals(self):
        snap = hw_stats.snapshot()
        cpu = snap["cpu_pct"]
        self._cpu_bar.setValue(int(cpu))
        self._cpu_val.setText(f"{cpu:.0f}%")
        try:
            import psutil
            ram = psutil.virtual_memory().percent
            disk = psutil.disk_usage("/").percent
            self._ram_bar.setValue(int(ram))
            self._ram_val.setText(f"{ram:.0f}%")
            self._disk_bar.setValue(int(disk))
            self._disk_val.setText(f"{disk:.0f}%")
            batt = psutil.sensors_battery()
            if batt:
                self._battery_lbl.setText(f"Battery: {batt.percent:.0f}%{' ⚡' if batt.power_plugged else ''}")
            self._footer_sys.setText(f"CPU {cpu:.0f}% · RAM {ram:.0f}% · Disk {disk:.0f}%")
        except Exception:
            pass

        try:
            rows = db.get_all_reminders()
            if rows:
                text = "\n".join(f"• {m[:26]} @ {f[11:16]}" for _, m, f in rows[:3])
            else:
                text = "None"
            self._reminders_lbl.setText(text)
        except Exception:
            pass


def _demo():
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    win = ChatWindow()
    win.resize(1000, 640)
    win.setWindowTitle("BLAZE — chatbot mode preview")

    win.add_message("Good evening, owner. I am B.L.A.Z.E. How may I assist you today?", sender="assistant")
    win.add_message("what's on my calendar today, sir?", sender="user")
    win.add_message("Two meetings, sir. Standup at 10, review at 3.", sender="assistant")

    def echo(text):
        win.add_message(f"(demo echo) you said: {text}", sender="assistant")

    win.message_submitted.connect(echo)
    win.switch_to_talk_mode.connect(lambda: print("[demo] would switch to talk mode here"))

    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    _demo()
