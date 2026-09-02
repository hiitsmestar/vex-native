#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
text = BRIDGE.read_text(encoding="utf-8")

start = text.find("def _ollama_chat(")
if start < 0:
    raise SystemExit("v0.12 Ollama chat transport could not find _ollama_chat")
next_def = re.search(r"(?m)^def [A-Za-z0-9_]+\(", text[start + 1:])
end = len(text) if next_def is None else start + 1 + next_def.start()
chat = text[start:end]

if "session.trust_env = False" not in chat:
    old = "        import requests\n        response = requests.post(\n"
    new = "        import requests\n        session = requests.Session()\n        session.trust_env = False\n        response = session.post(\n"
    if old not in chat:
        raise SystemExit("v0.12 Ollama chat transport could not find requests.post anchor")
    chat = chat.replace(old, new, 1)

# The field machine is CPU-only/low-memory; 42 seconds is too short for a cold
# first generation even when the model is healthy. Keep it bounded, but patient.
chat, n = re.subn(r"timeout=42(?:\.0)?", "timeout=180", chat, count=1)
if n == 0 and "timeout=180" not in chat:
    raise SystemExit("v0.12 Ollama chat transport could not update generation timeout")

text = text[:start] + chat + text[end:]

# The old endpoint mapped every generation failure to the same misleading
# 'no local cognition model available' message. Preserve that message only when
# the chooser truly sees no installed model; otherwise report generation failure.
old_error = '''                result = _ollama_chat(history, message)\n                if result is None:\n                    self._json(503, {\n                        "ok": False,\n                        "error": "no local cognition model available",\n                        "setup": "Run VexBrainSetup.ps1 on this PC",\n                    })\n                    return\n'''
new_error = '''                result = _ollama_chat(history, message)\n                if result is None:\n                    visible_model = _choose_ollama_model()\n                    self._json(503, {\n                        "ok": False,\n                        "error": "local cognition generation failed" if visible_model else "no local cognition model available",\n                        "model": visible_model,\n                        "setup": None if visible_model else "Run VexBrainSetup.ps1 on this PC",\n                    })\n                    return\n'''
if old_error in text:
    text = text.replace(old_error, new_error, 1)
elif "local cognition generation failed" not in text:
    raise SystemExit("v0.12 Ollama chat transport could not differentiate chat failure")

BRIDGE.write_text(text, encoding="utf-8")
compile(text, str(BRIDGE), "exec")

for marker in [
    "session.trust_env = False",
    "response = session.post(",
    "timeout=180",
    "local cognition generation failed",
    "visible_model = _choose_ollama_model()",
]:
    if marker not in text:
        raise SystemExit(f"v0.12 Ollama chat transport missing marker: {marker}")

print("Applied v0.12 proxy-safe patient Ollama chat transport + truthful generation errors")
