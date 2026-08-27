#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

PATH = Path("Bridge/vex_bridge.py")
text = PATH.read_text(encoding="utf-8")

if '"version": "0.11.7.37"' not in text:
    raise SystemExit("v0.11.7.38 expected Bridge v0.11.7.37 source")

choose_marker = "def _choose_ollama_model() -> str | None:\n"
choose_at = text.find(choose_marker)
if choose_at < 0:
    raise SystemExit("_choose_ollama_model marker missing")

# Field failure on v0.11.7.37: _choose_ollama_model referenced
# _cognition_capacity, but the assembled Windows chain did not contain its
# definition. Install a dependency-free Windows-safe fallback before chooser.
if "def _cognition_capacity() -> dict:" not in text:
    helper = r'''
def _cognition_capacity() -> dict:
    total = 0
    available = 0
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            total = int(stat.ullTotalPhys)
            available = int(stat.ullAvailPhys)
    except Exception:
        pass

    cpu = max(1, int(os.cpu_count() or 1))
    total_gb = total / (1024 ** 3) if total else 0.0
    available_gb = available / (1024 ** 3) if available else 0.0

    # Conservative CPU/RAM-only sizing. The field machine has historically
    # used the lite local model, so never require GPU discovery to answer chat.
    if total_gb >= 20.0 and cpu >= 8:
        tier, max_billions = "strong", 8.0
    elif total_gb >= 9.0:
        tier, max_billions = "balanced", 4.0
    else:
        tier, max_billions = "lite", 2.0

    pressure = "normal"
    if available_gb and available_gb < 3.0:
        pressure = "memory"
        max_billions = min(max_billions, 2.0)
    elif available_gb and available_gb < 6.0:
        max_billions = min(max_billions, 4.0)

    return {
        "tier": tier,
        "pressure": pressure,
        "max_billions": max_billions,
        "memory_total_gb": round(total_gb, 1),
        "memory_available_gb": round(available_gb, 1),
        "cpu_logical": cpu,
        "gpu_name": None,
        "gpu_vram_gb": 0.0,
        "gpu_source": None,
        "art_running": False,
    }


'''
    text = text[:choose_at] + helper + text[choose_at:]

text = text.replace('"version": "0.11.7.37"', '"version": "0.11.7.38"', 1)
PATH.write_text(text, encoding="utf-8")
compile(text, str(PATH), "exec")

capacity_at = text.find("def _cognition_capacity() -> dict:")
choose_at = text.find(choose_marker)
if capacity_at < 0 or choose_at < 0 or capacity_at > choose_at:
    raise SystemExit("cognition capacity must be defined before model chooser")
for marker in [
    '"version": "0.11.7.38"',
    "def _cognition_capacity() -> dict:",
    "GlobalMemoryStatusEx",
    "def _start_ollama_if_needed()",
]:
    if marker not in text:
        raise SystemExit(f"missing v0.11.7.38 marker: {marker}")

print("Applied v0.11.7.38 cognition capacity hotfix")
