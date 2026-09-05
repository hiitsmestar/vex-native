#!/usr/bin/env python3
from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
text = BRIDGE.read_text(encoding="utf-8")

MARKER = 'V120_MEMORY_SINGLETON_GUARD = "v0.12-memory-singleton-port-guard-v1"'

if MARKER not in text:
    anchor = "def _memory_worker_health(start_if_needed: bool = False) -> dict:\n"
    if anchor not in text:
        raise SystemExit("memory health anchor missing")
    helper = '''V120_MEMORY_SINGLETON_GUARD = "v0.12-memory-singleton-port-guard-v1"\n\n\ndef _memory_worker_port_open(timeout: float = 0.20) -> bool:\n    try:\n        with socket.create_connection(("127.0.0.1", MEMORY_WORKER_PORT), timeout=timeout):\n            return True\n    except OSError:\n        return False\n\n\n'''
    text = text.replace(anchor, helper + anchor, 1)

old_spawn_gate = '''        now = time.time()\n        if now - _MEMORY_WORKER_LAST_START > 3.0:\n'''
new_spawn_gate = '''        now = time.time()\n        port_open = _memory_worker_port_open()\n        if not port_open and now - _MEMORY_WORKER_LAST_START > 3.0:\n'''
if old_spawn_gate in text:
    text = text.replace(old_spawn_gate, new_spawn_gate, 1)
elif new_spawn_gate not in text:
    raise SystemExit("memory primary spawn gate anchor missing")

old_fallback = '''            if attempt == 20:\n                try:\n'''
new_fallback = '''            if attempt == 20 and not _memory_worker_port_open():\n                try:\n'''
if old_fallback in text:
    text = text.replace(old_fallback, new_fallback, 1)
elif new_fallback not in text:
    raise SystemExit("memory recovery fallback anchor missing")

for required in [
    MARKER,
    "def _memory_worker_port_open(timeout: float = 0.20) -> bool:",
    "if not port_open and now - _MEMORY_WORKER_LAST_START > 3.0:",
    "if attempt == 20 and not _memory_worker_port_open():",
]:
    if required not in text:
        raise SystemExit(f"singleton verification failed: {required}")

BRIDGE.write_text(text, encoding="utf-8")
print("Applied v0.12 persistent-memory singleton guard")
