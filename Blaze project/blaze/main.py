"""
B.L.A.Z.E — Entry Point
Run this file to launch the assistant.
"""

import tkinter as tk
from blaze.gui.app import BlazeGUI

if __name__ == "__main__":
    root = tk.Tk()
    app  = BlazeGUI(root)
    root.mainloop()
