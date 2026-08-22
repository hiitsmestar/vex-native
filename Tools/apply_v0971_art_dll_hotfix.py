#!/usr/bin/env python3
from pathlib import Path

bridge_path = Path("Bridge/vex_bridge.py")
text = bridge_path.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global text
    if old not in text:
        raise SystemExit(f"{label}: expected source block not found")
    text = text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# v0.9.7.1 field hotfix for Windows PyTorch/ComfyUI c10.dll WinError 1114.
#
# The v0.9.7 self-repair routine could repair the DLL runtime when the background
# supervisor reached it, but a user-started render called _ensure_art_comfy()
# directly and returned the startup error before that dependency repair path ran.
# This hotfix puts the dependency-aware recovery directly in the render path and
# makes the Windows art subprocess environment less vulnerable to global Conda
# DLL/PATH contamination.
# ---------------------------------------------------------------------------

marker = "def _art_torch_smoke() -> tuple[bool, str]:\n"
if marker not in text:
    raise SystemExit("v0.9.7 torch smoke marker missing")
helpers = r'''def _art_clean_env() -> dict:
    env = dict(os.environ)
    raw_path = env.get("PATH", "")
    cleaned = []
    for entry in raw_path.split(os.pathsep):
        lower = entry.lower()
        if any(token in lower for token in ["anaconda", "miniconda", "\\conda\\", "/conda/"]):
            continue
        cleaned.append(entry)
    env["PATH"] = os.pathsep.join(cleaned)
    env["PYTHONNOUSERSITE"] = "1"
    env.pop("PYTHONHOME", None)
    return env


def _art_vcredist_present() -> bool:
    try:
        import ctypes
        root = Path(os.environ.get("WINDIR", r"C:\\Windows")) / "System32"
        needed = [root / "vcruntime140.dll", root / "msvcp140.dll"]
        if not all(p.exists() for p in needed):
            return False
        for name in ["vcruntime140.dll", "msvcp140.dll"]:
            ctypes.WinDLL(str(root / name))
        return True
    except Exception:
        return False


def _art_try_vcredist_repair() -> tuple[bool, str]:
    if _art_vcredist_present():
        return True, "Microsoft Visual C++ runtime is present"
    try:
        import subprocess
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        result = subprocess.run(
            ["winget", "install", "--id", "Microsoft.VCRedist.2015+.x64", "--exact",
             "--silent", "--accept-package-agreements", "--accept-source-agreements"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=600,
            creationflags=flags,
        )
        detail = str(result.stdout or "")[-3500:]
        ok = result.returncode == 0 and _art_vcredist_present()
        return ok, detail or ("Visual C++ runtime installed" if ok else "Visual C++ runtime repair did not complete")
    except Exception as exc:
        return False, f"Visual C++ runtime repair unavailable: {exc}"


def _art_repair_pytorch_280() -> tuple[bool, str]:
    """Known-stable Windows CPU fallback for current c10.dll 1114 failures."""
    try:
        import subprocess
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        _art_release_cognition_memory()
        command = [
            str(ART_PYTHON), "-m", "pip", "install", "--upgrade", "--force-reinstall", "--no-cache-dir",
            "torch==2.8.0", "torchvision==0.23.0", "torchaudio==2.8.0",
            "--index-url", "https://download.pytorch.org/whl/cpu",
        ]
        result = subprocess.run(
            command,
            cwd=str(ART_ROOT),
            env=_art_clean_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=1800,
            creationflags=flags,
        )
        detail = str(result.stdout or "")[-7000:]
        if result.returncode != 0:
            return False, f"Pinned PyTorch 2.8 CPU install failed: {detail[-2200:]}"
        ok, smoke = _art_torch_smoke()
        if ok:
            return True, f"PyTorch 2.8 CPU runtime verified: {smoke[-1200:]}"
        return False, f"Pinned PyTorch installed but import still fails: {smoke[-2200:]}"
    except Exception as exc:
        return False, f"Pinned PyTorch repair failed: {exc}"


def _art_recover_dll_runtime(detail: str = "", force: bool = False) -> tuple[bool, str]:
    if not _art_runtime_repair_needed(detail):
        return False, "startup failure is not the recognized PyTorch DLL error"

    _art_release_cognition_memory()
    smoke_ok, smoke = _art_torch_smoke()
    if smoke_ok:
        return True, "torch imports after freeing cognition memory"

    vc_ok, vc_detail = _art_try_vcredist_repair()
    if vc_ok:
        smoke_ok, smoke = _art_torch_smoke()
        if smoke_ok:
            return True, "repaired/verified Microsoft Visual C++ runtime and torch now imports"

    pinned_ok, pinned_detail = _art_repair_pytorch_280()
    if pinned_ok:
        _learning_queue_topic(
            "Windows PyTorch c10.dll WinError 1114: Visual C++ runtime, PATH conflicts, and PyTorch 2.9 versus 2.8",
            reason="self-repair-learn", priority=72,
        )
        return True, pinned_detail

    generic_ok, generic_detail = _art_repair_cpu_torch(force=force)
    if generic_ok:
        return True, generic_detail
    return False, (
        f"torch smoke failed: {smoke[-1200:]} | VC runtime: {vc_detail[-900:]} | "
        f"PyTorch 2.8 fallback: {pinned_detail[-1400:]} | generic repair: {generic_detail[-1400:]}"
    )


'''
text = text.replace(marker, helpers + marker, 1)

# Torch smoke uses only VexArt's intended DLL search environment.
old_smoke = '''            cwd=str(ART_ROOT),\n            stdout=subprocess.PIPE,\n            stderr=subprocess.STDOUT,\n            text=True,\n            timeout=50,\n            creationflags=flags,\n'''
new_smoke = '''            cwd=str(ART_ROOT),\n            env=_art_clean_env(),\n            stdout=subprocess.PIPE,\n            stderr=subprocess.STDOUT,\n            text=True,\n            timeout=50,\n            creationflags=flags,\n'''
replace_once(old_smoke, new_smoke, "sanitized torch smoke environment")

# The CPU/CUDA probe introduced in v0.9.6.1 also needs the clean environment.
old_mode = '''            cwd=str(ART_COMFY_DIR),\n            stdout=subprocess.PIPE,\n            stderr=subprocess.STDOUT,\n            text=True,\n            timeout=25,\n            creationflags=flags,\n'''
new_mode = '''            cwd=str(ART_COMFY_DIR),\n            env=_art_clean_env(),\n            stdout=subprocess.PIPE,\n            stderr=subprocess.STDOUT,\n            text=True,\n            timeout=25,\n            creationflags=flags,\n'''
replace_once(old_mode, new_mode, "sanitized art runtime probe")

# v0.9.6.1's launcher includes stdin=DEVNULL; match that exact live source.
old_popen = '''                cwd=str(ART_COMFY_DIR),\n                stdin=subprocess.DEVNULL,\n                stdout=log,\n                stderr=subprocess.STDOUT,\n                creationflags=flags,\n'''
new_popen = '''                cwd=str(ART_COMFY_DIR),\n                env=_art_clean_env(),\n                stdin=subprocess.DEVNULL,\n                stdout=log,\n                stderr=subprocess.STDOUT,\n                creationflags=flags,\n'''
replace_once(old_popen, new_popen, "sanitized ComfyUI environment")

# A render request now triggers dependency recovery immediately.
old_run = '''    ok, error = _ensure_art_comfy()\n    if not ok:\n        with _ART_JOB_LOCK:\n            _ART_JOBS[job_id]["status"] = "error"\n            _ART_JOBS[job_id]["error"] = error\n        return\n'''
new_run = '''    ok, error = _ensure_art_comfy()\n    if not ok and _art_runtime_repair_needed(str(error or "")):\n        with _ART_JOB_LOCK:\n            _ART_JOBS[job_id]["status"] = "repairing-art-runtime"\n        repaired, repair_detail = _art_recover_dll_runtime(str(error or ""), force=False)\n        if repaired:\n            ok, error = _ensure_art_comfy()\n        else:\n            error = f"Automatic art DLL repair did not finish: {repair_detail}"\n    if not ok:\n        with _ART_JOB_LOCK:\n            _ART_JOBS[job_id]["status"] = "error"\n            _ART_JOBS[job_id]["error"] = error\n        return\n'''
replace_once(old_run, new_run, "direct render DLL recovery")

# Background self-heal shares the same stronger dependency path.
old_dep = '''    detail = str(error or "ComfyUI restart failed")\n    if _art_runtime_repair_needed(detail):\n        smoke_ok, smoke = _art_torch_smoke()\n        if not smoke_ok:\n            repaired, repair_detail = _art_repair_cpu_torch(force=force)\n            if repaired:\n                ok2, error2 = _ensure_art_comfy()\n                if ok2:\n                    _learning_queue_topic("ComfyUI CPU-only Windows startup reliability and memory management", reason="self-repair-learn", priority=60)\n                    return True, "repaired CPU PyTorch runtime and restarted ComfyUI"\n                return False, f"PyTorch repaired but ComfyUI still failed: {error2}"\n            return False, f"ComfyUI torch runtime failure. {repair_detail}"\n        # Torch imports now, so the original failure was likely transient memory\n        # pressure. Give ComfyUI one clean retry with cognition unloaded.\n        ok3, error3 = _ensure_art_comfy()\n        if ok3:\n            return True, "recovered transient PyTorch DLL startup failure"\n        return False, str(error3 or detail)\n    return False, detail\n'''
new_dep = '''    detail = str(error or "ComfyUI restart failed")\n    if _art_runtime_repair_needed(detail):\n        repaired, repair_detail = _art_recover_dll_runtime(detail, force=force)\n        if repaired:\n            ok2, error2 = _ensure_art_comfy()\n            if ok2:\n                _learning_queue_topic("ComfyUI CPU-only Windows startup reliability and memory management", reason="self-repair-learn", priority=60)\n                return True, "repaired PyTorch/Windows DLL runtime and restarted ComfyUI"\n            return False, f"DLL runtime repaired but ComfyUI still failed: {error2}"\n        return False, f"ComfyUI torch runtime failure. {repair_detail}"\n    return False, detail\n'''
replace_once(old_dep, new_dep, "stronger background art recovery")

bridge_path.write_text(text, encoding="utf-8")

full_path = Path("Bridge/vex_bridge_full.py")
full = full_path.read_text(encoding="utf-8")
if 'VERSION = "0.9.7"' not in full:
    raise SystemExit("v0.9.7 launcher marker missing")
full = full.replace('VERSION = "0.9.7"', 'VERSION = "0.9.7.1"', 1)
full_path.write_text(full, encoding="utf-8")

checks = [
    "def _art_clean_env", "def _art_try_vcredist_repair", "torch==2.8.0",
    "def _art_recover_dll_runtime", '"repairing-art-runtime"', "env=_art_clean_env()",
]
final = bridge_path.read_text(encoding="utf-8")
for check in checks:
    if check not in final:
        raise SystemExit(f"v0.9.7.1 missing marker: {check}")
if 'VERSION = "0.9.7.1"' not in full_path.read_text(encoding="utf-8"):
    raise SystemExit("v0.9.7.1 launcher version missing")

print("Applied Vex v0.9.7.1 direct render WinError 1114/c10.dll recovery hotfix")
