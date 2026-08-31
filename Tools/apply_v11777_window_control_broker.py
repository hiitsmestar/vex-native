#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
INSTALLER = Path("Tools/VexAgentRuntimeInstall.py")
bridge = BRIDGE.read_text(encoding="utf-8")
installer = INSTALLER.read_text(encoding="utf-8")

for marker in [
    '"agent_runtime_bundle": "0.11.7.76"',
    'def _v11776_launch_app(',
    'parsed.path == "/windows/apps"',
    'parsed.path == "/windows/launch"',
]:
    if marker not in bridge:
        raise SystemExit(f"v0.11.7.77 expected Bridge marker missing: {marker}")
if 'BUNDLE_VERSION = "0.11.7.76"' not in installer:
    raise SystemExit("v0.11.7.77 expected installer .76")

insert_anchor = "def _vex_background_services() -> None:\n"
if insert_anchor not in bridge:
    raise SystemExit("v0.11.7.77 background-service insertion anchor missing")

layer = r'''
# ---------------------------------------------------------------------------
# v0.11.7.77 Window Control Broker
# Authenticated local UI-control foundation over Win32. Normal window management
# actions are allowed; close requires an explicit confirm bit because it can
# discard unsaved work. Every successful action is locally audited.
# ---------------------------------------------------------------------------
def _v11777_window_exists(hwnd: int) -> bool:
    if os.name != "nt" or int(hwnd or 0) <= 0:
        return False
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32.dll", use_last_error=True)
        user32.IsWindow.argtypes = [wintypes.HWND]
        user32.IsWindow.restype = wintypes.BOOL
        return bool(user32.IsWindow(wintypes.HWND(int(hwnd))))
    except Exception:
        return False


def _v11777_window_action(hwnd: int, action: str, confirm: bool = False, dry_run: bool = False) -> dict:
    hwnd = int(hwnd or 0)
    action = re.sub(r"[^a-z_-]", "", str(action or "").lower())[:40]
    allowed = {"focus", "minimize", "maximize", "restore", "close"}
    if action not in allowed:
        return {"ok": False, "version": "0.11.7.77", "error": "unsupported window action"}
    if not _v11777_window_exists(hwnd):
        return {"ok": False, "version": "0.11.7.77", "error": "window not found"}
    if action == "close" and not bool(confirm):
        return {"ok": False, "version": "0.11.7.77", "error": "close requires confirm=true"}
    if dry_run:
        return {"ok": True, "version": "0.11.7.77", "dry_run": True, "hwnd": hwnd, "action": action}
    if os.name != "nt":
        return {"ok": False, "version": "0.11.7.77", "error": "Windows window broker unavailable"}
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32.dll", use_last_error=True)
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.restype = wintypes.BOOL
        user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.PostMessageW.restype = wintypes.BOOL
        handle = wintypes.HWND(hwnd)
        if action == "focus":
            user32.ShowWindow(handle, 9)  # SW_RESTORE
            ok = bool(user32.SetForegroundWindow(handle))
        elif action == "minimize":
            ok = bool(user32.ShowWindow(handle, 6))  # SW_MINIMIZE
        elif action == "maximize":
            ok = bool(user32.ShowWindow(handle, 3))  # SW_MAXIMIZE
        elif action == "restore":
            ok = bool(user32.ShowWindow(handle, 9))  # SW_RESTORE
        else:
            ok = bool(user32.PostMessageW(handle, 0x0010, 0, 0))  # WM_CLOSE
        detail = {"hwnd": hwnd, "action": action, "accepted": bool(ok)}
        if ok:
            _v11776_audit("window_action", detail)
        return {"ok": bool(ok), "version": "0.11.7.77", **detail}
    except Exception as exc:
        return {"ok": False, "version": "0.11.7.77", "error": exc.__class__.__name__, "hwnd": hwnd, "action": action}


'''
if "def _v11777_window_action(" not in bridge:
    bridge = bridge.replace(insert_anchor, layer + insert_anchor, 1)

post_anchor = '        if parsed.path == "/windows/launch":\n'
post_route = '''        if parsed.path == "/windows/window-action":\n            try:\n                hwnd = int(body.get("hwnd") or 0)\n            except Exception:\n                hwnd = 0\n            action = str(body.get("action") or "").strip()\n            confirm = bool(body.get("confirm"))\n            dry_run = bool(body.get("dry_run"))\n            result = _v11777_window_action(hwnd, action, confirm=confirm, dry_run=dry_run)\n            self._json(200 if result.get("ok") else 400, result)\n            return\n\n'''
if 'parsed.path == "/windows/window-action"' not in bridge:
    if post_anchor not in bridge:
        raise SystemExit("v0.11.7.77 Windows POST anchor missing")
    bridge = bridge.replace(post_anchor, post_route + post_anchor, 1)

bridge = bridge.replace('"agent_runtime_bundle": "0.11.7.76"', '"agent_runtime_bundle": "0.11.7.77"', 1)
installer = installer.replace('BUNDLE_VERSION = "0.11.7.76"', 'BUNDLE_VERSION = "0.11.7.77"', 1)
installer = installer.replace('Vex Agent Runtime v0.11.7.76', 'Vex Agent Runtime v0.11.7.77')

BRIDGE.write_text(bridge, encoding="utf-8")
INSTALLER.write_text(installer, encoding="utf-8")
compile(bridge, str(BRIDGE), "exec")
compile(installer, str(INSTALLER), "exec")

required = [
    '"agent_runtime_bundle": "0.11.7.77"',
    'def _v11777_window_exists(', 'def _v11777_window_action(',
    'parsed.path == "/windows/window-action"',
    'close requires confirm=true', 'WM_CLOSE', 'def _v11776_launch_app(',
    'pc-memory-star-query-v11775',
]
for marker in required:
    if marker not in bridge:
        raise SystemExit(f"v0.11.7.77 Bridge marker missing: {marker}")
if 'BUNDLE_VERSION = "0.11.7.77"' not in installer:
    raise SystemExit("v0.11.7.77 installer identity missing")
print("Applied v0.11.7.77 window control broker")
