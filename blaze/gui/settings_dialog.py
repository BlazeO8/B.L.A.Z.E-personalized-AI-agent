"""
settings_dialog.py — full settings dialog, ported from blaze/gui/dialogs.py's
open_settings_dialog(). Same six sections, same fields, same save-and-report
behavior (only reports "changed" for values that actually differ, only
restarts the TTS thread if voice/speed actually changed).

This is a genuine port, not a simplified stand-in — Personal Info, Voice &
TTS, BLAZE Voice (with the same Edge TTS neural voice list + Windows voice
fallback + preview button), Security (PIN), Knowledge Base (view + add
fact), and Automation Rules (view + add rule) are all here.

One thing that could NOT be tested in this sandbox: the "preview voice"
button shells out to PowerShell's System.Windows.Media.MediaPlayer to
play back a generated Edge TTS clip — that's a Windows-only code path,
identical to the original, and needs verification on your machine.
"""

from __future__ import annotations
import os
import time
import queue
import threading

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QWidget, QFrame, QRadioButton, QButtonGroup, QSlider,
    QListWidget, QTextEdit, QSizePolicy,
)

from blaze.gui.chat_window import BG, BG2, BG3, BG4, ACC, CYAN, GREEN, TXT, TXT2, MUTED, BDR, BDR2, mono
from blaze.core.database import db
from blaze.core.security import hash_pin
from blaze.ai.persona import persona
from blaze.intelligence.knowledge import knowledge
from blaze.intelligence.automations import automation

EDGE_VOICES = [
    ("Prabhat (Indian Male — Natural)", "en-IN-PrabhatNeural"),
    ("Neerja (Indian Female — Natural)", "en-IN-NeerjaNeural"),
    ("Guy (US Male — Natural)", "en-US-GuyNeural"),
    ("Jenny (US Female — Natural)", "en-US-JennyNeural"),
    ("Davis (US Male — Calm)", "en-US-DavisNeural"),
    ("Andrew (US Male — Confident)", "en-US-AndrewNeural"),
    ("Brian (US Male — Casual)", "en-US-BrianNeural"),
    ("Ryan (UK Male — Natural)", "en-GB-RyanNeural"),
    ("Sonia (UK Female — Natural)", "en-GB-SoniaNeural"),
    ("Natasha (AU Female)", "en-AU-NatashaNeural"),
    ("William (AU Male)", "en-AU-WilliamNeural"),
]


def _update_env(key: str, value: str):
    """Identical logic to dialogs.py's _update_env — update or append a key
    in .env, always UTF-8."""
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    lines = []
    found = False
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except UnicodeDecodeError:
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


# Bare `color:` stylesheets on QRadioButton can suppress the native
# indicator circle entirely on some Windows Qt installs — once you touch
# a widget's stylesheet at all, Qt can stop drawing the default indicator
# unless you explicitly style ::indicator yourself. This makes the circle
# always visible and always clickable regardless of platform defaults.
RADIO_STYLE = f"""
    QRadioButton {{ color: {TXT}; spacing: 6px; }}
    QRadioButton::indicator {{
        width: 14px; height: 14px; border-radius: 7px;
        border: 1px solid {BDR2}; background: {BG3};
    }}
    QRadioButton::indicator:checked {{
        border: 1px solid {ACC}; background: {ACC};
    }}
    QRadioButton::indicator:hover {{ border: 1px solid {CYAN}; }}
"""


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setFont(mono(9, QFont.DemiBold))
    lbl.setStyleSheet(f"color:{CYAN}; letter-spacing:1px; margin-top:14px; border-top:1px solid {BDR}; padding-top:10px;")
    return lbl


def _labeled_entry(layout: QVBoxLayout, label: str, default: str = "", password: bool = False) -> QLineEdit:
    row = QHBoxLayout()
    lbl = QLabel(label)
    lbl.setFont(mono(9))
    lbl.setFixedWidth(140)
    lbl.setStyleSheet(f"color:{TXT2};")
    entry = QLineEdit(default)
    entry.setFont(mono(9))
    if password:
        entry.setEchoMode(QLineEdit.Password)
    entry.setStyleSheet(
        f"QLineEdit {{ background:{BG3}; color:{TXT}; border:1px solid {BDR2};"
        f" border-radius:6px; padding:6px 8px; }}"
    )
    row.addWidget(lbl)
    row.addWidget(entry, stretch=1)
    layout.addLayout(row)
    return entry


class SettingsDialog(QDialog):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self._controller = controller  # BlazeController — for gui.ai and chat access
        self.setWindowTitle("B.L.A.Z.E — Settings")
        self.resize(600, 700)
        self.setMinimumWidth(560)  # radio button rows need at least this to stay clickable
        self.setStyleSheet(f"background:{BG};")
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        header = QLabel("⚙  B.L.A.Z.E  SETTINGS")
        header.setFont(mono(13, QFont.Bold))
        header.setStyleSheet(f"color:{CYAN}; padding:12px; border-bottom:2px solid {CYAN};")
        header.setAlignment(Qt.AlignCenter)
        outer.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ background:{BG}; border:none; }}")
        content = QWidget()
        content.setStyleSheet(f"background:{BG};")
        col = QVBoxLayout(content)
        col.setContentsMargins(16, 8, 16, 8)
        col.setSpacing(6)

        # --- Personal Info ---------------------------------------------
        col.addWidget(_section_label("Personal Info"))
        self._name_e = _labeled_entry(col, "Your name:", db.get_pref("user_name", "sir"))
        self._city_e = _labeled_entry(col, "City:", db.get_pref("BLAZE_CITY", ""))
        self._wthr_e = _labeled_entry(col, "Weather key:", db.get_pref("WEATHER_API_KEY", ""))
        self._news_e = _labeled_entry(col, "News key:", db.get_pref("NEWS_API_KEY", ""))
        self._sp_id_e = _labeled_entry(col, "Spotify ID:", db.get_pref("SPOTIFY_CLIENT_ID", ""))
        self._sp_sec_e = _labeled_entry(col, "Spotify Secret:", db.get_pref("SPOTIFY_CLIENT_SECRET", ""), password=True)
        self._groq_e = _labeled_entry(col, "GROQ API key:", db.get_pref("GROQ_API_KEY", ""), password=True)

        # --- Voice & TTS --------------------------------------------------
        col.addWidget(_section_label("Voice & TTS"))

        tone_lbl = QLabel("Tone:")
        tone_lbl.setFont(mono(9)); tone_lbl.setStyleSheet(f"color:{TXT2}; margin-top:4px;")
        col.addWidget(tone_lbl)
        tone_grid = QHBoxLayout()
        tone_grid.setSpacing(4)
        self._tone_group = QButtonGroup(self)
        for t in ("professional", "casual", "minimal", "og"):
            rb = QRadioButton(t)
            rb.setFont(mono(9)); rb.setStyleSheet(RADIO_STYLE)
            rb.setMinimumWidth(0)  # don't let Qt reserve extra width that starves later buttons
            if t == persona.tone:
                rb.setChecked(True)
            self._tone_group.addButton(rb)
            tone_grid.addWidget(rb)
        col.addLayout(tone_grid)

        verb_lbl = QLabel("Verbosity:")
        verb_lbl.setFont(mono(9)); verb_lbl.setStyleSheet(f"color:{TXT2}; margin-top:6px;")
        col.addWidget(verb_lbl)
        verb_grid = QHBoxLayout()
        verb_grid.setSpacing(4)
        self._verb_group = QButtonGroup(self)
        for v in ("brief", "normal", "detailed"):
            rb = QRadioButton(v)
            rb.setFont(mono(9)); rb.setStyleSheet(RADIO_STYLE)
            rb.setMinimumWidth(0)
            if v == persona.verbosity:
                rb.setChecked(True)
            self._verb_group.addButton(rb)
            verb_grid.addWidget(rb)
        col.addLayout(verb_grid)



        speed_row = QHBoxLayout()
        speed_lbl = QLabel("Voice speed:")
        speed_lbl.setFont(mono(9)); speed_lbl.setFixedWidth(140); speed_lbl.setStyleSheet(f"color:{TXT2};")
        self._speed_slider = QSlider(Qt.Horizontal)
        self._speed_slider.setRange(80, 280)
        self._speed_slider.setValue(persona.tts_speed)
        self._speed_val_lbl = QLabel(str(persona.tts_speed))
        self._speed_val_lbl.setFont(mono(9)); self._speed_val_lbl.setStyleSheet(f"color:{CYAN};")
        self._speed_slider.valueChanged.connect(lambda v: self._speed_val_lbl.setText(str(v)))
        speed_row.addWidget(speed_lbl)
        speed_row.addWidget(self._speed_slider, stretch=1)
        speed_row.addWidget(self._speed_val_lbl)
        col.addLayout(speed_row)

        # --- BLAZE Voice ----------------------------------------------
        col.addWidget(_section_label("BLAZE Voice"))
        hint1 = QLabel("★ Top section = Neural AI voices (Edge TTS) — much more natural")
        hint1.setFont(mono(8)); hint1.setStyleSheet(f"color:{GREEN};")
        hint2 = QLabel("  Bottom section = Built-in Windows voices (robotic)")
        hint2.setFont(mono(8)); hint2.setStyleSheet(f"color:{MUTED};")
        col.addWidget(hint1)
        col.addWidget(hint2)

        try:
            win_voices = persona.get_all_voices()
        except Exception:
            win_voices = []
        self._all_voices = EDGE_VOICES + [(f"[Windows] {n}", vid) for n, vid in win_voices]

        self._voice_list = QListWidget()
        self._voice_list.setFixedHeight(140)
        self._voice_list.setStyleSheet(
            f"QListWidget {{ background:{BG3}; color:{TXT}; border:1px solid {BDR2}; border-radius:6px; }}"
            f"QListWidget::item:selected {{ background:{ACC}; }}"
        )
        self._voice_list.setFont(mono(9))
        selected_idx = 0
        for i, (name, vid) in enumerate(self._all_voices):
            self._voice_list.addItem(f"  {name}")
            if vid == persona.voice_id:
                selected_idx = i
        self._voice_list.setCurrentRow(selected_idx)
        col.addWidget(self._voice_list)

        preview_btn = QPushButton("🔊 PREVIEW VOICE")
        preview_btn.setFont(mono(9))
        preview_btn.setStyleSheet(
            f"QPushButton {{ background:{BG3}; color:{GREEN}; border:1px solid {BDR2};"
            f" border-radius:6px; padding:6px 14px; }}"
            f"QPushButton:hover {{ background:{BG4}; }}"
        )
        preview_btn.clicked.connect(self._preview_voice)
        col.addWidget(preview_btn)

        # --- Security ----------------------------------------------------
        col.addWidget(_section_label("Security"))
        self._pin_e = _labeled_entry(col, "Set PIN (lock):", "", password=True)

        # --- Knowledge Base ------------------------------------------------
        col.addWidget(_section_label("Knowledge Base"))
        self._kb_box = QTextEdit()
        self._kb_box.setReadOnly(True)
        self._kb_box.setFixedHeight(70)
        self._kb_box.setFont(mono(9))
        self._kb_box.setStyleSheet(f"background:{BG3}; color:{GREEN}; border:1px solid {BDR2}; border-radius:6px;")
        self._kb_box.setText(knowledge.list_all())
        col.addWidget(self._kb_box)

        fact_row = QHBoxLayout()
        fact_lbl = QLabel("Add fact:")
        fact_lbl.setFont(mono(9)); fact_lbl.setFixedWidth(80); fact_lbl.setStyleSheet(f"color:{TXT2};")
        self._fact_e = QLineEdit()
        self._fact_e.setFont(mono(9))
        self._fact_e.setStyleSheet(f"background:{BG3}; color:{TXT}; border:1px solid {BDR2}; border-radius:6px; padding:6px;")
        add_fact_btn = QPushButton("ADD")
        add_fact_btn.setFont(mono(9))
        add_fact_btn.setStyleSheet(f"background:{BG3}; color:{CYAN}; border:1px solid {BDR2}; border-radius:6px; padding:6px 12px;")
        add_fact_btn.clicked.connect(self._add_fact)
        fact_row.addWidget(fact_lbl)
        fact_row.addWidget(self._fact_e, stretch=1)
        fact_row.addWidget(add_fact_btn)
        col.addLayout(fact_row)

        # --- Automation Rules -----------------------------------------
        col.addWidget(_section_label("Automation Rules"))
        self._auto_box = QTextEdit()
        self._auto_box.setReadOnly(True)
        self._auto_box.setFixedHeight(70)
        self._auto_box.setFont(mono(9))
        self._auto_box.setStyleSheet(f"background:{BG3}; color:{CYAN}; border:1px solid {BDR2}; border-radius:6px;")
        self._auto_box.setText(automation.list_rules())
        col.addWidget(self._auto_box)

        self._atrig_e = _labeled_entry(col, "Trigger:")
        self._aact_e = _labeled_entry(col, "Actions:", "open chrome, open spotify")
        self._atime_e = _labeled_entry(col, "Time HH:MM:")

        add_rule_btn = QPushButton("ADD RULE")
        add_rule_btn.setFont(mono(9))
        add_rule_btn.setStyleSheet(f"background:{BG3}; color:{CYAN}; border:1px solid {BDR2}; border-radius:6px; padding:6px 14px;")
        add_rule_btn.clicked.connect(self._add_rule)
        col.addWidget(add_rule_btn, alignment=Qt.AlignCenter)

        # --- Save ----------------------------------------------------------
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background:{BDR}; margin-top:10px;")
        col.addWidget(divider)

        save_btn = QPushButton("✓  SAVE ALL SETTINGS")
        save_btn.setFont(mono(10, QFont.DemiBold))
        save_btn.setStyleSheet(
            f"QPushButton {{ background:{CYAN}; color:{BG}; border:none;"
            f" border-radius:8px; padding:10px 24px; }}"
            f"QPushButton:hover {{ background:{GREEN}; }}"
        )
        save_btn.clicked.connect(self._save)
        col.addWidget(save_btn, alignment=Qt.AlignCenter)
        col.addSpacing(16)

        scroll.setWidget(content)
        outer.addWidget(scroll)

    # --- actions -----------------------------------------------------------

    def _add_fact(self):
        fact = self._fact_e.text().strip()
        if fact:
            knowledge.add_fact(fact)
            self._fact_e.clear()
            self._kb_box.setText(knowledge.list_all())
            self._controller.chat_window.chat.add_message(f"Remembered: {fact}", sender="system")

    def _add_rule(self):
        trigger = self._atrig_e.text().strip()
        actions = [a.strip() for a in self._aact_e.text().split(",")]
        time_str = self._atime_e.text().strip() or None
        if trigger and actions:
            automation.add_rule(trigger, trigger, actions, time_str)
            self._controller.chat_window.chat.add_message(f"Automation '{trigger}' saved.", sender="system")
            self._atrig_e.clear(); self._aact_e.clear(); self._atime_e.clear()
            self._auto_box.setText(automation.list_rules())

    def _preview_voice(self):
        row = self._voice_list.currentRow()
        if row < 0:
            return
        vid = self._all_voices[row][1]
        speed = self._speed_slider.value()

        def _preview():
            try:
                if vid.endswith("Neural"):
                    import tempfile, subprocess, asyncio
                    import edge_tts
                    tmp = tempfile.mktemp(suffix=".mp3")

                    async def _gen():
                        comm = edge_tts.Communicate(
                            "Hello sir, I am Blaze, your personal AI assistant. How can I help you today?",
                            vid,
                        )
                        await comm.save(tmp)

                    last_err = None
                    for _attempt in range(2):
                        try:
                            asyncio.run(_gen())
                            if os.path.exists(tmp) and os.path.getsize(tmp) > 1000:
                                last_err = None
                                break
                            last_err = "generated file was empty or too small"
                        except Exception as e:
                            last_err = str(e)
                        time.sleep(0.5)

                    if last_err:
                        self._controller.chat_window.chat.add_message(
                            f"Preview failed: {last_err}. Try again or pick another voice.", sender="system"
                        )
                        return

                    time.sleep(0.3)
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
                        capture_output=True, text=True, timeout=15,
                    )
                    if proc.returncode != 0 and proc.stderr.strip():
                        self._controller.chat_window.chat.add_message(
                            f"Playback error: {proc.stderr.strip()[:150]}", sender="system"
                        )
                    try:
                        os.remove(tmp)
                    except Exception:
                        pass
                else:
                    import pyttsx3
                    eng = pyttsx3.init()
                    eng.setProperty("voice", vid)
                    eng.setProperty("rate", speed)
                    eng.say("Hello sir, I am Blaze, your personal AI assistant.")
                    eng.runAndWait()
            except ImportError:
                self._controller.chat_window.chat.add_message(
                    "Run: pip install edge-tts", sender="system"
                )
            except Exception as e:
                self._controller.chat_window.chat.add_message(f"Preview error: {e}", sender="system")

        threading.Thread(target=_preview, daemon=True).start()

    def _save(self):
        changes = []

        name = self._name_e.text().strip() or "sir"
        if name != persona.name:
            changes.append("name")
        db.set_pref("user_name", name)
        persona.name = name

        field_map = [
            (self._city_e, "BLAZE_CITY", "city"),
            (self._wthr_e, "WEATHER_API_KEY", "weather key"),
            (self._news_e, "NEWS_API_KEY", "news key"),
            (self._sp_id_e, "SPOTIFY_CLIENT_ID", "Spotify ID"),
            (self._sp_sec_e, "SPOTIFY_CLIENT_SECRET", "Spotify secret"),
            (self._groq_e, "GROQ_API_KEY", "GROQ key"),
        ]
        for entry, key, label in field_map:
            val = entry.text().strip()
            if val and val != db.get_pref(key, ""):
                changes.append(label)
                db.set_pref(key, val)
                _update_env(key, val)

        new_tone = self._tone_group.checkedButton().text() if self._tone_group.checkedButton() else persona.tone
        new_verb = self._verb_group.checkedButton().text() if self._verb_group.checkedButton() else persona.verbosity
        new_speed = self._speed_slider.value()

        if new_tone != persona.tone:
            changes.append("tone")
        if new_verb != persona.verbosity:
            changes.append("verbosity")
        if new_speed != persona.tts_speed:
            changes.append("voice speed")

        persona.tone = new_tone
        persona.verbosity = new_verb
        persona.tts_speed = new_speed

        voice_changed = False
        row = self._voice_list.currentRow()
        if row >= 0:
            new_voice = self._all_voices[row][1]
            if new_voice != persona.voice_id:
                voice_changed = True
                changes.append("voice")
            persona.voice_id = new_voice

        persona.save()

        pin = self._pin_e.text().strip()
        if pin:
            db.set_pref("pin_hash", hash_pin(pin))
            changes.append("PIN")

        ai = self._controller.ai
        if voice_changed or "voice speed" in changes:
            try:
                ai.tts_queue.put(None)
                time.sleep(0.3)
                ai.tts_queue = queue.Queue()
                ai.tts_engine = None
                ai._start_tts_thread()
                time.sleep(0.8)
            except Exception:
                pass

        chat = self._controller.chat_window.chat
        if not changes:
            chat.add_message("No changes detected, sir.", sender="system")
        else:
            chat.add_message(f"Settings saved, sir. Updated: {', '.join(changes)}.", sender="system")
            if voice_changed:
                threading.Thread(target=ai.speak, args=("Settings saved. I am now using the new voice, sir.",), daemon=True).start()
            else:
                threading.Thread(target=ai.speak, args=("Settings saved, sir.",), daemon=True).start()

        self.close()
