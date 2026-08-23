#!/usr/bin/env python3
from pathlib import Path

path = Path("Bridge/vex_bridge.py")
text = path.read_text(encoding="utf-8")

start = text.find("def _cognition_capacity() -> dict:\n")
if start < 0:
    raise SystemExit("v0.10.9 cognition capacity marker missing")
end = text.find("\n\ndef ", start + 20)
if end < 0:
    raise SystemExit("v0.10.9 cognition capacity end marker missing")

replacement = r'''def _cognition_capacity() -> dict:
    # Do not call _resource_snapshot() here. That snapshot includes
    # _choose_ollama_model(), which calls this function and would recurse.
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

        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            total = int(status.ullTotalPhys)
            available = int(status.ullAvailPhys)
    except Exception:
        pass

    cpu = max(1, int(os.cpu_count() or 1))
    total_gb = total / (1024 ** 3) if total else 0.0
    available_gb = available / (1024 ** 3) if available else 0.0
    gpu = _cognition_gpu_profile()
    vram_gb = int(gpu.get("vram_mb") or 0) / 1024.0

    art_running = False
    try:
        with _ART_JOB_LOCK:
            art_running = any(
                isinstance(job, dict)
                and str(job.get("status") or "").lower() in {"queued", "starting", "rendering"}
                for job in _ART_JOBS.values()
            )
    except Exception:
        art_running = False

    if (vram_gb >= 11.0 and total_gb >= 24.0) or (total_gb >= 32.0 and cpu >= 12):
        tier, max_billions = "max", 14.0
    elif (vram_gb >= 7.0 and total_gb >= 16.0) or (total_gb >= 20.0 and cpu >= 8):
        tier, max_billions = "strong", 8.0
    elif total_gb >= 9.0:
        tier, max_billions = "balanced", 4.0
    else:
        tier, max_billions = "lite", 2.0

    pressure = "normal"
    if art_running:
        pressure = "art"
        max_billions = min(max_billions, 4.0 if total_gb >= 16.0 else 2.0)
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
        "gpu_name": gpu.get("name"),
        "gpu_vram_gb": round(vram_gb, 1),
        "gpu_source": gpu.get("source"),
        "art_running": art_running,
    }'''

text = text[:start] + replacement + text[end:]
path.write_text(text, encoding="utf-8")

final = path.read_text(encoding="utf-8")
if "snap = _resource_snapshot()" in final[start:start + len(replacement) + 500]:
    raise SystemExit("recursive cognition resource call survived")
compile(final, str(path), "exec")
print("Applied v0.10.9.2 adaptive cognition recursion hotfix")
