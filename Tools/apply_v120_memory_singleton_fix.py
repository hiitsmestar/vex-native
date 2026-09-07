#!/usr/bin/env python3
from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
WORKER = Path("Tools/VexMemoryWorker.py")
bridge = BRIDGE.read_text(encoding="utf-8")
worker = WORKER.read_text(encoding="utf-8")

BRIDGE_MARKER = 'V120_MEMORY_SINGLETON_GUARD = "v0.12-memory-singleton-port-guard-v1"'
WORKER_MARKER = 'V120_MEMORY_BIND_FIRST = "v0.12-memory-bind-first-v2"'
LOCK_MARKER = 'V120_MEMORY_WINDOWS_FILE_LOCK = "v0.12-memory-windows-file-lock-v4"'

if BRIDGE_MARKER not in bridge:
    anchor = "def _memory_worker_health(start_if_needed: bool = False) -> dict:\n"
    if anchor not in bridge:
        raise SystemExit("memory health anchor missing")
    helper = '''V120_MEMORY_SINGLETON_GUARD = "v0.12-memory-singleton-port-guard-v1"\n\n\ndef _memory_worker_port_open(timeout: float = 0.20) -> bool:\n    try:\n        with socket.create_connection(("127.0.0.1", MEMORY_WORKER_PORT), timeout=timeout):\n            return True\n    except OSError:\n        return False\n\n\n'''
    bridge = bridge.replace(anchor, helper + anchor, 1)

old_spawn = '''        now = time.time()\n        if now - _MEMORY_WORKER_LAST_START > 3.0:\n'''
new_spawn = '''        now = time.time()\n        port_open = _memory_worker_port_open()\n        if not port_open and now - _MEMORY_WORKER_LAST_START > 3.0:\n'''
if old_spawn in bridge:
    bridge = bridge.replace(old_spawn, new_spawn, 1)
elif new_spawn not in bridge:
    raise SystemExit("memory primary spawn gate anchor missing")
old_fallback = '''            if attempt == 20:\n                try:\n'''
new_fallback = '''            if attempt == 20 and not _memory_worker_port_open():\n                try:\n'''
if old_fallback in bridge:
    bridge = bridge.replace(old_fallback, new_fallback, 1)
elif new_fallback not in bridge:
    raise SystemExit("memory recovery fallback anchor missing")

LOCK_BLOCK = '''V120_MEMORY_BIND_FIRST = "v0.12-memory-bind-first-v2"\nV120_MEMORY_WINDOWS_FILE_LOCK = "v0.12-memory-windows-file-lock-v4"\n\n\ndef _claim_singleton(port: int):\n    if not sys.platform.startswith("win"):\n        return None\n    import msvcrt\n    lock_path = ROOT / f"worker-{int(port)}.lock"\n    lock_path.touch(exist_ok=True)\n    fh = lock_path.open("r+b")\n    fh.seek(0, 2)\n    if fh.tell() == 0:\n        fh.write(b"0")\n        fh.flush()\n    fh.seek(0)\n    try:\n        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)\n    except OSError:\n        fh.close()\n        return False\n    return fh\n\n\ndef serve(port: int) -> None:\n    singleton = _claim_singleton(port)\n    if singleton is False:\n        _log(f"VexMemoryWorker singleton exit on {HOST}:{port}: file lock already held")\n        return\n    server = None\n    try:\n        try:\n            server = ThreadingHTTPServer((HOST, int(port)), Handler)\n        except OSError as exc:\n            _log(f"VexMemoryWorker singleton exit on {HOST}:{port}: {exc}")\n            return\n        _auto_import_private_seeds()\n        _log(f"VexMemoryWorker v{VERSION} listening on {HOST}:{port} — {DB.stats()}")\n        server.serve_forever(poll_interval=0.5)\n    finally:\n        if server is not None:\n            server.server_close()\n        if singleton:\n            singleton.close()\n'''

if LOCK_MARKER not in worker:
    if WORKER_MARKER in worker:
        start = worker.index(WORKER_MARKER)
        end = worker.index('\n\ndef main(', start)
        worker = worker[:start] + LOCK_BLOCK + worker[end:]
    else:
        serve_old = '''def serve(port: int) -> None:\n    _auto_import_private_seeds()\n    server = ThreadingHTTPServer((HOST, int(port)), Handler)\n    _log(f"VexMemoryWorker v{VERSION} listening on {HOST}:{port} — {DB.stats()}")\n    try:\n        server.serve_forever(poll_interval=0.5)\n    finally:\n        server.server_close()\n'''
        if serve_old not in worker:
            raise SystemExit("memory worker serve anchor missing")
        worker = worker.replace(serve_old, LOCK_BLOCK, 1)

for required in [
    BRIDGE_MARKER,
    "def _memory_worker_port_open(timeout: float = 0.20) -> bool:",
    "if not port_open and now - _MEMORY_WORKER_LAST_START > 3.0:",
    "if attempt == 20 and not _memory_worker_port_open():",
]:
    if required not in bridge:
        raise SystemExit(f"bridge singleton verification failed: {required}")
for required in [WORKER_MARKER, LOCK_MARKER, "msvcrt.LK_NBLCK", "file lock already held"]:
    if required not in worker:
        raise SystemExit(f"worker singleton verification failed: {required}")

BRIDGE.write_text(bridge, encoding="utf-8")
WORKER.write_text(worker, encoding="utf-8")
print("Applied v0.12 persistent-memory singleton guard v4 (Windows file lock)")