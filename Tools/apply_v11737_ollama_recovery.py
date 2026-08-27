#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

PATH = Path("Bridge/vex_bridge.py")
text = PATH.read_text(encoding="utf-8")

start = text.find("def _ollama_models() -> list[str]:\n")
if start < 0:
    raise SystemExit("_ollama_models marker missing")
end = text.find("\n\ndef _choose_ollama_model()", start)
if end < 0:
    raise SystemExit("_ollama_models end marker missing")

replacement = r'''_OLLAMA_RECOVERY_LOCK = threading.Lock()
_OLLAMA_RECOVERY_LAST = 0.0


def _ollama_executable() -> str | None:
    import shutil
    direct = shutil.which("ollama") or shutil.which("ollama.exe")
    if direct:
        return direct
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    candidates = [
        local / "Programs" / "Ollama" / "ollama.exe",
        local / "Ollama" / "ollama.exe",
        Path(os.environ.get("ProgramFiles", r"C:\\Program Files")) / "Ollama" / "ollama.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def _start_ollama_if_needed() -> bool:
    global _OLLAMA_RECOVERY_LAST
    import subprocess
    now = time.time()
    if now - _OLLAMA_RECOVERY_LAST < 20:
        return False
    if not _OLLAMA_RECOVERY_LOCK.acquire(blocking=False):
        return False
    try:
        _OLLAMA_RECOVERY_LAST = time.time()
        exe = _ollama_executable()
        if not exe:
            return False
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
        return True
    except Exception:
        return False
    finally:
        _OLLAMA_RECOVERY_LOCK.release()


def _ollama_models() -> list[str]:
    import requests
    def fetch() -> list[str]:
        try:
            response = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=2.0)
            if response.status_code >= 400:
                return []
            payload = response.json()
            result = []
            for item in payload.get("models") or []:
                name = str(item.get("name") or item.get("model") or "").strip()
                if name:
                    result.append(name)
            return result
        except Exception:
            return []
    models = fetch()
    if models:
        return models
    if _start_ollama_if_needed():
        for _ in range(8):
            time.sleep(1)
            models = fetch()
            if models:
                return models
    return []
'''

text = text[:start] + replacement + text[end:]
text = text.replace('"version": "0.11.7.34"', '"version": "0.11.7.37"')
PATH.write_text(text, encoding="utf-8")
compile(text, str(PATH), "exec")
for marker in ["def _start_ollama_if_needed()", "ollama.exe", '"version": "0.11.7.37"']:
    if marker not in text:
        raise SystemExit(f"missing marker: {marker}")
print("Applied v0.11.7.37 Ollama self-recovery")
