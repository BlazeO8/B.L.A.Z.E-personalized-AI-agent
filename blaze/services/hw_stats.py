"""
hw_stats.py — best-effort CPU/GPU usage + temperature reader.

Honest caveats up front, since these bite people silently otherwise:

- CPU % is reliable everywhere (psutil.cpu_percent()).
- CPU temperature is NOT reliable on Windows. psutil.sensors_temperatures()
  is a Linux/macOS API and returns an empty dict on most Windows machines
  because Windows doesn't expose a standard sensor API the way Linux does.
  Getting real CPU temp on Windows generally means talking to
  LibreHardwareMonitor (via its WMI namespace) or a vendor SDK. This module
  tries LibreHardwareMonitor's WMI namespace if `wmi` is installed and the
  LHM service is running, and returns None if it isn't — it does NOT fake
  a number.
- GPU usage/temp requires a vendor library. This module tries `pynvml`
  (NVIDIA only) and falls back to `GPUtil` (also NVIDIA-only, wraps nvidia-smi).
  If you have an AMD or Intel GPU, both will silently return None — that's
  a real gap, not a bug, and would need pyadl (AMD) or intel_gpu_top parsing
  to close.

Every getter returns None when it can't get a real reading. The caller
(orb widget) is responsible for showing "N/A" rather than a fabricated
number — don't patch that by inventing a fallback value here.
"""

from __future__ import annotations
import psutil
from typing import Optional

# --- optional deps, all soft-imported -------------------------------------

try:
    import pynvml
    pynvml.nvmlInit()
    _NVML_OK = True
except Exception:
    _NVML_OK = False

try:
    import GPUtil
    _GPUTIL_OK = True
except Exception:
    _GPUTIL_OK = False

try:
    import wmi
    _WMI_OK = True
except Exception:
    _WMI_OK = False


def cpu_percent() -> float:
    """Non-blocking CPU usage. Call this on your own poll interval —
    passing interval=None means it compares against the last call,
    so the first call after import will always read 0.0."""
    return psutil.cpu_percent(interval=None)


def cpu_temp_c() -> Optional[float]:
    """Best-effort CPU temperature in Celsius. Returns None if unavailable."""
    # Linux / macOS path
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            for key in ("coretemp", "k10temp", "cpu_thermal", "acpitz"):
                if key in temps and temps[key]:
                    return round(temps[key][0].current, 1)
            # fall back to first available sensor group
            first = next(iter(temps.values()))
            if first:
                return round(first[0].current, 1)
    except Exception:
        pass

    # Windows path via LibreHardwareMonitor's WMI namespace, if present.
    # Requires LibreHardwareMonitor running with "Remote Web Server" /
    # WMI provider enabled. This is opt-in on the user's machine, not
    # something we can assume is set up.
    if _WMI_OK:
        try:
            w = wmi.WMI(namespace="root\\LibreHardwareMonitor")
            sensors = w.Sensor()
            for s in sensors:
                if s.SensorType == "Temperature" and "CPU" in (s.Name or ""):
                    return round(float(s.Value), 1)
        except Exception:
            pass

    return None


def gpu_stats() -> dict:
    """Returns {'usage_pct': float|None, 'temp_c': float|None, 'name': str|None}."""
    if _NVML_OK:
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode()
            return {"usage_pct": float(util.gpu), "temp_c": float(temp), "name": name}
        except Exception:
            pass

    if _GPUTIL_OK:
        try:
            gpus = GPUtil.getGPUs()
            if gpus:
                g = gpus[0]
                return {
                    "usage_pct": round(g.load * 100, 1),
                    "temp_c": g.temperature,
                    "name": g.name,
                }
        except Exception:
            pass

    return {"usage_pct": None, "temp_c": None, "name": None}


def snapshot() -> dict:
    """One-shot read of everything the orb widget's corner graphs need."""
    gpu = gpu_stats()
    return {
        "cpu_pct": cpu_percent(),
        "cpu_temp_c": cpu_temp_c(),
        "gpu_pct": gpu["usage_pct"],
        "gpu_temp_c": gpu["temp_c"],
        "gpu_name": gpu["name"],
    }


if __name__ == "__main__":
    import time
    print("Reading hardware stats for 5 seconds (Ctrl+C to stop)...")
    print("If GPU/CPU-temp show None, see the module docstring for why.\n")
    try:
        while True:
            print(snapshot())
            time.sleep(1)
    except KeyboardInterrupt:
        pass
