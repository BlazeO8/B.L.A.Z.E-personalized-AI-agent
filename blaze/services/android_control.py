"""
services/android_control.py — wraps the real `adb` (Android Debug Bridge)
binary via subprocess. No device required just to import this module;
every function fails gracefully with a clear message if adb isn't
installed or no device is connected/authorized — same pattern as
hw_stats.py elsewhere in this codebase.

Requires Android SDK Platform Tools (`adb`) installed and on PATH:
https://developer.android.com/tools/releases/platform-tools

═══════════════════════════════════════════════════════════════════════════
ONE-TIME PHONE-SIDE SETUP — this module CANNOT automate this part.
Android requires pairing to happen physically on the device, by design,
as a security measure. There is no way around this, not even for BLAZE.
═══════════════════════════════════════════════════════════════════════════
  1. On your phone: Settings -> About phone -> tap "Build number" 7 times
     to unlock Developer Options.
  2. Settings -> System -> Developer options -> enable "Wireless debugging".
  3. Tap "Wireless debugging" -> "Pair device with pairing code" — shows
     an IP:port and a 6-digit code, both change each time you open this.
  4. On your PC, run: adb pair <ip>:<port>   (enter the 6-digit code)
  5. The Wireless debugging screen also shows a separate IP:port for
     connecting (NOT the pairing one) — run: adb connect <ip>:<port>
  6. After this, BLAZE can reconnect on its own each session with
     connect_wireless() as long as your phone's IP doesn't change (same
     Wi-Fi network) — no more manual pairing needed unless you disable
     Wireless debugging or factory reset.

Save the phone's IP once it's working — pass it to connect_wireless()
from wherever you wire this into settings/config.
"""

from __future__ import annotations
import subprocess
import shutil
import re

ADB_BIN = shutil.which("adb")
SCRCPY_BIN = shutil.which("scrcpy")


def adb_available() -> bool:
    return ADB_BIN is not None


def scrcpy_available() -> bool:
    return SCRCPY_BIN is not None


def _run(*args, timeout: int = 15, serial: str | None = None) -> tuple[bool, str]:
    """Runs `adb [-s <serial>] <args>`, returns (success, output_or_error_message).
    `serial` targets a specific device when more than one is connected —
    same as adb's own `-s` flag; omit it when there's only one device."""
    if not adb_available():
        return False, "adb not found. Install Android SDK Platform Tools and add it to PATH."
    cmd = [ADB_BIN]
    if serial:
        cmd += ["-s", serial]
    cmd += list(args)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, shell=False
        )
        if result.returncode != 0:
            return False, (result.stderr or result.stdout).strip() or "adb command failed"
        return True, result.stdout.strip()
    except subprocess.TimeoutExpired:
        return False, f"adb command timed out after {timeout}s — phone may be unreachable"
    except Exception as e:
        return False, str(e)


def _run_bytes(*args, timeout: int = 15, serial: str | None = None) -> tuple[bool, bytes]:
    """Same as _run but for commands whose output is binary (e.g. screencap
    piped straight through `exec-out`) — returns raw stdout bytes instead
    of decoding as text."""
    if not adb_available():
        return False, b""
    cmd = [ADB_BIN]
    if serial:
        cmd += ["-s", serial]
    cmd += list(args)
    try:
        result = subprocess.run(
            cmd, capture_output=True, timeout=timeout, shell=False
        )
        if result.returncode != 0:
            return False, b""
        return True, result.stdout
    except Exception:
        return False, b""


# ── Connection ──────────────────────────────────────────────────────────────

def is_connected() -> bool:
    ok, out = _run("devices")
    if not ok:
        return False
    for line in out.splitlines()[1:]:
        if line.strip().endswith("\tdevice"):
            return True
    return False


def connected_device_id() -> str | None:
    ok, out = _run("devices")
    if not ok:
        return None
    for line in out.splitlines()[1:]:
        if line.strip().endswith("\tdevice"):
            return line.split("\t")[0]
    return None


def list_devices() -> list[tuple[str, str]]:
    """All devices adb currently knows about, as (serial, state) pairs.
    state is usually 'device' (ready), 'unauthorized' (needs an on-phone
    tap to approve this computer), or 'offline'. Returns [] if adb isn't
    installed or nothing is connected — never raises."""
    ok, out = _run("devices")
    if not ok:
        return []
    devices = []
    for line in out.splitlines()[1:]:
        line = line.strip()
        if not line or "\t" not in line:
            continue
        serial, state = line.split("\t", 1)
        devices.append((serial, state))
    return devices


def connect_wireless(ip: str, port: int = 5555) -> tuple[bool, str]:
    return _run("connect", f"{ip}:{port}")


def pair(ip: str, port: int, code: str) -> tuple[bool, str]:
    """One-time pairing using the code shown on the phone's Wireless
    debugging > Pair device screen. This is the one step you always have
    to do by hand at least once — see the module docstring."""
    return _run("pair", f"{ip}:{port}", code)


def disconnect() -> tuple[bool, str]:
    return _run("disconnect")


# ── Status ──────────────────────────────────────────────────────────────────

def battery_status(serial: str | None = None) -> dict | None:
    ok, out = _run("shell", "dumpsys", "battery", serial=serial)
    if not ok:
        return None
    level = re.search(r"level:\s*(\d+)", out)
    plugged = re.search(r"plugged:\s*(\d+)", out)
    return {
        "level": int(level.group(1)) if level else None,
        "plugged": bool(int(plugged.group(1))) if plugged else False,
    }


def screen_size(serial: str | None = None) -> tuple[int, int] | None:
    """Physical screen resolution in pixels, e.g. (1080, 2400). Needed to
    map a tap on the mirrored image back to real device coordinates."""
    ok, out = _run("shell", "wm", "size", serial=serial)
    if not ok:
        return None
    m = re.search(r"(\d+)x(\d+)", out)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


# ── Screen ──────────────────────────────────────────────────────────────────

def screenshot(save_path: str, also_save_on_phone: bool = True) -> tuple[bool, str]:
    """Captures the phone's screen. By default this now does two things:
    1. Captures directly to the phone's own storage under
       Pictures/Screenshots/, then tells Android's media scanner to index
       it — so it shows up in the phone's Gallery/Photos app immediately,
       same as if you'd pressed the physical screenshot button.
    2. Pulls a copy to save_path on this laptop too.

    Pass also_save_on_phone=False to skip step 1 and only pull straight
    to the laptop (the original behavior, slightly faster, nothing left
    on the phone)."""
    if not adb_available():
        return False, "adb not found."

    if not also_save_on_phone:
        try:
            with open(save_path, "wb") as f:
                result = subprocess.run(
                    [ADB_BIN, "exec-out", "screencap", "-p"],
                    stdout=f, stderr=subprocess.PIPE, timeout=15, shell=False,
                )
            if result.returncode != 0:
                return False, result.stderr.decode(errors="ignore")
            return True, save_path
        except Exception as e:
            return False, str(e)

    import time as _time
    remote_dir = "/sdcard/Pictures/Screenshots"
    filename = f"blaze_{_time.strftime('%Y%m%d_%H%M%S')}.png"
    remote_path = f"{remote_dir}/{filename}"

    ok, out = _run("shell", "mkdir", "-p", remote_dir)
    if not ok:
        return False, f"Couldn't prepare storage on phone: {out}"

    ok, out = _run("shell", "screencap", "-p", remote_path)
    if not ok:
        return False, f"Couldn't capture screen: {out}"

    # Tell Android's media scanner about the new file so it shows up in
    # Gallery/Photos right away instead of only after a reboot or manual scan.
    _run("shell", "am", "broadcast", "-a",
         "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
         "-d", f"file://{remote_path}")

    ok, out = _run("pull", remote_path, save_path)
    if not ok:
        # Capture on the phone still succeeded even if the pull-to-laptop
        # step failed — say so rather than reporting total failure.
        return True, f"Saved to your phone's Gallery, but couldn't also copy it to this laptop: {out}"

    return True, f"{save_path} (also saved to your phone's Gallery)"


def screencap_png_bytes(serial: str | None = None, timeout: int = 8) -> bytes | None:
    """Grabs a single screencap and returns raw PNG bytes (no disk write) —
    the building block for an embedded live mirror: call this in a loop
    from a background thread and hand each frame to the UI. Cheaper than
    screenshot() since nothing touches the phone's Gallery or this
    laptop's filesystem, but it's still a fresh full-screen PNG encode on
    the phone every call, so realistically this gets you ~1-3 frames per
    second, not real video — good enough to see what's on screen and tap
    around, not for watching something play back smoothly. For that,
    scrcpy's actual H.264 stream (mirror_screen() below) is the right
    tool, just not one this method embeds inline."""
    ok, data = _run_bytes("exec-out", "screencap", "-p", serial=serial, timeout=timeout)
    if not ok or not data:
        return None
    return data


def mirror_screen() -> tuple[bool, str]:
    """Launches scrcpy for a live, interactive screen-mirror window with
    mouse/keyboard control. scrcpy is a SEPARATE free tool from adb, not
    part of platform-tools — install it yourself from
    github.com/Genymobile/scrcpy and make sure it's on PATH too."""
    if not SCRCPY_BIN:
        return False, "scrcpy not found. Install it separately (github.com/Genymobile/scrcpy) for screen mirroring."
    try:
        subprocess.Popen([SCRCPY_BIN], shell=False)
        return True, "Mirroring your phone screen now."
    except Exception as e:
        return False, str(e)


def open_screenrecord_stream(serial: str | None = None, size: str | None = None,
                              bit_rate: str = "4M") -> subprocess.Popen | None:
    """Launches `adb shell screenrecord`, streaming a raw H.264 elementary
    stream straight to this process's stdout — no file ever touches the
    phone's storage or this laptop's disk. This is the building block for
    genuine real-time embedded mirroring (continuous video), as opposed to
    screencap_png_bytes()'s ~1-3fps screenshot polling.

    Caller owns the returned Popen: read frames from `.stdout`, and
    terminate() it when done. Returns None if adb isn't available or the
    process fails to launch.

    IMPORTANT: Android's screenrecord silently stops itself after ~180s
    no matter what --time-limit says (a platform limit, not ours/adb's) —
    callers should watch for the process exiting and start a fresh one to
    keep the stream effectively continuous (a brief hiccup at the
    handoff, not a real interruption)."""
    if not adb_available():
        return None
    cmd = [ADB_BIN]
    if serial:
        cmd += ["-s", serial]
    cmd += ["exec-out", "screenrecord", "--output-format=h264", "--bit-rate", bit_rate]
    if size:
        cmd += ["--size", size]
    cmd += ["-"]
    try:
        return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, shell=False)
    except Exception:
        return None


# ── Apps ────────────────────────────────────────────────────────────────────

_KNOWN_PACKAGES = {
    "whatsapp": "com.whatsapp", "instagram": "com.instagram.android",
    "youtube": "com.google.android.youtube", "chrome": "com.android.chrome",
    "gmail": "com.google.android.gm", "camera": "com.android.camera",
    "spotify": "com.spotify.music", "gallery": "com.google.android.apps.photos",
    "settings": "com.android.settings", "maps": "com.google.android.apps.maps",
    "messages": "com.google.android.apps.messaging", "playstore": "com.android.vending",
}


def list_apps(third_party_only: bool = True) -> list[str]:
    args = ["shell", "pm", "list", "packages"]
    if third_party_only:
        args.append("-3")
    ok, out = _run(*args)
    if not ok:
        return []
    return [line.replace("package:", "").strip() for line in out.splitlines() if line.strip()]


def find_package(app_name: str) -> str | None:
    """Fuzzy-matches a spoken app name against installed packages first,
    falls back to a small table of common apps if the package name
    doesn't obviously contain the spoken name (e.g. 'camera' vs
    'com.android.camera' — no direct substring match there)."""
    packages = list_apps(third_party_only=True)
    needle = app_name.lower().replace(" ", "")
    for pkg in packages:
        if needle in pkg.lower():
            return pkg
    return _KNOWN_PACKAGES.get(app_name.lower())


def open_app(app_name: str) -> tuple[bool, str]:
    pkg = find_package(app_name)
    if not pkg:
        return False, f"Couldn't find an installed app matching '{app_name}' on your phone."
    ok, out = _run("shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1")
    if ok:
        return True, f"Opened {app_name} on your phone."
    return False, out


# ── Files ───────────────────────────────────────────────────────────────────

def push_file(local_path: str, remote_path: str = "/sdcard/Download/") -> tuple[bool, str]:
    return _run("push", local_path, remote_path)


def pull_file(remote_path: str, local_path: str) -> tuple[bool, str]:
    return _run("pull", remote_path, local_path)


def list_files(remote_dir: str = "/sdcard/") -> list[str]:
    ok, out = _run("shell", "ls", remote_dir)
    if not ok:
        return []
    return [l.strip() for l in out.splitlines() if l.strip()]


# ── Remote input ────────────────────────────────────────────────────────────

def tap(x: int, y: int, serial: str | None = None) -> tuple[bool, str]:
    return _run("shell", "input", "tap", str(x), str(y), serial=serial)


def swipe(x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300, serial: str | None = None) -> tuple[bool, str]:
    return _run("shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms), serial=serial)


def input_text(text: str, serial: str | None = None) -> tuple[bool, str]:
    # ADB's `input text` uses %s for spaces; anything fancier (emoji,
    # non-ASCII) is unreliable through this interface — known limitation.
    escaped = text.replace(" ", "%s")
    return _run("shell", "input", "text", escaped, serial=serial)


def press_key(keycode: str, serial: str | None = None) -> tuple[bool, str]:
    """keycode examples: HOME, BACK, POWER, VOLUME_UP, CAMERA — full list
    at developer.android.com/reference/android/view/KeyEvent"""
    return _run("shell", "input", "keyevent", keycode, serial=serial)


if __name__ == "__main__":
    print("adb available:", adb_available())
    print("device connected:", is_connected())
    if is_connected():
        print("device id:", connected_device_id())
        print("battery:", battery_status())
