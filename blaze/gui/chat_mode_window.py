"""
chat_mode_window.py — the normal, bordered, resizable window for chatbot
mode. This is deliberately a plain QMainWindow (title bar, taskbar entry,
resizable) — the opposite of talk_mode_window.py on purpose, since chat
mode is meant to feel like a normal app window, not a floating overlay.
"""

from __future__ import annotations
from PySide6.QtWidgets import QMainWindow

from blaze.gui.chat_window import ChatWindow


class ChatModeWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("B.L.A.Z.E")
        self.resize(420, 560)
        self.chat = ChatWindow()
        self.setCentralWidget(self.chat)

    def closeEvent(self, event):
        # ChatWindow is a central *widget*, not a top-level window, so its
        # own closeEvent() never fires here — this QMainWindow is the one
        # that actually receives the real close event. Forward it so the
        # phone mirror's background polling thread stops instead of
        # continuing to hit adb after the window's gone.
        self.chat.closeEvent(event)
        super().closeEvent(event)


def _demo():
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    win = ChatModeWindow()
    win.chat.add_message("Chat mode window, standalone test.", sender="assistant")
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    _demo()
