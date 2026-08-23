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


bridge_path = Path("Bridge/vex_bridge.py")
text = bridge_path.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# Hardware-aware cognition. Fit is based on real local headroom, not a hardcoded
# assumption that every PC should run the same model. The phone still owns its
# tiny offline fallback; this only selects among PC-local Ollama models.
# ---------------------------------------------------------------------------
choose_marker = "def _choose_ollama_model() -> str | None:\n"
choose_at = text.find(choose_marker)
if choose_at < 0:
    raise SystemExit("Ollama chooser marker missing")

helpers = r'''
def _cognition_gpu_profile() -> dict:
    result = {"name": None, "vram_mb": 0, "source": None}
    try:
        import shutil
        import subprocess

        nvidia = shutil.which("nvidia-smi") or shutil.which("nvidia-smi.exe")
        if nvidia:
            proc = subprocess.run(
                [nvidia, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if proc.returncode == 0:
                best = None
                for line in (proc.stdout or "").splitlines():
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) < 2:
                        continue
                    try:
                        mb = int(float(parts[-1]))
                    except Exception:
                        continue
                    name = ",".join(parts[:-1]).strip()[:120]
                    if best is None or mb > best[1]:
                        best = (name, mb)
                if best:
                    return {"name": best[0], "vram_mb": best[1], "source": "nvidia-smi"}
    except Exception:
        pass

    # Generic Windows fallback. AdapterRAM can be imperfect on some drivers, so
    # it is treated as a conservative hint rather than permission to overcommit.
    try:
        import subprocess
        ps = (
            "$g=Get-CimInstance Win32_VideoController | "
            "Select-Object Name,AdapterRAM | ConvertTo-Json -Compress; $g"
        )
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode == 0 and (proc.stdout or "").strip():
            import json
            raw = json.loads(proc.stdout.strip())
            rows = raw if isinstance(raw, list) else [raw]
            best = None
            for row in rows:
                if not isinstance(row, dict):
                    continue
                name = str(row.get("Name") or "").strip()[:120]
                try:
                    mb = max(0, int(row.get("AdapterRAM") or 0) // (1024 * 1024))
                except Exception:
                    mb = 0
                if best is None or mb > best[1]:
                    best = (name, mb)
            if best:
                result = {"name": best[0] or None, "vram_mb": best[1], "source": "windows-cim"}
    except Exception:
        pass
    return result


def _cognition_capacity() -> dict:
    snap = _resource_snapshot()
    total = int(snap.get("memory_total") or 0)
    available = int(snap.get("memory_available") or 0)
    cpu = max(1, int(snap.get("cpu_logical") or os.cpu_count() or 1))
    total_gb = total / (1024 ** 3) if total else 0.0
    available_gb = available / (1024 ** 3) if available else 0.0
    gpu = _cognition_gpu_profile()
    vram_gb = int(gpu.get("vram_mb") or 0) / 1024.0
    art_running = bool(snap.get("art_running"))

    # Conservative tiers leave room for Windows, Bridge, Remote Support and
    # separately launched workers. A larger model is never selected merely
    # because its file could technically fit in RAM.
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
    }


def _model_billions(name: str) -> float | None:
    low = str(name or "").lower()
    import re
    match = re.search(r"(?:^|[-_:])([0-9]+(?:\.[0-9]+)?)b(?:$|[-_:])", low)
    if not match:
        return None
    try:
        return float(match.group(1))
    except Exception:
        return None


def _cognition_model_rank(name: str, max_billions: float) -> tuple:
    low = str(name or "").lower()
    size = _model_billions(low)
    fits = size is None or size <= max_billions + 0.01
    family = 0
    if "qwen3" in low:
        family = 5
    elif "qwen" in low:
        family = 4
    elif "gemma" in low:
        family = 3
    elif "llama" in low:
        family = 2
    known = size is not None
    # Prefer the largest fitting Qwen-family model. Unknown-size models are kept
    # behind known fitting models so a strangely named local model cannot bypass
    # the hardware cap.
    return (1 if fits else 0, family, 1 if known else 0, size or 0.0)

'''
if "def _cognition_capacity() -> dict:" not in text:
    text = text[:choose_at] + helpers + text[choose_at:]

new_choose = r'''def _choose_ollama_model() -> str | None:
    models = _ollama_models()
    if not models:
        return None
    capacity = _cognition_capacity()
    max_billions = float(capacity.get("max_billions") or 2.0)

    fitting = []
    oversized = []
    for name in models:
        size = _model_billions(name)
        if size is None or size <= max_billions + 0.01:
            fitting.append(name)
        else:
            oversized.append(name)

    if fitting:
        return sorted(fitting, key=lambda n: _cognition_model_rank(n, max_billions), reverse=True)[0]

    # Compatibility fallback: never make cognition disappear merely because an
    # older install has only a 4B model on a lite node. Use the smallest known
    # installed model and surface the mismatch in /llm/status for the next setup.
    known = [(float(_model_billions(n)), n) for n in oversized if _model_billions(n) is not None]
    if known:
        known.sort(key=lambda pair: pair[0])
        return known[0][1]
    return models[0]
'''
text = replace_function(text, "_choose_ollama_model", new_choose)

# Enrich /llm/status with sanitized fit telemetry. No hostname, paths, tokens,
# user names, or file contents are exposed.
status_start = text.find('        if parsed.path == "/llm/status":\n')
status_end = text.find('        if parsed.path in ("/", "/status"):\n', status_start)
if status_start < 0 or status_end < 0:
    raise SystemExit("llm status route markers missing")
new_status = '''        if parsed.path == "/llm/status":\n            model = _choose_ollama_model()\n            capacity = _cognition_capacity()\n            selected_size = _model_billions(model or "")\n            self._json(200, {\n                "ok": model is not None,\n                "model": model,\n                "available_models": _ollama_models(),\n                "provider": "local-pc",\n                "tier": capacity.get("tier"),\n                "pressure": capacity.get("pressure"),\n                "selected_billions": selected_size,\n                "hardware": {\n                    "memory_total_gb": capacity.get("memory_total_gb"),\n                    "memory_available_gb": capacity.get("memory_available_gb"),\n                    "cpu_logical": capacity.get("cpu_logical"),\n                    "gpu_name": capacity.get("gpu_name"),\n                    "gpu_vram_gb": capacity.get("gpu_vram_gb"),\n                    "gpu_source": capacity.get("gpu_source"),\n                    "art_running": capacity.get("art_running"),\n                    "model_cap_billions": capacity.get("max_billions"),\n                },\n            })\n            return\n\n'''
text = text[:status_start] + new_status + text[status_end:]

bridge_path.write_text(text, encoding="utf-8")

# ---------------------------------------------------------------------------
# Remote Support: publish only the same sanitized cognition fit telemetry so an
# active opt-in session can answer "what can this node actually run?".
# ---------------------------------------------------------------------------
remote_path = Path("Tools/VexRemoteSupport.py")
remote = remote_path.read_text(encoding="utf-8")
remote = remote.replace('VERSION = "0.9.9"', 'VERSION = "0.10.9"', 1)
old_cognition = '''        "cognition": {\n            "ok": yes(llm.get("ok")),\n            "model": model_label(llm.get("model")),\n            "available_model_count": len(llm.get("available_models") or []) if isinstance(llm.get("available_models"), list) else 0,\n        },\n'''
new_cognition = '''        "cognition": {\n            "ok": yes(llm.get("ok")),\n            "model": model_label(llm.get("model")),\n            "available_model_count": len(llm.get("available_models") or []) if isinstance(llm.get("available_models"), list) else 0,\n            "tier": str(llm.get("tier") or "")[:24] or None,\n            "pressure": str(llm.get("pressure") or "")[:24] or None,\n            "hardware": {\n                "memory_total_gb": number((llm.get("hardware") or {}).get("memory_total_gb")) if isinstance(llm.get("hardware"), dict) else 0.0,\n                "memory_available_gb": number((llm.get("hardware") or {}).get("memory_available_gb")) if isinstance(llm.get("hardware"), dict) else 0.0,\n                "cpu_logical": integer((llm.get("hardware") or {}).get("cpu_logical")) if isinstance(llm.get("hardware"), dict) else 0,\n                "gpu_name": model_label((llm.get("hardware") or {}).get("gpu_name")) if isinstance(llm.get("hardware"), dict) else None,\n                "gpu_vram_gb": number((llm.get("hardware") or {}).get("gpu_vram_gb")) if isinstance(llm.get("hardware"), dict) else 0.0,\n                "model_cap_billions": number((llm.get("hardware") or {}).get("model_cap_billions")) if isinstance(llm.get("hardware"), dict) else 0.0,\n            },\n        },\n'''
if old_cognition not in remote:
    raise SystemExit("Remote Support cognition snapshot marker missing")
remote = remote.replace(old_cognition, new_cognition, 1)
remote_path.write_text(remote, encoding="utf-8")

# Build version markers for the next package without touching the proven 0.10.8
# branch or its artifacts.
full_path = Path("Bridge/vex_bridge_full.py")
full = full_path.read_text(encoding="utf-8")
if 'VERSION = "0.10.8"' not in full:
    raise SystemExit("v0.10.8 launcher marker missing")
full = full.replace('VERSION = "0.10.8"', 'VERSION = "0.10.9"', 1)
full_path.write_text(full, encoding="utf-8")

art_path = Path("Tools/VexArtWorker.py")
art = art_path.read_text(encoding="utf-8")
if 'VERSION = "0.10.8"' in art:
    art = art.replace('VERSION = "0.10.8"', 'VERSION = "0.10.9"', 1)
art_path.write_text(art, encoding="utf-8")

checks = {
    bridge_path: ["def _cognition_capacity()", "model_cap_billions", "def _cognition_gpu_profile()", "def _model_billions("],
    remote_path: ['VERSION = "0.10.9"', '"hardware": {', '"tier": str(llm.get("tier")'],
    full_path: ['VERSION = "0.10.9"'],
}
for target, markers in checks.items():
    data = target.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in data:
            raise SystemExit(f"{target}: missing v0.10.9 marker: {marker}")

print("Applied v0.10.9 adaptive hardware-aware PC cognition")
