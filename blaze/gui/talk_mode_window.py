"""
talk_mode_window.py — the actual floating orb window.

This is a separate top-level window (not a page inside a bigger window),
frameless and translucent, so only the orb's drawn shapes are visible —
no rectangle, no title bar, no taskbar-window chrome around it. It's
always-on-top and remembers where you last dragged it.

Honest limits, so they don't surprise you later:
- "Always on top" via Qt.WindowStaysOnTopHint keeps it above normal
  windows, but exclusive-fullscreen apps/games (the kind that bypass the
  normal Windows compositor) can still cover it. There's no portable fix
  for that short of a lower-level Windows API hook — flagging it now so
  it's not a "bug report" later.
- No edge-snapping, no multi-monitor-aware positioning beyond "wherever
  you last dragged it, clamped so it can't end up fully off-screen." Both
  are addable later if you want them.
- Right-click gives you a "Quit BLAZE" option since there's no title bar
  close button — without that, a frameless window with a crashed hotword
  listener has no way to close itself.
"""

from __future__ import annotations
import json
from pathlib import Path

from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QWidget, QVBoxLayout, QMenu, QApplication

from blaze.gui.orb_widget import BlazeOrb

STATE_FILE = Path.home() / ".blaze" / "orb_position.json"
ORB_SIZE = (340, 400)


class TalkModeWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool  # keeps it off the taskbar/alt-tab list, like Cortana's orb was
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(*ORB_SIZE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.orb = BlazeOrb(floating=True)
        layout.addWidget(self.orb)

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        self._restore_position()

    # --- position persistence --------------------------------------------

    def _restore_position(self):
        try:
            data = json.loads(STATE_FILE.read_text())
            pos = QPoint(data["x"], data["y"])
            if self._on_some_screen(pos):
                self.move(pos)
                return
        except Exception:
            pass
        self._move_to_default_corner()

    def _move_to_default_corner(self):
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.right() - ORB_SIZE[0] - 24
        y = screen.bottom() - ORB_SIZE[1] - 24
        self.move(x, y)

    def _on_some_screen(self, pos: QPoint) -> bool:
        for screen in QApplication.screens():
            if screen.availableGeometry().contains(pos):
                return True
        return False

    def _save_position(self):
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(json.dumps({"x": self.x(), "y": self.y()}))
        except Exception:
            pass  # position memory is a nicety, not worth crashing over

    def moveEvent(self, event):
        self._save_position()
        super().moveEvent(event)

    def closeEvent(self, event):
        self._save_position()
        super().closeEvent(event)

    # --- context menu ---------------------------------------------------

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        quit_action = menu.addAction("Quit BLAZE")
        chosen = menu.exec(self.mapToGlobal(pos))
        if chosen == quit_action:
            QApplication.instance().quit()


def _demo():
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    win = TalkModeWindow()
    win.show()

    # cycle states every 3s just so you can see it live without wiring
    # anything else up
    from PySide6.QtCore import QTimer
    states = ["idle", "listening", "speaking", "danger"]
    idx = {"i": 0}

    def cycle():
        win.orb.set_state(states[idx["i"] % len(states)])
        idx["i"] += 1

    t = QTimer()
    t.timeout.connect(cycle)
    t.start(3000)

    sys.exit(app.exec())


if __name__ == "__main__":
    _demo()
