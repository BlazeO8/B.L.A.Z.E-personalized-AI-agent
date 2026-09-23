"""
B.L.A.Z.E — Entry Point
Run this file to launch the assistant: py -3.11 -m blaze.main

This now launches the new PySide6 UI (blaze.gui.app_shell.BlazeController)
instead of the original tkinter GUI. The old tkinter app is fully intact
and still runnable — use `python -m blaze.main_tkinter` for that.
"""

import sys
from PySide6.QtWidgets import QApplication

from blaze.gui.app_shell import BlazeController


def _cleanup(controller: BlazeController):
    """Same shutdown sequence as the old tkinter app's _on_close — stops
    the hotword loop, TTS thread/subprocess, and background schedulers so
    nothing is left running after the window closes."""
    try:
        from blaze.ai.voice import voice_engine
        voice_engine.stop_hotword_loop()
    except Exception:
        pass
    try:
        controller.ai.voice_enabled = False
        controller.ai.tts_queue.put(None)
    except Exception:
        pass
    try:
        if hasattr(controller.ai, "_tts_proc") and controller.ai._tts_proc:
            controller.ai._tts_proc.terminate()
    except Exception:
        pass
    try:
        from blaze.intelligence.automations import automation
        automation._scheduler_active = False
    except Exception:
        pass
    try:
        from blaze.services.calendar import calendar_manager
        calendar_manager._scheduler_active = False
    except Exception:
        pass


if __name__ == "__main__":
    app = QApplication(sys.argv)
    controller = BlazeController()
    app.aboutToQuit.connect(lambda: _cleanup(controller))
    sys.exit(app.exec())
