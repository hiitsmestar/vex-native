#!/usr/bin/env python3
from pathlib import Path


def replace_function(text: str, name: str, replacement: str) -> str:
    start = text.find(f"def {name}(")
    if start < 0:
        raise SystemExit(f"missing function: {name}")
    end = text.find("\n\ndef ", start + 10)
    if end < 0:
        raise SystemExit(f"could not find end of function: {name}")
    return text[:start] + replacement.rstrip() + text[end:]


# ---------------------------------------------------------------------------
# Standalone Art Worker: keep CPU-only / 8 GB hosts responsive and make the
# worker the sole owner of ComfyUI.
# ---------------------------------------------------------------------------
worker_path = Path("Tools/VexArtWorker.py")
worker = worker_path.read_text(encoding="utf-8")
if 'VERSION = "0.10.0"' not in worker:
    raise SystemExit("VexArtWorker v0.10.0 marker missing")
worker = worker.replace('VERSION = "0.10.0"', 'VERSION = "0.10.2"', 1)

memory_helper = r'''
def _memory_profile() -> dict:
    result = {
        "total_physical_mb": None,
        "available_physical_mb": None,
        "total_commit_mb": None,
        "available_commit_mb": None,
        "low_memory": False,
    }
    if os.name != "nt":
        return result
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
            result["total_physical_mb"] = int(status.ullTotalPhys // (1024 * 1024))
            result["available_physical_mb"] = int(status.ullAvailPhys // (1024 * 1024))
            result["total_commit_mb"] = int(status.ullTotalPageFile // (1024 * 1024))
            result["available_commit_mb"] = int(status.ullAvailPageFile // (1024 * 1024))
            result["low_memory"] = result["total_physical_mb"] <= 12 * 1024
    except Exception:
        pass
    return result
'''
marker = "\n\ndef _start_process(args: list[str]) -> subprocess.Popen:\n"
if marker not in worker:
    raise SystemExit("Art Worker start-process marker missing")
worker = worker.replace(marker, "\n\n" + memory_helper.strip() + marker, 1)

worker = replace_function(worker, "_start_process", r'''def _start_process(args: list[str]) -> subprocess.Popen:
    WORKER_ROOT.mkdir(parents=True, exist_ok=True)
    log = open(LOG_PATH, "a", encoding="utf-8", errors="replace")
    env = os.environ.copy()
    # On the 8 GB CPU node, rendering must never starve Remote Support or the UI.
    threads = max(2, min(4, int(os.cpu_count() or 2) // 2 or 2))
    for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[key] = str(threads)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    flags |= getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
    return subprocess.Popen(
        args,
        cwd=str(COMFY_DIR),
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=flags,
        env=env,
    )
''')

worker = replace_function(worker, "ensure_comfy", r'''def ensure_comfy() -> tuple[bool, dict]:
    global _COMFY_PROCESS, _COMFY_OWNED
    # Modular ownership rule: Bridge/watchdog/manual ComfyUI copies may not be
    # silently adopted. One renderer process, one owner.
    if comfy_health():
        if _COMFY_OWNED and _COMFY_PROCESS is not None:
            return True, {"mode": "worker-owned", "owned": True, "memory": _memory_profile()}
        return False, {
            "error": "ComfyUI is already running outside Vex Art Worker. Stop the other ComfyUI process first.",
            "error_class": "ArtOwnershipConflict",
            "memory": _memory_profile(),
        }

    state = installed_state()
    if not state["installed"] or not state["checkpoint_exists"]:
        return False, {"error": "Vex Art installation is incomplete", **state}

    profile = _memory_profile()
    probe = _torch_probe()
    mode = "gpu" if probe.get("ok") and probe.get("cuda") else "cpu-lowmem"
    base = [str(ART_PYTHON), "main.py", "--listen", "127.0.0.1", "--port", "8188", "--disable-auto-launch"]

    if mode == "cpu-lowmem":
        # Do NOT force the fp16 checkpoint to fp32 on an 8 GB host. That was the
        # main memory explosion in v0.10.0. Try strict low-memory modes first.
        attempts = [
            base + ["--cpu", "--lowvram", "--disable-smart-memory", "--disable-xformers", "--preview-method", "none"],
            base + ["--cpu", "--lowvram", "--disable-xformers", "--preview-method", "none"],
            base + ["--cpu", "--disable-xformers", "--preview-method", "none"],
        ]
    else:
        attempts = [base + ["--preview-method", "none"], base]

    for number, args in enumerate(attempts, start=1):
        try:
            _COMFY_PROCESS = _start_process(args)
            _COMFY_OWNED = True
            deadline = time.time() + (300 if mode == "cpu-lowmem" else 210)
            while time.time() < deadline:
                if comfy_health(timeout=1.5):
                    return True, {
                        "mode": mode,
                        "owned": True,
                        "attempt": number,
                        "torch": probe,
                        "memory": profile,
                    }
                if _COMFY_PROCESS.poll() is not None:
                    break
                time.sleep(1.5)
        except Exception as exc:
            if number == len(attempts):
                return False, {"error": f"{exc.__class__.__name__}: {exc}", "mode": mode, "torch": probe, "memory": profile}
        try:
            if _COMFY_PROCESS and _COMFY_PROCESS.poll() is None:
                _COMFY_PROCESS.terminate()
                _COMFY_PROCESS.wait(timeout=8)
        except Exception:
            pass
        _COMFY_PROCESS = None
        _COMFY_OWNED = False

    return False, {
        "error": "ComfyUI did not become ready in any low-memory launch mode",
        "mode": mode,
        "torch": probe,
        "memory": profile,
        "log_tail": _read_log_tail(),
    }
''')

worker = replace_function(worker, "_dimensions", r'''def _dimensions(orientation: str, mode: str, test: bool) -> tuple[int, int]:
    cpu = mode != "gpu"
    if test:
        return (384, 384) if cpu else (512, 512)
    low = str(orientation or "portrait").lower()
    if low in {"square", "1:1"}:
        return (512, 512) if cpu else (1024, 1024)
    if low in {"landscape", "wide", "horizontal"}:
        return (640, 448) if cpu else (1216, 832)
    return (448, 640) if cpu else (832, 1216)
''')

old_steps = "workflow = _workflow(prompt, checkpoint, width, height, seed, 4 if test else 6)"
if old_steps not in worker:
    raise SystemExit("Art Worker step-count marker missing")
worker = worker.replace(old_steps, "workflow = _workflow(prompt, checkpoint, width, height, seed, 3 if test else 5)", 1)

# Expose the machine memory profile in status without leaking paths or personal data.
old_headless = '''    state["mode"] = "gpu" if probe.get("ok") and probe.get("cuda") else ("cpu" if state["installed"] else "missing")\n    state["ok"] = bool(state["installed"] and state["checkpoint_exists"])\n    return sanitized(state)\n'''
new_headless = '''    state["mode"] = "gpu" if probe.get("ok") and probe.get("cuda") else ("cpu-lowmem" if state["installed"] else "missing")\n    memory = _memory_profile()\n    state.update({\n        "memory_total_mb": memory.get("total_physical_mb"),\n        "memory_available_mb": memory.get("available_physical_mb"),\n        "commit_total_mb": memory.get("total_commit_mb"),\n        "commit_available_mb": memory.get("available_commit_mb"),\n        "low_memory": memory.get("low_memory"),\n    })\n    state["ok"] = bool(state["installed"] and state["checkpoint_exists"])\n    return sanitized(state)\n'''
if old_headless not in worker:
    raise SystemExit("Art Worker headless status marker missing")
worker = worker.replace(old_headless, new_headless, 1)
old_allowed = '"mode", "image_bytes", "elapsed_seconds"}'
new_allowed = '"mode", "image_bytes", "elapsed_seconds", "memory_total_mb", "memory_available_mb", "commit_total_mb", "commit_available_mb", "low_memory"}'
if old_allowed not in worker:
    raise SystemExit("Art Worker sanitized-key marker missing")
worker = worker.replace(old_allowed, new_allowed, 1)

worker_path.write_text(worker, encoding="utf-8")


# ---------------------------------------------------------------------------
# Bridge: finish the modular split. The Bridge may report art health, but it may
# no longer start/restart ComfyUI, unload cognition for art, or repair art. The
# standalone VexArtWorker owns that lifecycle.
# ---------------------------------------------------------------------------
bridge_path = Path("Bridge/vex_bridge.py")
bridge = bridge_path.read_text(encoding="utf-8")
for required in ("def _ensure_art_comfy(", "def _art_release_cognition_memory(", "def _sr_repair_art("):
    if required not in bridge:
        raise SystemExit(f"patched Bridge missing expected marker: {required}")

insert_at = bridge.rfind('\nif __name__ == "__main__":')
if insert_at < 0:
    raise SystemExit("Bridge __main__ marker missing")

ownership = r'''

# v0.10.2 MODULAR ART OWNERSHIP ---------------------------------------------
# The core Bridge can observe the renderer, but only VexArtWorker.exe may own
# its process lifecycle. This intentionally overrides older integrated helpers.
MODULAR_ART_EXTERNAL = True


def _ensure_art_comfy(*args, **kwargs) -> tuple[bool, str | None]:
    return False, "Art lifecycle is external in modular mode. Open VexArtWorker.exe."


def _art_release_cognition_memory(*args, **kwargs) -> bool:
    # A Bridge chat turn must never evict Ollama merely because art is installed.
    return False


def _art_recover_dll_runtime(*args, **kwargs):
    return False, "Art runtime repair belongs to VexArtWorker/Doctor in modular mode."


def _sr_repair_art(force: bool = False) -> tuple[bool, str]:
    # Self-heal may report health, but must not resurrect ComfyUI behind the
    # standalone worker's back.
    if not _sr_art_installed():
        return True, "external art worker is not installed on this node"
    if _art_comfy_health(timeout=0.8):
        return True, "external Art Worker ComfyUI is running"
    return True, "external Art Worker owns ComfyUI; Bridge restart disabled"
'''
bridge = bridge[:insert_at] + ownership + bridge[insert_at:]

# Surface the actual modular build version where the patched status endpoint
# still carries an older compatibility label.
bridge = bridge.replace('"version": "0.8.0"', '"version": "0.10.2"')
bridge_path.write_text(bridge, encoding="utf-8")

full_path = Path("Bridge/vex_bridge_full.py")
full = full_path.read_text(encoding="utf-8")
if 'VERSION = "0.9.8"' in full:
    full = full.replace('VERSION = "0.9.8"', 'VERSION = "0.10.2"', 1)
elif 'VERSION = "0.10.2"' not in full:
    raise SystemExit("Bridge launcher v0.9.8 marker missing")
full_path.write_text(full, encoding="utf-8")

checks = [
    'VERSION = "0.10.2"',
    '"--lowvram"',
    '"--disable-smart-memory"',
    'BELOW_NORMAL_PRIORITY_CLASS',
    'ArtOwnershipConflict',
]
final_worker = worker_path.read_text(encoding="utf-8")
for check in checks:
    if check not in final_worker:
        raise SystemExit(f"v0.10.2 Art Worker missing marker: {check}")
final_bridge = bridge_path.read_text(encoding="utf-8")
for check in ("MODULAR_ART_EXTERNAL = True", "Bridge restart disabled", "def _art_release_cognition_memory(*args, **kwargs)"):
    if check not in final_bridge:
        raise SystemExit(f"v0.10.2 Bridge missing marker: {check}")

print("Applied v0.10.2 modular art ownership + 8 GB CPU low-memory patch")
