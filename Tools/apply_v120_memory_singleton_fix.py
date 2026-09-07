#!/usr/bin/env python3
from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
WORKER = Path("Tools/VexMemoryWorker.py")

bridge = BRIDGE.read_text(encoding="utf-8")
worker = WORKER.read_text(encoding="utf-8")

BRIDGE_MARKER = 'V120_MEMORY_SINGLETON_GUARD = "v0.12-memory-singleton-port-guard-v1"'
WORKER_MARKER = 'V120_MEMORY_BIND_FIRST = "v0.12-memory-bind-first-v2"'

if BRIDGE_MARKER not in bridge:
    anchor = "def _memory_worker_health(start_if_needed: bool = False) -> dict:\n"
    if anchor not in bridge:
        raise SystemExit("memory health anchor missing")
    helper = '''V120_MEMORY_SINGLETON_GUARD = "v0.12-memory-singleton-port-guard-v1"\n\n\ndef _memory_worker_port_open(timeout: float = 0.20) -> bool:\n    try:\n        with socket.create_connection(("127.0.0.1", MEMORY_WORKER_PORT), timeout=timeout):\n            return True\n    except OSError:\n        return False\n\n\n'''
    bridge = bridge.replace(anchor, helper + anchor, 1)

old_spawn_gate = '''        now = time.time()\n        if now - _MEMORY_WORKER_LAST_START > 3.0:\n'''
new_spawn_gate = '''        now = time.time()\n        port_open = _memory_worker_port_open()\n        if not port_open and now - _MEMORY_WORKER_LAST_START > 3.0:\n'''
if old_spawn_gate in bridge:
    bridge = bridge.replace(old_spawn_gate, new_spawn_gate, 1)
elif new_spawn_gate not in bridge:
    raise SystemExit("memory primary spawn gate anchor missing")

old_fallback = '''            if attempt == 20:\n                try:\n'''
new_fallback = '''            if attempt == 20 and not _memory_worker_port_open():\n                try:\n'''
if old_fallback in bridge:
    bridge = bridge.replace(old_fallback, new_fallback, 1)
elif new_fallback not in bridge:
    raise SystemExit("memory recovery fallback anchor missing")

if WORKER_MARKER not in worker:
    serve_old = '''def serve(port: int) -> None:\n    _auto_import_private_seeds()\n    server = ThreadingHTTPServer((HOST, int(port)), Handler)\n    _log(f"VexMemoryWorker v{VERSION} listening on {HOST}:{port} — {DB.stats()}")\n    try:\n        server.serve_forever(poll_interval=0.5)\n    finally:\n        server.server_close()\n'''
    serve_new = '''V120_MEMORY_BIND_FIRST = "v0.12-memory-bind-first-v2"\n\n\ndef serve(port: int) -> None:\n    # Claim the listener before touching seed imports/SQLite. Competing launches\n    # then fail immediately instead of piling up behind memory initialization.\n    try:\n        server = ThreadingHTTPServer((HOST, int(port)), Handler)\n    except OSError as exc:\n        _log(f"VexMemoryWorker singleton exit on {HOST}:{port}: {exc}")\n        return\n    try:\n        _auto_import_private_seeds()\n        _log(f"VexMemoryWorker v{VERSION} listening on {HOST}:{port} — {DB.stats()}")\n        server.serve_forever(poll_interval=0.5)\n    finally:\n        server.server_close()\n'''
    if serve_old not in worker:
        raise SystemExit("memory worker serve anchor missing")
    worker = worker.replace(serve_old, serve_new, 1)

for required in [
    BRIDGE_MARKER,
    "def _memory_worker_port_open(timeout: float = 0.20) -> bool:",
    "if not port_open and now - _MEMORY_WORKER_LAST_START > 3.0:",
    "if attempt == 20 and not _memory_worker_port_open():",
]:
    if required not in bridge:
        raise SystemExit(f"bridge singleton verification failed: {required}")

for required in [
    WORKER_MARKER,
    "server = ThreadingHTTPServer((HOST, int(port)), Handler)",
    "except OSError as exc:",
    "_auto_import_private_seeds()",
]:
    if required not in worker:
        raise SystemExit(f"worker singleton verification failed: {required}")

# Prove binding happens before private seed/database work in the worker.
serve_block = worker[worker.index("def serve(port: int) -> None:"):]
if serve_block.index("server = ThreadingHTTPServer") > serve_block.index("_auto_import_private_seeds()"):
    raise SystemExit("worker bind-first ordering verification failed")

BRIDGE.write_text(bridge, encoding="utf-8")
WORKER.write_text(worker, encoding="utf-8")
print("Applied v0.12 persistent-memory singleton guard v2 (bridge gate + worker bind-first)")
