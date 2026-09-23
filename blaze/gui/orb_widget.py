"""
orb_widget.py — the "talk mode" floating HUD orb.

Draws everything with QPainter in one paintEvent: the two rotating rings,
the glowing core, the ripple pulses (speaking state), the "BLAZE" wordmark,
and two corner mini-graphs for CPU and GPU (usage % as a smoothed scrolling
line, temperature as text next to it).

States: "idle" (blue), "listening" (purple), "speaking" (orange, core does
a heartbeat-style beat pulse + expanding ripples), "danger" (red, whole
widget flickers). Danger should only be entered from idle — that priority
decision belongs to whatever drives set_state() (see demo main() below),
not to this widget.

This widget does NOT poll hardware itself. Call push_cpu()/push_gpu() from
outside (e.g. a QTimer tied to blaze.services.hw_stats) at whatever rate
you're already polling at — the widget smooths between real readings on
its own animation clock, so it looks continuous even if you only feed it
one real sample per second.
"""

from __future__ import annotations
import math
from collections import deque
from dataclasses import dataclass

from PySide6.QtCore import Qt, QTimer, QRectF, Signal, QPointF
from PySide6.QtGui import QPainter, QPainterPath, QRadialGradient, QColor, QFont, QPen
from PySide6.QtWidgets import QWidget, QPushButton


@dataclass
class _StateStyle:
    ring: QColor
    core_inner: QColor
    core_outer: QColor
    ring1_period_s: float = 18.0


STYLES = {
    "idle": _StateStyle(
        ring=QColor("#2fb8d6"), core_inner=QColor("#a6f3ff"), core_outer=QColor("#2fb8d6"),
        ring1_period_s=18.0,
    ),
    "listening": _StateStyle(
        ring=QColor("#a78bfa"), core_inner=QColor("#e4d9ff"), core_outer=QColor("#8b5cf6"),
        ring1_period_s=4.0,
    ),
    "speaking": _StateStyle(
        ring=QColor("#f0973a"), core_inner=QColor("#ffe3c2"), core_outer=QColor("#f0973a"),
        ring1_period_s=18.0,
    ),
    "danger": _StateStyle(
        ring=QColor("#e5484d"), core_inner=QColor("#ffd0d0"), core_outer=QColor("#e5484d"),
        ring1_period_s=18.0,
    ),
}

HISTORY_LEN = 120          # samples kept per graph (~4s at 30fps)
FRAME_MS = 33              # ~30fps animation tick
SMOOTH_FACTOR = 0.15       # how fast the displayed value chases the real one


class _MetricTrack:
    """One metric's smoothing + rolling history, e.g. CPU usage."""

    def __init__(self):
        self.target_pct: float = 0.0
        self.display_pct: float = 0.0
        self.temp_c: float | None = None
        self.history: deque[float] = deque([0.0] * HISTORY_LEN, maxlen=HISTORY_LEN)

    def push(self, pct: float, temp_c: float | None):
        self.target_pct = max(0.0, min(100.0, pct))
        self.temp_c = temp_c

    def tick(self):
        self.display_pct += (self.target_pct - self.display_pct) * SMOOTH_FACTOR
        self.history.append(self.display_pct)


class BlazeOrb(QWidget):
    """The talk-mode HUD. Emits switch_to_chat_mode when the corner button
    is clicked (wire this to your mode-switching logic)."""

    switch_to_chat_mode = Signal()

    def __init__(self, parent=None, floating: bool = False):
        """floating=True skips painting an opaque background rectangle, so
        when this widget sits inside a frameless/translucent top-level
        window (see talk_mode_window.py), the desktop shows through
        everywhere except the drawn rings/core/text/graphs — the actual
        floating-orb look. floating=False (default) fills an opaque dark
        background, which is what you want when testing this widget
        standalone or embedding it in a normal bordered window."""
        super().__init__(parent)
        self.setMinimumSize(320, 380)
        self._floating = floating
        self._state = "idle"
        self._t = 0.0
        self._danger_prev_state = "idle"  # so danger can hand control back
        self._drag_offset = None

        self.cpu = _MetricTrack()
        self.gpu = _MetricTrack()

        self._chat_btn = QPushButton("💬", self)
        self._chat_btn.setFixedSize(30, 30)
        self._chat_btn.setStyleSheet(
            "QPushButton { background: rgba(47,184,214,20); border: 1px solid #2a2d36;"
            " border-radius: 15px; color: #4fd8e8; }"
            "QPushButton:hover { background: rgba(47,184,214,40); }"
        )
        self._chat_btn.clicked.connect(self.switch_to_chat_mode.emit)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(FRAME_MS)

    # --- public API ---------------------------------------------------

    def set_state(self, state: str):
        if state not in STYLES:
            raise ValueError(f"unknown state {state!r}, expected one of {list(STYLES)}")
        if state == "danger":
            self._danger_prev_state = self._state if self._state != "danger" else self._danger_prev_state
        self._state = state
        self.update()

    def clear_danger(self):
        """Call when the thermal/RAM condition clears. Returns to whatever
        state was active before danger fired (normally idle, since danger
        should only be entered from idle in the first place)."""
        self._state = self._danger_prev_state
        self.update()

    def push_cpu(self, pct: float, temp_c: float | None = None):
        self.cpu.push(pct, temp_c)

    def push_gpu(self, pct: float, temp_c: float | None = None):
        self.gpu.push(pct, temp_c)

    # --- animation ------------------------------------------------------

    def _on_tick(self):
        self._t += FRAME_MS / 1000.0
        self.cpu.tick()
        self.gpu.tick()
        self.update()

    def resizeEvent(self, event):
        self._chat_btn.move(self.width() - 44, self.height() - 44)
        super().resizeEvent(event)

    # --- window dragging (only when hosted in a frameless window) --------
    # A frameless window has no title bar to grab, so this widget moves
    # its own top-level window when dragged. Guarded on FramelessWindowHint
    # so embedding this widget in a normal bordered window (e.g. the old
    # single-window demo) doesn't suddenly make clicking-and-dragging the
    # orb move the whole app window unexpectedly.

    def _window_is_frameless(self) -> bool:
        return bool(self.window().windowFlags() & Qt.FramelessWindowHint)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._window_is_frameless():
            self._drag_offset = event.globalPosition().toPoint() - self.window().pos()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    # --- painting ---------------------------------------------------------

    def paintEvent(self, event):
        style = STYLES[self._state]
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        if self._state == "danger":
            # hard flicker, not a fade — matches a "something is wrong" alarm feel
            flicker_on = int(self._t / 0.25) % 2 == 0
            p.setOpacity(1.0 if flicker_on else 0.55)

        if not self._floating:
            p.fillRect(self.rect(), QColor("#04070a"))

        cx, cy = self.width() / 2, 160
        self._draw_corner_graph(p, self.cpu, "CPU", 14, 14, style, align_right=False)
        self._draw_corner_graph(p, self.gpu, "GPU", self.width() - 14, 14, style, align_right=True)
        self._draw_orb(p, cx, cy, style)

        p.setOpacity(1.0)
        p.setPen(QPen(style.ring))
        p.setFont(QFont("Consolas", 9))
        label = self._state.upper() if self._state != "danger" else "DANGER — THERMAL"
        p.drawText(QRectF(0, cy + 100, self.width(), 20), Qt.AlignCenter, label)

    def _draw_orb(self, p: QPainter, cx: float, cy: float, style: _StateStyle):
        outer_r = 100

        # static dashed outer boundary
        p.setPen(QPen(QColor("#1c2530"), 1, Qt.DashLine))
        p.drawEllipse(QPointF(cx, cy), outer_r, outer_r)

        # ring 1 — slow/fast rotating dashed ring, speed depends on state
        angle1 = (self._t / style.ring1_period_s) * 360.0
        p.save()
        p.translate(cx, cy)
        p.rotate(angle1)
        pen = QPen(style.ring, 1.5)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(-84, -84, 168, 168), 0, 16 * 120)
        p.restore()

        # ring 2 — counter-rotating, faster
        angle2 = -(self._t / 12.0) * 360.0
        p.save()
        p.translate(cx, cy)
        p.rotate(angle2)
        p.setPen(QPen(style.ring, 1))
        p.drawArc(QRectF(-70, -70, 140, 140), 0, 16 * 30)
        p.restore()

        # ripple pulses, speaking only
        if self._state == "speaking":
            for phase_offset in (0.0, 0.55):
                phase = (self._t + phase_offset) % 1.1 / 1.1  # 0..1
                r = 50 + phase * 50
                opacity = max(0.0, 0.7 * (1 - phase))
                p.save()
                p.setOpacity(opacity)
                p.setPen(QPen(style.ring, 2))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(cx, cy), r, r)
                p.restore()

        # core radius: state-specific pulse behavior
        core_r = self._core_radius(style)

        grad = QRadialGradient(cx, cy, core_r)
        inner = QColor(style.core_inner)
        outer = QColor(style.core_outer)
        outer_transparent = QColor(outer)
        outer_transparent.setAlpha(0)
        grad.setColorAt(0.0, inner)
        grad.setColorAt(0.55, outer)
        grad.setColorAt(1.0, outer_transparent)
        p.setBrush(grad)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy), core_r, core_r)

        p.setPen(QPen(style.ring, 1))
        p.setBrush(Qt.NoBrush)
        p.setOpacity(0.8)
        p.drawEllipse(QPointF(cx, cy), core_r, core_r)
        p.setOpacity(1.0)

        p.setPen(QColor("#eafdff"))
        f = QFont("Consolas", 16)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 4)
        p.setFont(f)
        p.drawText(QRectF(cx - 100, cy - 12, 200, 24), Qt.AlignCenter, "BLAZE")

    def _core_radius(self, style: _StateStyle) -> float:
        if self._state == "idle":
            return 70 + 4 * math.sin(self._t / 2.4 * 2 * math.pi)
        if self._state == "listening":
            return 66 + 4 * math.sin(self._t / 0.9 * 2 * math.pi)
        if self._state == "speaking":
            # sharp attack, quick settle — a heartbeat, not a smooth sine
            phase = (self._t % 0.55) / 0.55
            if phase < 0.2:
                return 64 + (78 - 64) * (phase / 0.2)
            elif phase < 0.45:
                return 78 - (78 - 66) * ((phase - 0.2) / 0.25)
            else:
                return 66 - (66 - 64) * ((phase - 0.45) / 0.55)
        if self._state == "danger":
            return 70
        return 70

    def _draw_corner_graph(self, p: QPainter, metric: _MetricTrack, label: str,
                            x: float, y: float, style: _StateStyle, align_right: bool):
        w, h = 84, 24
        px = x - w if align_right else x

        p.setPen(style.ring)
        p.setFont(QFont("Consolas", 8))
        temp_str = f" · {metric.temp_c:.0f}°C" if metric.temp_c is not None else " · N/A"
        text = f"{label} {metric.display_pct:.0f}%{temp_str}"
        align = Qt.AlignRight if align_right else Qt.AlignLeft
        p.drawText(QRectF(px, y, w, 12), align, text)

        path = QPainterPath()
        pts = list(metric.history)
        n = len(pts)
        step = w / (n - 1)
        prev = None
        for i, val in enumerate(pts):
            px_pt = px + i * step
            py_pt = y + 22 - (val / 100.0) * 18  # scale 0-100% into a 18px tall band
            pt = QPointF(px_pt, py_pt)
            if prev is None:
                path.moveTo(pt)
            else:
                mid = QPointF((prev.x() + pt.x()) / 2, (prev.y() + pt.y()) / 2)
                path.quadTo(prev, mid)
            prev = pt
        p.setPen(QPen(style.ring, 1.4))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)


def _demo():
    """Standalone visual test: run `python -m blaze.gui.orb_widget` to see
    the orb live, cycle states with the buttons, and watch real CPU/GPU
    stats (where available) drive the corner graphs."""
    import sys
    from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QHBoxLayout, QPushButton
    from blaze.services import hw_stats

    app = QApplication(sys.argv)
    win = QMainWindow()
    win.setWindowTitle("BLAZE — talk mode preview")
    central = QWidget()
    layout = QVBoxLayout(central)

    orb = BlazeOrb()
    layout.addWidget(orb)

    btn_row = QHBoxLayout()
    for state in ("idle", "listening", "speaking", "danger"):
        b = QPushButton(state)
        b.clicked.connect(lambda checked=False, s=state: orb.set_state(s))
        btn_row.addWidget(b)
    layout.addLayout(btn_row)

    win.setCentralWidget(central)
    win.resize(360, 460)

    orb.switch_to_chat_mode.connect(lambda: print("[demo] would switch to chatbot mode here"))

    hw_timer = QTimer()

    def poll_hw():
        snap = hw_stats.snapshot()
        orb.push_cpu(snap["cpu_pct"], snap["cpu_temp_c"])
        if snap["gpu_pct"] is not None:
            orb.push_gpu(snap["gpu_pct"], snap["gpu_temp_c"])

    hw_timer.timeout.connect(poll_hw)
    hw_timer.start(1000)  # real hardware read once a second; the widget smooths the rest

    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    _demo()
