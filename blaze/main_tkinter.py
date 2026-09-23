"""
B.L.A.Z.E — tkinter GUI entry point (the original interface).

This is exactly what blaze/main.py used to do before this session switched
the default to the new PySide6 UI. Kept as a real fallback: run
`python -m blaze.main_tkinter` any time you want the old interface back.
"""

import sys
import tkinter as tk
from blaze.gui.app import BlazeGUI

if __name__ == "__main__":
    root = tk.Tk()
    app = BlazeGUI(root)

    def _on_close():
        """Fully shut down BLAZE — stops all threads, subprocesses, and audio."""
        try:
            from blaze.ai.voice import voice_engine
            voice_engine.stop_hotword_loop()
        except Exception:
            pass
        try:
            app.ai.voice_enabled = False
            app.ai.tts_queue.put(None)
        except Exception:
            pass
        try:
            if hasattr(app.ai, "_tts_proc") and app.ai._tts_proc:
                app.ai._tts_proc.terminate()
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
        try:
            root.destroy()
        except Exception:
            pass
        sys.exit(0)

    root.protocol("WM_DELETE_WINDOW", _on_close)
    root.mainloop()
