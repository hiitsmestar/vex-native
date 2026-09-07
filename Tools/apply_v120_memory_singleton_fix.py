#!/usr/bin/env python3
from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
WORKER = Path("Tools/VexMemoryWorker.py")

bridge = BRIDGE.read_text(encoding="utf-8")
worker = WORKER.read_text(encoding="utf-8")

BRIDGE_MARKER = 'V120_MEMORY_SINGLETON_GUARD = "v0.12-memory-singleton-port-guard-v1"'
WORKER_MARKER = 'V120_MEMORY_BIND_FIRST = "v0.12-memory-bind-first-v2"'
MUTEX_MARKER = 'V120_MEMORY_WINDOWS_MUTEX = "v0.12-memory-windows-mutex-v3"'

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

if MUTEX_MARKER not in worker:
    if WORKER_MARKER in worker:
        start = worker.index(WORKER_MARKER)
        end = worker.index('\n\ndef main(', start)
        replacement = '''V120_MEMORY_BIND_FIRST = "v0.12-memory-bind-first-v2"\nV120_MEMORY_WINDOWS_MUTEX = "v0.12-memory-windows-mutex-v3"\n\n\ndef _claim_singleton(port: int):\n    if not sys.platform.startswith("win"):\n        return None\n    import ctypes\n    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)\n    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]\n    kernel32.CreateMutexW.restype = ctypes.c_void_p\n    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]\n    kernel32.CloseHandle.restype = ctypes.c_bool\n    handle = kernel32.CreateMutexW(None, False, f"Local\\\\VexNativeMemoryWorker_{int(port)}")\n    if not handle:\n        raise OSError(ctypes.get_last_error(), "CreateMutexW failed")\n    if ctypes.get_last_error() == 183:\n        kernel32.CloseHandle(handle)\n        return False\n    return kernel32, handle\n\n\ndef serve(port: int) -> None:\n    singleton = _claim_singleton(port)\n    if singleton is False:\n        _log(f"VexMemoryWorker singleton exit on {HOST}:{port}: mutex already owned")\n        return\n    server = None\n    try:\n        try:\n            server = ThreadingHTTPServer((HOST, int(port)), Handler)\n        except OSError as exc:\n            _log(f"VexMemoryWorker singleton exit on {HOST}:{port}: {exc}")\n            return\n        _auto_import_private_seeds()\n        _log(f"VexMemoryWorker v{VERSION} listening on {HOST}:{port} — {DB.stats()}")\n        server.serve_forever(poll_interval=0.5)\n    finally:\n        if server is not None:\n            server.server_close()\n        if singleton:\n            kernel32, handle = singleton\n            kernel32.CloseHandle(handle)\n'''
        worker = worker[:start] + replacement + worker[end:]
    else:
        serve_old = '''def serve(port: int) -> None:\n    _auto_import_private_seeds()\n    server = ThreadingHTTPServer((HOST, int(port)), Handler)\n    _log(f"VexMemoryWorker v{VERSION} listening on {HOST}:{port} — {DB.stats()}")\n    try:\n        server.serve_forever(poll_interval=0.5)\n    finally:\n        server.server_close()\n'''
        serve_new = '''V120_MEMORY_BIND_FIRST = "v0.12-memory-bind-first-v2"\nV120_MEMORY_WINDOWS_MUTEX = "v0.12-memory-windows-mutex-v3"\n\n\ndef _claim_singleton(port: int):\n    if not sys.platform.startswith("win"):\n        return None\n    import ctypes\n    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)\n    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]\n    kernel32.CreateMutexW.restype = ctypes.c_void_p\n    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]\n    kernel32.CloseHandle.restype = ctypes.c_bool\n    handle = kernel32.CreateMutexW(None, False, f"Local\\\\VexNativeMemoryWorker_{int(port)}")\n    if not handle:\n        raise OSError(ctypes.get_last_error(), "CreateMutexW failed")\n    if ctypes.get_last_error() == 183:\n        kernel32.CloseHandle(handle)\n        return False\n    return kernel32, handle\n\n\ndef serve(port: int) -> None:\n    singleton = _claim_singleton(port)\n    if singleton is False:\n        _log(f"VexMemoryWorker singleton exit on {HOST}:{port}: mutex already owned")\n        return\n    server = None\n    try:\n        try:\n            server = ThreadingHTTPServer((HOST, int(port)), Handler)\n        except OSError as exc:\n            _log(f"VexMemoryWorker singleton exit on {HOST}:{port}: {exc}")\n            return\n        _auto_import_private_seeds()\n        _log(f"VexMemoryWorker v{VERSION} listening on {HOST}:{port} — {DB.stats()}")\n        server.serve_forever(poll_interval=0.5)\n    finally:\n        if server is not None:\n            server.server_close()\n        if singleton:\n            kernel32, handle = singleton\n            kernel32.CloseHandle(handle)\n'''
        if serve_old not in worker:
            raise SystemExit("memory worker serve anchor missing")
        worker = worker.replace(serve_old, serve_new, 1)

for required in [BRIDGE_MARKER,"def _memory_worker_port_open(timeout: float = 0.20) -> bool:","if not port_open and now - _MEMORY_WORKER_LAST_START > 3.0:","if attempt == 20 and not _memory_worker_port_open():"]:
    if required not in bridge:
        raise SystemExit(f"bridge singleton verification failed: {required}")
for required in [WORKER_MARKER,MUTEX_MARKER,"CreateMutexW","mutex already owned"]:
    if required not in worker:
        raise SystemExit(f"worker singleton verification failed: {required}")

BRIDGE.write_text(bridge, encoding="utf-8")
WORKER.write_text(worker, encoding="utf-8")
print("Applied v0.12 persistent-memory singleton guard v3 (Windows mutex)")
