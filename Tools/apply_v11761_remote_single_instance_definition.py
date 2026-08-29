#!/usr/bin/env python3
from __future__ import annotations

import ast
import re
from pathlib import Path

REMOTE = Path("Tools/VexRemoteSupport.py")
remote = REMOTE.read_text(encoding="utf-8")

if 'VERSION = "0.11.7.60"' not in remote:
    raise SystemExit("v0.11.7.61 expected v0.11.7.60 Remote Support identity")
remote = re.sub(r'^VERSION = "0\.11\.7\.60"', 'VERSION = "0.11.7.61"', remote, count=1, flags=re.M)

# Field failure in v0.11.7.60 was an exact NameError at main():
# acquire_remote_single_instance was referenced but absent from the packaged source.
# Guarantee a top-level definition immediately before main(), then prove the AST.

def top_level_functions(text: str) -> set[str]:
    tree = ast.parse(text)
    return {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}

helper = r'''_REMOTE_INSTANCE_HANDLE = None


def acquire_remote_single_instance() -> bool:
    global _REMOTE_INSTANCE_HANDLE
    if not sys.platform.startswith("win"):
        return True
    try:
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel32.CreateMutexW(None, 0, "Local\\VexRemoteSupport-v11761-single-instance")
        if not handle:
            return True
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            kernel32.CloseHandle(handle)
            return False
        _REMOTE_INSTANCE_HANDLE = handle
        return True
    except Exception:
        # Single-instance protection must never prevent Remote Support startup.
        return True


'''

funcs = top_level_functions(remote)
if "acquire_remote_single_instance" not in funcs:
    main_match = re.search(r'(?m)^def main\(\) -> int:\s*$', remote)
    if not main_match:
        raise SystemExit("v0.11.7.61 main declaration missing")
    remote = remote[:main_match.start()] + helper + remote[main_match.start():]

if "if not acquire_remote_single_instance():" not in remote:
    raise SystemExit("v0.11.7.61 expected single-instance call in main")

REMOTE.write_text(remote, encoding="utf-8")
compile(remote, str(REMOTE), "exec")
funcs = top_level_functions(remote)
if "acquire_remote_single_instance" not in funcs:
    raise SystemExit("v0.11.7.61 top-level acquire_remote_single_instance definition missing")
if 'VERSION = "0.11.7.61"' not in remote:
    raise SystemExit("v0.11.7.61 version marker missing")
if "Local\\\\VexRemoteSupport-v11761-single-instance" not in remote:
    raise SystemExit("v0.11.7.61 mutex marker missing")

print("Applied v0.11.7.61 Remote Support single-instance definition repair")
print("v0.11.7.61 trigger 2026-08-29")
