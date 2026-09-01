#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

INSTALLER = Path("Tools/VexAgentRuntimeInstall.py")
installer = INSTALLER.read_text(encoding="utf-8")

anchor = "\n\ndef wait_direct_memory(seconds: int = 30) -> dict:\n"
helper = r'''

def ollama_executable() -> str | None:
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


def ollama_models(timeout: float = 4.0) -> list[str]:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open("http://127.0.0.1:11434/api/tags", timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
    except Exception:
        return []
    models = []
    if isinstance(value, dict):
        for item in value.get("models") or []:
            if isinstance(item, dict):
                name = str(item.get("name") or item.get("model") or "").strip()
                if name:
                    models.append(name)
    return models


def wait_ollama_model(seconds: int = 90) -> dict:
    """Prove the real Ollama HTTP API and a deployed model before Bridge cognition checks."""
    deadline = time.time() + seconds
    exe = ollama_executable()
    launched = False
    last_models: list[str] = []
    while time.time() < deadline:
        models = ollama_models(timeout=3.0)
        if models:
            preferred = next((m for m in models if m.lower() == "vex-qwen3-4b:latest"), None)
            if preferred is None:
                preferred = next((m for m in models if "qwen3" in m.lower() and "4b" in m.lower()), None)
            return {"ok": True, "model": preferred or models[0], "models": models}
        last_models = models
        if not launched:
            if not exe:
                raise RuntimeError("Ollama is installed incompletely: ollama.exe was not found.")
            try:
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                subprocess.Popen(
                    [exe, "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=flags,
                )
            except Exception:
                # The desktop Ollama app may already own the server. Poll the API;
                # a genuine failure is reported below rather than guessed here.
                pass
            launched = True
        time.sleep(1.0)
    if exe:
        raise RuntimeError(
            "Ollama started but its local API exposed no models. Open Ollama and verify the Vex model is installed."
        )
    raise RuntimeError("Ollama local API did not become ready and ollama.exe was not found.")
'''

if "def wait_ollama_model(" not in installer:
    if anchor not in installer:
        raise SystemExit("v0.12 Ollama preflight could not find installer helper anchor")
    installer = installer.replace(anchor, helper + anchor, 1)

main_anchor = "        wait_direct_memory()\n\n        # Preserve APPDATA/LOCALAPPDATA private configuration, pairing, memory DB,\n"
main_replacement = "        wait_direct_memory()\n        ollama = wait_ollama_model()\n\n        # Preserve APPDATA/LOCALAPPDATA private configuration, pairing, memory DB,\n"
if "        ollama = wait_ollama_model()\n" not in installer:
    if main_anchor not in installer:
        raise SystemExit("v0.12 Ollama preflight could not find main install anchor")
    installer = installer.replace(main_anchor, main_replacement, 1)

INSTALLER.write_text(installer, encoding="utf-8")
compile(installer, str(INSTALLER), "exec")

for marker in [
    "def ollama_executable() -> str | None:",
    "def ollama_models(timeout: float = 4.0) -> list[str]:",
    "def wait_ollama_model(seconds: int = 90) -> dict:",
    'http://127.0.0.1:11434/api/tags',
    'ollama = wait_ollama_model()',
]:
    if marker not in installer:
        raise SystemExit(f"v0.12 Ollama preflight missing marker: {marker}")

print("Applied v0.12 direct Ollama API/model preflight")
