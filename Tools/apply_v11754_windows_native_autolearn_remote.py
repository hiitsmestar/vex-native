#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
REMOTE = Path("Tools/VexRemoteSupport.py")
INSTALLER = Path("Tools/VexAgentRuntimeInstall.py")

bridge = BRIDGE.read_text(encoding="utf-8")
remote = REMOTE.read_text(encoding="utf-8")
installer = INSTALLER.read_text(encoding="utf-8")

for label, text, marker in [
    ("Bridge", bridge, '"agent_runtime_bundle": "0.11.7.53"'),
    ("Bridge autolearn", bridge, 'parsed.path == "/autolearn/status"'),
    ("Remote Support", remote, 'VERSION = "0.11.7.29"'),
    ("Installer", installer, 'BUNDLE_VERSION = "0.11.7.53"'),
]:
    if marker not in text:
        raise SystemExit(f"v0.11.7.54 expected {label} marker missing: {marker}")

# ---------------------------------------------------------------------------
# Windows-native local access foundation.
# Read-only discovery lives behind the already-authenticated local Bridge.
# Remote Support only receives the sanitized capability summary, never titles.
# ---------------------------------------------------------------------------
native_anchor = "def _vex_background_services() -> None:\n"
if native_anchor not in bridge:
    raise SystemExit("v0.11.7.54 Windows-native insertion anchor missing")

native_layer = r'''
# ---------------------------------------------------------------------------
# v0.11.7.54 Windows Native Access Foundation
#
# Uses supported/built-in Windows primitives already present on the PC. Raw
# window titles are available only through the authenticated local Bridge.
# Public Remote Support exposes booleans/counts only.
# ---------------------------------------------------------------------------
def _windows_native_visible_windows(limit: int = 64) -> list[dict]:
    if os.name != "nt":
        return []
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32.dll", use_last_error=True)
        rows: list[dict] = []
        enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetClassNameW.restype = ctypes.c_int
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD

        @enum_proc
        def collect(hwnd, _lparam):
            if len(rows) >= max(1, min(int(limit or 64), 128)):
                return False
            if not user32.IsWindowVisible(hwnd):
                return True
            length = int(user32.GetWindowTextLengthW(hwnd) or 0)
            if length <= 0:
                return True
            title_buf = ctypes.create_unicode_buffer(min(length + 1, 1024))
            user32.GetWindowTextW(hwnd, title_buf, len(title_buf))
            title = str(title_buf.value or "").strip()
            if not title:
                return True
            class_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, class_buf, len(class_buf))
            pid = wintypes.DWORD(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            rows.append(
                {
                    "hwnd": int(hwnd or 0),
                    "pid": int(pid.value or 0),
                    "title": title[:700],
                    "class_name": str(class_buf.value or "")[:240],
                }
            )
            return True

        user32.EnumWindows(enum_proc, 0)
        return rows
    except Exception:
        return []


def _windows_native_capabilities() -> dict:
    result = {
        "ok": True,
        "version": "0.11.7.54",
        "windows": os.name == "nt",
        "ui_automation_api": False,
        "msaa_accessibility_api": False,
        "shell_com_api": False,
        "windows_search_service": False,
        "windows_search_running": False,
        "sapi_speech": False,
        "powershell": False,
        "native_window_inventory": False,
        "visible_window_count": 0,
        "privacy": "raw window titles remain local; remote relay gets capabilities/counts only",
    }
    if os.name != "nt":
        return result
    try:
        import ctypes
        ctypes.WinDLL("UIAutomationCore.dll")
        result["ui_automation_api"] = True
    except Exception:
        pass
    try:
        import ctypes
        ctypes.WinDLL("oleacc.dll")
        result["msaa_accessibility_api"] = True
    except Exception:
        pass
    try:
        import ctypes
        ctypes.OleDLL("ole32.dll")
        result["shell_com_api"] = True
    except Exception:
        pass
    try:
        import shutil
        result["powershell"] = bool(shutil.which("powershell.exe") or shutil.which("pwsh.exe"))
        sc = shutil.which("sc.exe")
        if sc:
            import subprocess
            completed = subprocess.run(
                [sc, "query", "WSearch"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=4,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            text = str(completed.stdout or "").upper()
            result["windows_search_service"] = completed.returncode == 0
            result["windows_search_running"] = "RUNNING" in text
    except Exception:
        pass
    try:
        from pathlib import Path as _Path
        windir = _Path(os.environ.get("WINDIR") or r"C:\Windows")
        speech_candidates = [
            windir / "Speech" / "Common" / "sapisvr.exe",
            windir / "System32" / "Speech" / "Common" / "sapisvr.exe",
            windir / "SysWOW64" / "Speech" / "Common" / "sapisvr.exe",
        ]
        result["sapi_speech"] = any(path.exists() for path in speech_candidates)
    except Exception:
        pass
    windows = _windows_native_visible_windows(limit=64)
    result["native_window_inventory"] = True
    result["visible_window_count"] = len(windows)
    return result


'''

if "def _windows_native_capabilities(" not in bridge:
    bridge = bridge.replace(native_anchor, native_layer + native_anchor, 1)

get_anchor = '        if parsed.path == "/autolearn/status":\n'
get_routes = '''        if parsed.path == "/windows/capabilities":\n            status = _windows_native_capabilities()\n            self._json(200 if status.get("ok") else 503, status)\n            return\n\n        if parsed.path == "/windows/windows":\n            rows = _windows_native_visible_windows(limit=64)\n            self._json(200, {"ok": True, "version": "0.11.7.54", "count": len(rows), "windows": rows})\n            return\n\n'''
if 'parsed.path == "/windows/capabilities"' not in bridge:
    if get_anchor not in bridge:
        raise SystemExit("v0.11.7.54 autolearn GET anchor missing")
    bridge = bridge.replace(get_anchor, get_routes + get_anchor, 1)

# Bundle identity advances; the field-proven Bridge protocol stays 0.11.7.39 and
# the autonomous project-learning engine itself stays versioned 0.11.7.53.
bridge = bridge.replace('"agent_runtime_bundle": "0.11.7.53"', '"agent_runtime_bundle": "0.11.7.54"', 1)

# ---------------------------------------------------------------------------
# Remote Support v0.11.7.54: sanitized autolearn telemetry/control plus Windows
# capability telemetry. No raw goals, evidence URLs, proposal filenames/paths,
# window titles, private IPs, tokens or personal memory are emitted publicly.
# ---------------------------------------------------------------------------
remote = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.54"', remote, count=1, flags=re.M)

helper_anchor = "def maintenance_public(value: dict) -> dict:\n"
helpers = r'''def autolearn_public(value: dict) -> dict:
    return {
        "ok": yes(value.get("ok")),
        "version": str(value.get("version") or "")[:40] or None,
        "mode": str(value.get("mode") or "")[:80] or None,
        "worker_started": yes(value.get("worker_started")),
        "worker_alive": yes(value.get("worker_alive")),
        "tasks": integer(value.get("tasks")),
        "pending": integer(value.get("pending")),
        "proposals": integer(value.get("proposals")),
        "ready_for_review": integer(value.get("ready_for_review")),
        "approval_required": integer(value.get("approval_required")),
    }


def windows_native_public(value: dict) -> dict:
    return {
        "ok": yes(value.get("ok")),
        "version": str(value.get("version") or "")[:40] or None,
        "windows": yes(value.get("windows")),
        "ui_automation_api": yes(value.get("ui_automation_api")),
        "msaa_accessibility_api": yes(value.get("msaa_accessibility_api")),
        "shell_com_api": yes(value.get("shell_com_api")),
        "windows_search_service": yes(value.get("windows_search_service")),
        "windows_search_running": yes(value.get("windows_search_running")),
        "sapi_speech": yes(value.get("sapi_speech")),
        "powershell": yes(value.get("powershell")),
        "native_window_inventory": yes(value.get("native_window_inventory")),
        "visible_window_count": integer(value.get("visible_window_count")),
    }


'''
if "def autolearn_public(" not in remote:
    if helper_anchor not in remote:
        raise SystemExit("v0.11.7.54 Remote helper anchor missing")
    remote = remote.replace(helper_anchor, helpers + helper_anchor, 1)

collect_anchor = '    maintenance = bridge_get("/maintenance/status", timeout=20)\n'
collect_new = (
    collect_anchor
    + '    autolearn = bridge_get("/autolearn/status", timeout=12)\n'
    + '    windows_native = bridge_get("/windows/capabilities", timeout=10)\n'
)
if 'autolearn = bridge_get("/autolearn/status"' not in remote:
    if collect_anchor not in remote:
        raise SystemExit("v0.11.7.54 Remote snapshot fetch anchor missing")
    remote = remote.replace(collect_anchor, collect_new, 1)

snap_anchor = '        "learning": learning_public(learning),\n'
snap_new = (
    snap_anchor
    + '        "autolearn": autolearn_public(autolearn),\n'
    + '        "windows_native": windows_native_public(windows_native),\n'
)
if '"autolearn": autolearn_public(autolearn)' not in remote:
    if snap_anchor not in remote:
        raise SystemExit("v0.11.7.54 Remote snapshot payload anchor missing")
    remote = remote.replace(snap_anchor, snap_new, 1)

action_anchor = '    if action == "maintenance_status":\n'
actions = r'''    if action == "autolearn_status":
        return {"autolearn": autolearn_public(bridge_get("/autolearn/status", timeout=15))}
    if action == "autolearn_run":
        result = bridge_post("/autolearn/run", {}, timeout=210)
        return {
            "ok": yes(result.get("ok")),
            "task_id": integer(result.get("task_id")),
            "proposal_id": integer(result.get("proposal_id")),
            "status": str(result.get("status") or "")[:50] or None,
            "risk": str(result.get("risk") or "")[:30] or None,
            "confidence": number(result.get("confidence")),
            "http_status": integer(result.get("http_status")),
            "error_class": str(result.get("error") or "")[:100] if result.get("error") else None,
        }
    if action == "autolearn_queue":
        topic = str(command.get("topic") or "").strip()
        if not technical_topic(topic):
            return {"ok": False, "error": "remote autonomous queue accepts generic technical topics only"}
        result = bridge_post(
            "/autolearn/queue",
            {"goal": topic, "category": "capability", "detail": "sanitized remote-support technical request"},
            timeout=25,
        )
        return {
            "ok": yes(result.get("ok")),
            "task_id": integer(result.get("task_id")),
            "queued_for_research": bool(str(result.get("public_topic") or "").strip()),
            "http_status": integer(result.get("http_status")),
        }
    if action == "windows_capabilities":
        return {"windows_native": windows_native_public(bridge_get("/windows/capabilities", timeout=12))}
'''
if 'action == "autolearn_status"' not in remote:
    if action_anchor not in remote:
        raise SystemExit("v0.11.7.54 Remote action anchor missing")
    remote = remote.replace(action_anchor, actions + action_anchor, 1)

# Installer identity and field text. Do not regress the working iPhone .49 build.
installer = installer.replace('BUNDLE_VERSION = "0.11.7.53"', 'BUNDLE_VERSION = "0.11.7.54"', 1)
installer = installer.replace('REMOTE_VERSION = "0.11.7.29"', 'REMOTE_VERSION = "0.11.7.54"', 1)
installer = installer.replace("Vex Agent Runtime v0.11.7.53 installed.", "Vex Agent Runtime v0.11.7.54 installed.", 1)
installer = installer.replace(
    "Keep VexNative v0.11.7.48 on the iPhone; its working pairing is preserved.",
    "Keep VexNative v0.11.7.49 on the iPhone; its working PC-routing pairing is preserved.",
)

BRIDGE.write_text(bridge, encoding="utf-8")
REMOTE.write_text(remote, encoding="utf-8")
INSTALLER.write_text(installer, encoding="utf-8")
for path, text in [(BRIDGE, bridge), (REMOTE, remote), (INSTALLER, installer)]:
    compile(text, str(path), "exec")

for marker in [
    '"agent_runtime_bundle": "0.11.7.54"',
    '"version": "0.11.7.39"',
    "def _windows_native_capabilities(",
    "def _windows_native_visible_windows(",
    'parsed.path == "/windows/capabilities"',
    'parsed.path == "/windows/windows"',
    'parsed.path == "/autolearn/status"',
    'name="VexAutonomousLearningSupervisor"',
]:
    if marker not in bridge:
        raise SystemExit(f"v0.11.7.54 Bridge marker missing: {marker}")

for marker in [
    'VERSION = "0.11.7.54"',
    "def autolearn_public(",
    "def windows_native_public(",
    'action == "autolearn_status"',
    'action == "autolearn_run"',
    'action == "autolearn_queue"',
    'action == "windows_capabilities"',
    'bridge_get("/autolearn/status"',
    'bridge_get("/windows/capabilities"',
]:
    if marker not in remote:
        raise SystemExit(f"v0.11.7.54 Remote Support marker missing: {marker}")

for marker in [
    'BUNDLE_VERSION = "0.11.7.54"',
    'REMOTE_VERSION = "0.11.7.54"',
    "Vex Agent Runtime v0.11.7.54 installed.",
    "Keep VexNative v0.11.7.49 on the iPhone",
]:
    if marker not in installer:
        raise SystemExit(f"v0.11.7.54 installer marker missing: {marker}")

# Hard public-relay privacy boundary: Remote Support must never request the raw
# local window inventory or emit raw proposal/evidence structures.
for forbidden in [
    'bridge_get("/windows/windows"',
    '"recent_proposals":',
    '"source_url":',
    '"artifact_path":',
    '"window_title":',
]:
    if forbidden in remote:
        raise SystemExit(f"v0.11.7.54 public relay privacy boundary violated: {forbidden}")

print("Applied v0.11.7.54 Windows-native access + autonomous supervisor remote control")
