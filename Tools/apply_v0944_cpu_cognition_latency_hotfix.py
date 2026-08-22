#!/usr/bin/env python3
from pathlib import Path

bridge_path = Path("Bridge/vex_bridge.py")
text = bridge_path.read_text(encoding="utf-8")

replacements = [
    (
        'OLLAMA_PREFERRED_MODELS = [\n    "qwen3:8b",',
        'OLLAMA_PREFERRED_MODELS = [\n    "vex-qwen3-4b:latest",\n    "vex-qwen3-4b",\n    "qwen3:8b",',
        "prefer the installed Vex Qwen3 model",
    ),
    (
        'for item in history[-28:]:',
        'for item in history[-16:]:',
        "trim cognition history for CPU inference",
    ),
    (
        'safe_messages.append({"role": role, "content": content[:5000]})',
        'safe_messages.append({"role": role, "content": content[:3000]})',
        "trim history message size",
    ),
    (
        'safe_messages.append({"role": "user", "content": str(message or "").strip()[:5000]})',
        'safe_messages.append({"role": "user", "content": str(message or "").strip()[:3000]})',
        "trim current message size",
    ),
    (
        '                "stream": False,\n                "options": {',
        '                "stream": False,\n                "think": False,\n                "keep_alive": "30m",\n                "options": {',
        "disable Qwen thinking mode and keep model warm",
    ),
    (
        '                    "num_ctx": 8192,\n                    "repeat_penalty": 1.08,',
        '                    "num_ctx": 4096,\n                    "num_predict": 192,\n                    "repeat_penalty": 1.08,',
        "right-size CPU context and output budget",
    ),
    (
        '            timeout=42,',
        '            timeout=(3.0, 85.0),',
        "extend Ollama CPU read timeout while staying inside the iPhone 90s request window",
    ),
]

for old, new, label in replacements:
    if old not in text:
        raise SystemExit(f"{label}: expected source block not found")
    text = text.replace(old, new, 1)

bridge_path.write_text(text, encoding="utf-8")

full_path = Path("Bridge/vex_bridge_full.py")
full = full_path.read_text(encoding="utf-8")
if 'VERSION = "0.9.4"' not in full:
    raise SystemExit("vex_bridge_full.py: expected v0.9.4 version marker missing")
full = full.replace('VERSION = "0.9.4"', 'VERSION = "0.9.4.4"', 1)
full_path.write_text(full, encoding="utf-8")

checks = [
    '"vex-qwen3-4b:latest"',
    '"think": False',
    '"keep_alive": "30m"',
    '"num_ctx": 4096',
    '"num_predict": 192',
    'timeout=(3.0, 85.0)',
]
for marker in checks:
    if marker not in text:
        raise SystemExit(f"missing v0.9.4.4 cognition marker: {marker}")
if 'VERSION = "0.9.4.4"' not in full:
    raise SystemExit("missing v0.9.4.4 Bridge version marker")

print("Applied v0.9.4.4 CPU cognition latency hotfix")
