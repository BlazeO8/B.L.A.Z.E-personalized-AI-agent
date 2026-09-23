"""
gui/phone_mirror.py — embedded, interactive phone-screen panel.

Two mirroring modes, chosen automatically:

1. EMBEDDED SCRCPY (real-time, low latency) — Windows only, requires the
   `scrcpy` binary (github.com/Genymobile/scrcpy) and the `pywin32`
   package. scrcpy is launched pointed at a borderless off-screen-ish
   window, then that window's native handle is reparented directly inside
   this widget via the Win32 SetParent API — so what you're looking at is
   scrcpy's actual live H.264 decode, not a polled screenshot. Mouse
   clicks/drags on it go straight to scrcpy's own window and are handled
   by scrcpy natively (real phone control, not our own tap-forwarding).
   Typical latency for scrcpy itself is in the tens of milliseconds, not
   seconds — this is the "no lag" mode.

2. SNAPSHOT POLLING (fallback, ~1-3fps) — used whenever mode 1 isn't
   available (not on Windows, pywin32 not installed, scrcpy not
   installed, or scrcpy failed to open a window in time) or the phone
   isn't paired for scrcpy specifically. A background QThread polls
   `adb exec-out screencap -p` and streams frames into a QLabel. This is
   the same approach as before, with the earlier ~1fps pacing bugs fixed
   (see _MirrorWorker's docstring) — genuinely closer to ~1-3fps now, but
   still not real video; each frame is still a fresh capture + PNG encode
   + transfer, not a continuous stream.

Mode 1 is attempted first whenever the platform/deps support it; mode 2
is always kept running underneath as the connection watcher (it's how we
notice a phone connecting/disconnecting in the first place) and as the
automatic fallback the instant mode 1 isn't usable.

IMPORTANT — testability: the embedded-scrcpy path (mode 1) relies on
Win32-specific APIs (win32gui/win32con from pywin32) that only exist on
Windows, and on an actual scrcpy process + a real paired phone to open a
window against. None of that exists in the Linux sandbox this was
written in — the reparenting code follows the standard, well-documented
Win32 pattern for embedding a foreign top-level window (the same
technique used by various Windows apps that embed an external
player/game window), but it has not been run end-to-end against a real
scrcpy window. If it doesn't work as-is on your machine, the panel should
still fail safe into snapshot mode rather than showing a blank panel —
that fallback path is what was actually testable here.

Device naming: adb identifies phones by serial or IP:port, which means
nothing at a glance. The ✎ button here writes a friendly name via
blaze.core.devices.set_device_name(), persisted in the same pref store
as everything else in this codebase, so it's remembered next launch and
survives reconnects (keyed by serial, not by connection order).
"""

from __future__ import annotations
import logging
import os
import platform
import subprocess
import threading
import time

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont, QImage, QPixmap, QMouseEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QInputDialog,
    QFrame, QStackedLayout,
)

from blaze.services import android_control as adb
from blaze.core import devices

log = logging.getLogger("blaze.phone_mirror")

# Same literal palette as chat_window.py (lifted from blaze_ui.html's
# :root block) — re-declared here rather than imported to avoid a
# circular import between the two modules.
BG3 = "#141422"
BG4 = "#1c1c30"
GREEN = "#4ade80"
AMBER = "#fbbf24"
RED = "#f87171"
TXT = "#e2e8f0"
TXT2 = "#94a3b8"
BDR2 = "#2a2a48"

_IS_WINDOWS = platform.system() == "Windows"

try:
    import win32gui  # noqa: F401
    import win32con  # noqa: F401
    _PYWIN32_AVAILABLE = True
except ImportError:
    _PYWIN32_AVAILABLE = False

try:
    import av  # noqa: F401
    _AV_AVAILABLE = True
except ImportError as e:
    _AV_AVAILABLE = False
    logging.getLogger("blaze.phone_mirror").warning(
        "PyAV not importable (%s) — real-time mirroring will fall back to "
        "snapshot mode. Run: pip install av", e,
    )


def mono(size=10, weight=QFont.Normal):
    f = QFont("JetBrains Mono", size)
    f.setStyleHint(QFont.Monospace)
    f.setWeight(weight)
    return f


def streaming_supported() -> bool:
    """Whether genuine real-time (not polled-screenshot) mirroring is
    possible on this machine: needs the optional `av` package (PyAV) to
    decode the raw H.264 stream `adb shell screenrecord` gives us. This
    is the preferred mirroring path — unlike embedding scrcpy's own
    window (see _ScrcpyEmbed below), it needs no native-window
    reparenting, no pywin32, no scrcpy binary, and works identically on
    Windows/macOS/Linux. `pip install av` if this returns False."""
    return _AV_AVAILABLE


def embedding_supported() -> bool:
    """Whether real-time embedded mirroring (mode 1) is even possible on
    this machine, independent of whether a phone is currently paired.

    Disabled by default (opt-in via BLAZE_ENABLE_SCRCPY_EMBED=1). Reparenting
    scrcpy's own GPU-rendered window via raw Win32 calls turned out to be
    fragile in ways that go past "sometimes shows a blank panel": the
    SWP_FRAMECHANGED/style-fixing calls used to make it paint correctly send
    messages synchronously into scrcpy's own thread, and if that thread is
    busy, the whole app UI freezes ("Not Responding") instead of just the
    mirror panel misbehaving. Snapshot mode (mode 2, always running
    underneath) is the actually-tested, stable path — real-time embedding
    can be re-enabled by anyone who wants to keep iterating on it, but it
    should not be the silent default anymore."""
    if os.environ.get("BLAZE_ENABLE_SCRCPY_EMBED") != "1":
        return False
    return _IS_WINDOWS and _PYWIN32_AVAILABLE and adb.scrcpy_available()


class _MirrorWorker(QThread):
    """Background polling loop — this is BOTH the snapshot-mode frame
    source AND the always-on connection watcher (device connect/disconnect
    detection) used by embedded mode too. Every adb call here genuinely
    blocks (subprocess + phone-side work + transfer time), so this must
    never run on the Qt main thread — same reasoning as ai.chat() running
    on its own QThread in app_shell.py, or the whole window would freeze
    on every single poll."""

    frame_ready = Signal(bytes)
    # state in {"no_adb", "no_device", "connected"}
    status_changed = Signal(str)
    device_ready = Signal(str)  # serial of the device now being mirrored

    # How often to re-run `adb devices` while already mirroring, purely to
    # notice a disconnect/reconnect — NOT how often a frame is captured.
    # Earlier this ran on every single loop iteration, meaning every frame
    # actually cost two full adb round trips (one for `devices`, one for
    # the screencap itself). That extra call was the main reason snapshot
    # mode felt like ~1fps instead of the ~1-2fps a single screencap round
    # trip alone gets you.
    _DEVICE_RECHECK_SECS = 3.0

    def __init__(self, min_interval_ms: int = 50, parent=None):
        super().__init__(parent)
        # Floor between frame *starts*, not an unconditional sleep tacked
        # on after every capture — see the pacing note in run() below.
        self.min_interval_ms = min_interval_ms
        self._running = True
        self._serial: str | None = None
        # Set True once embedded (scrcpy) mode has taken over the actual
        # video — this loop then keeps watching for a disconnect but stops
        # wasting bandwidth/adb calls on screencaps nobody's looking at.
        self.capture_paused = False

    def stop(self):
        self._running = False

    def set_capture_paused(self, paused: bool):
        self.capture_paused = paused

    def run(self):
        if not adb.adb_available():
            self.status_changed.emit("no_adb")
            return

        last_device_check = 0.0

        while self._running:
            now = time.monotonic()
            need_check = self._serial is None or (now - last_device_check) >= self._DEVICE_RECHECK_SECS
            if need_check:
                devs = [s for s, state in adb.list_devices() if state == "device"]
                last_device_check = now
                if not devs:
                    self._serial = None
                    self.status_changed.emit("no_device")
                    self.msleep(500)
                    continue
                if self._serial not in devs:
                    self._serial = devs[0]
                    self.device_ready.emit(self._serial)

            self.status_changed.emit("connected")

            if self.capture_paused:
                # Embedded mode is handling real video itself — just keep
                # watching for a disconnect at the normal recheck cadence.
                self.msleep(500)
                continue

            start = time.monotonic()
            frame = adb.screencap_png_bytes(serial=self._serial)
            elapsed_ms = (time.monotonic() - start) * 1000

            if frame is None:
                # Capture failed — the phone likely dropped mid-stream.
                # Force a fresh device check next loop instead of hammering
                # a serial that's no longer there.
                self._serial = None
                last_device_check = 0.0
                self.status_changed.emit("no_device")
                self.msleep(500)
                continue

            if self._running:
                self.frame_ready.emit(frame)

            # Only pad the wait if the capture finished *faster* than the
            # floor — never add extra delay on top of a capture that
            # already took a while.
            remaining = self.min_interval_ms - elapsed_ms
            if remaining > 0:
                self.msleep(int(remaining))


class _H264StreamWorker(QThread):
    """Genuine real-time mirroring: pipes adb's raw H.264 screenrecord
    stream through PyAV's decoder and emits every decoded frame as it
    arrives, instead of polling individual screenshots like _MirrorWorker
    does. This is the same underlying video data scrcpy mirrors (Android's
    hardware screen encoder) — the difference is we decode and paint it
    onto our own QLabel directly, rather than launching scrcpy and
    embedding its native window. That sidesteps every issue further down
    this file (WS_CHILD/style bits, SDL3's direct3d11 black-screen bug,
    cross-process SendMessage freezes) entirely, since there's no foreign
    window involved at any point — just bytes in, QImages out.

    screenrecord stops itself after ~180s no matter what --time-limit
    says (an Android platform limit, not ours) — this loop notices the
    process exiting and transparently restarts it, so in practice the
    stream just has a brief hiccup every ~3 minutes rather than actually
    stopping.

    IMPORTANT — testability: like the scrcpy-embed path, this has been
    written against documented adb/screenrecord/PyAV behavior but not run
    end-to-end against a real device from this sandbox (no phone, no
    `av` package here). If PyAV chokes on a live non-seekable pipe on
    your setup, stream_failed fires and the caller falls back to snapshot
    mode — same fail-safe contract as the scrcpy path."""

    frame_ready = Signal(object)  # QImage
    stream_failed = Signal(str)

    def __init__(self, serial: str, size: str | None = None, parent=None):
        super().__init__(parent)
        self._serial = serial
        self._size = size
        self._running = True
        self._proc: subprocess.Popen | None = None

    def stop(self):
        self._running = False
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass

    def run(self):
        if not _AV_AVAILABLE:
            self.stream_failed.emit("PyAV not installed — run: pip install av")
            return

        ever_decoded_a_frame = False
        while self._running:
            self._proc = adb.open_screenrecord_stream(serial=self._serial, size=self._size)
            if self._proc is None:
                self.stream_failed.emit("couldn't start adb screenrecord")
                return
            try:
                container = av.open(self._proc.stdout, format="h264")
                for frame in container.decode(video=0):
                    if not self._running:
                        break
                    ever_decoded_a_frame = True
                    arr = frame.to_ndarray(format="rgb24")
                    h, w, _ = arr.shape
                    img = QImage(arr.tobytes(), w, h, w * 3, QImage.Format_RGB888).copy()
                    self.frame_ready.emit(img)
                container.close()
            except Exception as e:
                if not ever_decoded_a_frame:
                    # Never got a single frame, even on the very first
                    # attempt — treat as a hard failure (e.g. this
                    # Android version's screenrecord/PyAV combo doesn't
                    # cooperate) rather than looping forever.
                    self.stream_failed.emit(str(e))
                    return
                # Otherwise we were already streaming fine and this is
                # just the ~180s screenrecord cutoff (or a brief hiccup) —
                # fall through and restart below.
            finally:
                if self._proc and self._proc.poll() is None:
                    try:
                        self._proc.terminate()
                        self._proc.wait(timeout=2)
                    except Exception:
                        try:
                            self._proc.kill()
                        except Exception:
                            pass
            if self._running:
                self.msleep(200)  # brief pause before restarting screenrecord


class _TapLabel(QLabel):
    """QLabel that reports clicks as fractional (0..1, 0..1) coordinates
    within its own displayed pixmap. The panel converts that fraction to
    real device pixels once it knows the phone's actual resolution.
    Only used in snapshot mode — embedded mode gets real mouse input for
    free since it's a real reparented window, not an image."""

    tapped = Signal(float, float)

    def mousePressEvent(self, event: QMouseEvent):
        pm = self.pixmap()
        if pm and not pm.isNull():
            off_x = (self.width() - pm.width()) / 2
            off_y = (self.height() - pm.height()) / 2
            x = event.position().x() - off_x
            y = event.position().y() - off_y
            if 0 <= x <= pm.width() and 0 <= y <= pm.height():
                self.tapped.emit(x / pm.width(), y / pm.height())
        super().mousePressEvent(event)


class _ClickableLabel(QLabel):
    """Tiny QLabel that also emits a click — used for the mode indicator
    so there's a manual way to bail out of a stuck "live" embed (e.g. a
    future scrcpy/driver combo that hits the same GPU-swap-chain issue)
    without needing another code change."""

    clicked = Signal()

    def mousePressEvent(self, event: QMouseEvent):
        self.clicked.emit()
        super().mousePressEvent(event)


class _ScrcpyEmbed(QWidget):
    """Launches scrcpy targeting a specific device and embeds its native
    window inside this widget.

    First implementation used raw Win32 SetParent + manual WS_CHILD style
    munging. That technically reparents the window (it receives input
    correctly, hence "live" + a green dot showing up right away) but Qt's
    own compositor has no idea a foreign window is sitting there, so it
    keeps painting its normal background *over* it — the reported symptom
    (device shows "live", panel area is just blank/black) is close to the
    textbook signature of that exact gotcha.

    Fixed by using the officially supported Qt mechanism for this instead:
    QWindow.fromWinId() wraps the foreign HWND as a real QWindow, and
    QWidget.createWindowContainer() embeds that QWindow properly inside
    Qt's own widget/compositor hierarchy — Qt then handles painting,
    resizing, and input routing itself, which is what this API exists
    for (it's the same mechanism used to embed e.g. native video/OpenGL
    surfaces in Qt apps). No more manual style bit-twiddling or MoveWindow
    calls needed; the container behaves like a normal Qt widget in the
    layout.

    Reports embed_ready on success or embed_failed(reason) on any failure
    so the caller can fall back to snapshot mode instead of showing a
    dead panel. See the module docstring for the broader testability
    caveat — the FindWindow lookup still needs pywin32/Win32, but the
    embedding step itself is now plain Qt."""

    embed_ready = Signal()
    embed_failed = Signal(str)

    _FIND_TIMEOUT_MS = 6000
    _FIND_POLL_MS = 150

    def __init__(self, serial: str, parent=None):
        super().__init__(parent)
        self._serial = serial
        self._proc: subprocess.Popen | None = None
        self._container: QWidget | None = None  # wraps the foreign QWindow once found
        self._title = f"BLAZE_MIRROR_{id(self)}"
        self._elapsed_ms = 0
        self._hwnd = None
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._find_timer = QTimer(self)
        self._find_timer.timeout.connect(self._try_find_window)

    def start(self):
        if not _PYWIN32_AVAILABLE:
            self.embed_failed.emit("pywin32 not installed")
            return
        try:
            # scrcpy 4.x moved from SDL2 to SDL3, and SDL3 defaults to the
            # direct3d11 backend on Windows. There are multiple open SDL
            # bugs (e.g. libsdl-org/SDL#14733) about direct3d11 producing a
            # black/inert render surface in exactly this kind of embedding
            # scenario — matching the "live, green dot, blank panel"
            # symptom regardless of the WS_CHILD/style fix below. scrcpy
            # exposes --render-driver directly (passed straight into SDL3's
            # renderer creation), so use that instead of the SDL2-era
            # SDL_RENDER_DRIVER env var, which SDL3 doesn't honor the same
            # way.
            self._proc = subprocess.Popen(
                [
                    adb.SCRCPY_BIN, "-s", self._serial,
                    f"--window-title={self._title}",
                    "--window-borderless",
                    "--max-size=480",  # small target panel — lower res = lower latency
                    "--render-driver=software",
                ],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            self.embed_failed.emit(str(e))
            return
        self._elapsed_ms = 0
        self._find_timer.start(self._FIND_POLL_MS)

    def _try_find_window(self):
        self._elapsed_ms += self._FIND_POLL_MS
        if self._proc is None or self._proc.poll() is not None:
            self._find_timer.stop()
            self.embed_failed.emit("scrcpy exited before opening a window")
            return
        try:
            hwnd = win32gui.FindWindow(None, self._title)
        except Exception as e:
            self._find_timer.stop()
            self.embed_failed.emit(f"FindWindow failed: {e}")
            return
        if hwnd:
            self._find_timer.stop()
            self._embed(hwnd)
            return
        if self._elapsed_ms >= self._FIND_TIMEOUT_MS:
            self._find_timer.stop()
            self.embed_failed.emit("timed out waiting for scrcpy's window")

    def _embed(self, hwnd):
        try:
            from PySide6.QtGui import QWindow
            foreign = QWindow.fromWinId(int(hwnd))
            if foreign is None:
                raise RuntimeError("QWindow.fromWinId returned None for scrcpy's window")
            self._container = QWidget.createWindowContainer(foreign, self)
            self._layout.addWidget(self._container)
            self._hwnd = hwnd
            self._fix_native_window_style(hwnd)
        except Exception as e:
            self.embed_failed.emit(f"embedding failed: {e}")
            return
        self.embed_ready.emit()

    def _fix_native_window_style(self, hwnd):
        """createWindowContainer() reparents scrcpy's HWND in Qt's object
        tree, but it never touches the HWND's actual Win32 style bits.
        scrcpy's window (SDL-rendered) is still internally styled as a
        top-level WS_POPUP window, so even once it's a "child" as far as
        Qt is concerned, Windows itself keeps compositing it as an
        independent overlapping surface instead of clipping it into our
        panel's rectangle -- that's what produces the "live, green dot,
        blank panel" symptom: the video is genuinely being rendered
        somewhere, just not inside the space we can see. Stripping the
        popup/caption/frame bits, forcing WS_CHILD, and re-applying with
        SWP_FRAMECHANGED is what makes Windows actually treat it as a
        normal embedded child from here on."""
        try:
            style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
            style &= ~(win32con.WS_POPUP | win32con.WS_CAPTION | win32con.WS_THICKFRAME
                       | win32con.WS_SYSMENU | win32con.WS_MINIMIZEBOX | win32con.WS_MAXIMIZEBOX)
            style |= win32con.WS_CHILD
            win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)

            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            ex_style &= ~(win32con.WS_EX_APPWINDOW | win32con.WS_EX_TOPMOST)
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex_style)

            w = max(self.width(), 1)
            h = max(self.height(), 1)
            win32gui.SetWindowPos(
                hwnd, 0, 0, 0, w, h,
                win32con.SWP_FRAMECHANGED | win32con.SWP_NOZORDER
                | win32con.SWP_NOACTIVATE | win32con.SWP_ASYNCWINDOWPOS,
            )
        except Exception:
            # Non-fatal -- embed_ready still fires. Worst case we're back
            # to the blank-panel symptom, but the HWND is genuinely
            # reparented either way, so nothing else breaks.
            pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Forcing raw WS_CHILD above can bypass Qt's own internal resize
        # sync for a genuinely foreign (non-Qt) window, so keep the real
        # HWND's size pinned to this container ourselves. SWP_ASYNCWINDOWPOS
        # is load-bearing here: without it, this SetWindowPos call blocks
        # the calling (Qt main) thread until scrcpy's own thread processes
        # the resulting message — if that thread is busy, the whole app UI
        # freezes ("Not Responding") instead of just the mirror lagging.
        if self._hwnd:
            try:
                win32gui.SetWindowPos(
                    self._hwnd, 0, 0, 0, self.width(), self.height(),
                    win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
                    | win32con.SWP_ASYNCWINDOWPOS,
                )
            except Exception:
                pass

    def stop(self):
        self._find_timer.stop()
        if self._container:
            self._container.setParent(None)
            self._container.deleteLater()
            self._container = None
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=2)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
        self._proc = None
        self._hwnd = None


class PhoneMirrorPanel(QFrame):
    """Drop-in replacement for the old Quick Actions button list — sits
    in the same spot in chat_window.py's left panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        self._serial: str | None = None
        self._screen_wh: tuple[int, int] | None = None
        self._enlarged = False
        self._last_frame_img: QImage | None = None
        self._embed: _ScrcpyEmbed | None = None
        self._embed_attempted = False
        self._stream_worker: _H264StreamWorker | None = None
        self._stream_attempted = False
        self._build_ui()

        self._worker = _MirrorWorker()
        self._worker.frame_ready.connect(self._on_frame)
        self._worker.status_changed.connect(self._on_status)
        self._worker.device_ready.connect(self._on_device_ready)
        self._worker.start()

    def _build_ui(self):
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(6)

        header = QHBoxLayout()
        self._dot = QLabel("●")
        self._dot.setStyleSheet(f"color:{RED}; font-size:9px;")
        header.addWidget(self._dot)
        self._name_lbl = QLabel("No phone connected")
        self._name_lbl.setFont(mono(9))
        self._name_lbl.setStyleSheet(f"color:{TXT2};")
        header.addWidget(self._name_lbl, stretch=1)
        self._mode_lbl = _ClickableLabel("")
        self._mode_lbl.setFont(mono(8))
        self._mode_lbl.setStyleSheet(f"color:{TXT2};")
        self._mode_lbl.setToolTip("Click to switch to snapshot mode if the live view is blank")
        self._mode_lbl.clicked.connect(self._on_mode_label_clicked)
        header.addWidget(self._mode_lbl)
        rename_btn = QPushButton("✎")
        rename_btn.setFixedSize(20, 20)
        rename_btn.setToolTip("Rename this device")
        rename_btn.setStyleSheet(
            f"QPushButton {{ background:{BG3}; color:{TXT2}; border:1px solid {BDR2};"
            f" border-radius:4px; }} QPushButton:hover {{ background:{BG4}; color:{TXT}; }}"
        )
        rename_btn.clicked.connect(self._on_rename)
        header.addWidget(rename_btn)
        col.addLayout(header)

        # Stack: snapshot QLabel underneath, scrcpy embed widget on top —
        # only one is ever visible/active at a time.
        self._mirror_container = QWidget()
        self._mirror_container.setFixedSize(200, 400)
        self._stack = QStackedLayout(self._mirror_container)
        self._stack.setContentsMargins(0, 0, 0, 0)

        self._screen_lbl = _TapLabel()
        self._screen_lbl.setAlignment(Qt.AlignCenter)
        self._screen_lbl.setStyleSheet(
            f"background:{BG3}; border:1px solid {BDR2}; border-radius:10px; color:{TXT2};"
            f" padding:8px;"
        )
        self._screen_lbl.setFont(mono(8))
        self._screen_lbl.setWordWrap(True)
        self._screen_lbl.setText("Waiting for phone…")
        self._screen_lbl.tapped.connect(self._on_tap)
        self._stack.addWidget(self._screen_lbl)

        col.addWidget(self._mirror_container, alignment=Qt.AlignHCenter)

        nav = QHBoxLayout()
        nav.setSpacing(6)
        for label, keycode, attr in (("◁", "BACK", "back"), ("○", "HOME", "home"), ("▢", "APP_SWITCH", "recents")):
            btn = QPushButton(label)
            btn.setFixedSize(58, 24)
            btn.setEnabled(False)
            btn.setStyleSheet(
                f"QPushButton {{ background:{BG3}; color:{TXT2}; border:1px solid {BDR2};"
                f" border-radius:6px; }} QPushButton:hover {{ background:{BG4}; color:{TXT}; }}"
                f" QPushButton:disabled {{ color:{BDR2}; }}"
            )
            btn.clicked.connect(lambda checked=False, k=keycode: self._send_key(k))
            nav.addWidget(btn)
            setattr(self, f"_nav_{attr}", btn)
        col.addLayout(nav)

    # --- worker signal handlers --------------------------------------------

    def _on_status(self, state: str):
        if state == "no_adb":
            self._set_dot(RED)
            self._name_lbl.setText("adb not installed")
            self._mode_lbl.setText("")
            self._screen_lbl.setText("adb not found.\nInstall Android SDK\nPlatform Tools and add\nit to PATH.")
            self._set_nav_enabled(False)
        elif state == "no_device":
            self._set_dot(AMBER)
            self._name_lbl.setText("No phone connected")
            self._mode_lbl.setText("")
            self._screen_lbl.setText("No phone connected.\nEnable Wireless debugging\non your phone and pair it\n(see android_control.py).")
            self._set_nav_enabled(False)
            self._teardown_embed()
            self._embed_attempted = False
            self._stream_attempted = False
            self._stack.setCurrentWidget(self._screen_lbl)
        elif state == "connected":
            self._set_dot(GREEN)
            self._set_nav_enabled(True)

    # Panel width is fixed by the sidebar; height is derived from the
    # phone's actual aspect ratio once known, instead of a guessed fixed
    # box — a fixed 200x400 (1:2) box against a real phone's ~9:19.5-9:20
    # screen left visible black bars down both sides (reported: mirror
    # showing "live" content correctly, just letterboxed/pillarboxed
    # inside a box that didn't match its shape).
    _MIRROR_WIDTH = 200
    _MIRROR_WIDTH_ENLARGED = 360  # "open/enlarge my phone screen" target width
    _MIRROR_MAX_HEIGHT = 640  # sanity cap in case a bogus resolution ever comes back
    _MIRROR_MAX_HEIGHT_ENLARGED = 900

    def _resize_mirror_to_aspect(self):
        if not self._screen_wh:
            return
        w, h = self._screen_wh
        if w <= 0 or h <= 0:
            return
        target_w = self._MIRROR_WIDTH_ENLARGED if self._enlarged else self._MIRROR_WIDTH
        max_h = self._MIRROR_MAX_HEIGHT_ENLARGED if self._enlarged else self._MIRROR_MAX_HEIGHT
        target_h = min(round(target_w * h / w), max_h)
        self._mirror_container.setFixedSize(target_w, target_h)
        if self._last_frame_img is not None:
            self._render_frame(self._last_frame_img)

    def set_enlarged(self, enlarged: bool):
        """Called (via BlazeController's signal, see app_shell.py) when the
        user says something like "open my phone screen" or "make my phone
        screen bigger" — handled deterministically in
        handlers/phone_handler.py, no LLM round trip involved. Safe to call
        before a phone's ever connected; it just takes effect the moment
        _screen_wh becomes known."""
        self._enlarged = enlarged
        self._resize_mirror_to_aspect()

    def _on_device_ready(self, serial: str):
        self._serial = serial
        self._name_lbl.setText(devices.get_device_name(serial))
        wh = adb.screen_size(serial=serial)
        if wh:
            self._screen_wh = wh
            self._resize_mirror_to_aspect()

        if streaming_supported() and not self._stream_attempted:
            self._stream_attempted = True
            self._mode_lbl.setText("connecting…")
            target_size = None
            if self._screen_wh:
                w, h = self._screen_wh
                target_w = 480  # keep decode cheap for a small panel
                target_size = f"{target_w}x{round(target_w * h / w)}"
            self._stream_worker = _H264StreamWorker(serial, size=target_size)
            self._stream_worker.frame_ready.connect(self._on_stream_frame)
            self._stream_worker.stream_failed.connect(self._on_stream_failed)
            self._worker.set_capture_paused(True)  # real stream replaces snapshot polling
            self._stream_worker.start()
        elif embedding_supported() and not self._embed_attempted:
            self._embed_attempted = True
            self._mode_lbl.setText("connecting…")
            self._embed = _ScrcpyEmbed(serial, parent=self._mirror_container)
            self._embed.embed_ready.connect(self._on_embed_ready)
            self._embed.embed_failed.connect(self._on_embed_failed)
            self._stack.addWidget(self._embed)
            self._embed.start()
        elif not streaming_supported() and not embedding_supported():
            self._mode_lbl.setText("snapshot")

    def _on_stream_frame(self, img: QImage):
        if self._mode_lbl.text() != "live":
            self._mode_lbl.setText("live")
            self._mode_lbl.setStyleSheet(f"color:{GREEN};")
        self._render_frame(img)
        self._stack.setCurrentWidget(self._screen_lbl)

    def _on_stream_failed(self, reason: str):
        # Real-time streaming didn't pan out (e.g. PyAV missing, or this
        # phone's screenrecord/PyAV combo didn't cooperate) — fall back to
        # snapshot mode, which the worker's already been running the whole
        # time underneath.
        log.warning("Real-time phone mirror stream failed, falling back to snapshot: %s", reason)
        self._mode_lbl.setText("snapshot")
        self._mode_lbl.setStyleSheet(f"color:{TXT2};")
        self._worker.set_capture_paused(False)
        self._stack.setCurrentWidget(self._screen_lbl)
        if self._stream_worker:
            self._stream_worker.stop()
            self._stream_worker = None

    def _on_mode_label_clicked(self):
        # Manual override — only meaningful while some real-time mode is
        # actually active (live). Reuses the exact same fallback path as
        # an automatic failure, whichever engine is currently running.
        if self._stream_worker is not None:
            self._on_stream_failed("manually switched to snapshot mode")
        elif self._embed is not None:
            self._on_embed_failed("manually switched to snapshot mode")

    def _on_embed_ready(self):
        self._mode_lbl.setText("live")
        self._mode_lbl.setStyleSheet(f"color:{GREEN};")
        self._stack.setCurrentWidget(self._embed)
        self._worker.set_capture_paused(True)

    def _on_embed_failed(self, reason: str):
        # Real-time mode didn't pan out — fall back to snapshot mode,
        # which the worker's already been running the whole time.
        self._mode_lbl.setText("snapshot")
        self._mode_lbl.setStyleSheet(f"color:{TXT2};")
        self._worker.set_capture_paused(False)
        self._stack.setCurrentWidget(self._screen_lbl)
        if self._embed:
            self._embed.stop()
            self._embed = None

    def _teardown_embed(self):
        if self._embed:
            self._embed.stop()
            self._embed = None
        if self._stream_worker:
            self._stream_worker.stop()
            self._stream_worker = None
        self._worker.set_capture_paused(False)
        self._mode_lbl.setText("")

    def _on_frame(self, png_bytes: bytes):
        img = QImage.fromData(png_bytes, "PNG")
        if img.isNull():
            return
        self._render_frame(img)

    def _render_frame(self, img: QImage):
        """Single shared path for painting a frame onto _screen_lbl, used
        by both snapshot and real-time streaming. Caches the frame so
        _resize_mirror_to_aspect() can immediately redraw it at the new
        size — without this, resizing the panel (e.g. via "make my phone
        screen bigger") left the previous frame's already-scaled pixmap on
        screen until the *next* frame arrived, which at snapshot mode's
        ~1-3fps could visibly linger for a second at the wrong size/scale
        relative to the now-resized container — easy to mistake for actual
        cropping even though KeepAspectRatio itself never crops."""
        if img is None or img.isNull():
            return
        self._last_frame_img = img
        pix = QPixmap.fromImage(img).scaled(
            self._screen_lbl.width(), self._screen_lbl.height(),
            Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        self._screen_lbl.setPixmap(pix)

    def _on_rename(self):
        if not self._serial:
            return
        current = devices.get_device_name(self._serial)
        name, ok = QInputDialog.getText(self, "Rename device", "Name for this phone:", text=current)
        if ok:
            devices.set_device_name(self._serial, name)
            self._name_lbl.setText(name.strip() or self._serial)

    def _on_tap(self, rel_x: float, rel_y: float):
        if not self._serial or not self._screen_wh:
            return
        w, h = self._screen_wh
        x, y = int(rel_x * w), int(rel_y * h)
        serial = self._serial
        threading.Thread(target=adb.tap, args=(x, y), kwargs={"serial": serial}, daemon=True).start()

    def _send_key(self, keycode: str):
        if not self._serial:
            return
        serial = self._serial
        threading.Thread(target=adb.press_key, args=(keycode,), kwargs={"serial": serial}, daemon=True).start()

    def _set_dot(self, color: str):
        self._dot.setStyleSheet(f"color:{color}; font-size:9px;")

    def _set_nav_enabled(self, enabled: bool):
        for attr in ("back", "home", "recents"):
            btn = getattr(self, f"_nav_{attr}", None)
            if btn:
                btn.setEnabled(enabled)

    def shutdown(self):
        """Call from the parent window's closeEvent so the polling thread
        and any live scrcpy process stop instead of lingering after the
        window's gone."""
        self._teardown_embed()
        self._worker.stop()
        self._worker.wait(2000)
