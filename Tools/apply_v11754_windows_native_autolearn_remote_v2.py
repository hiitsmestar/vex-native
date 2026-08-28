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

native_anchor = "def _vex_background_services() -> None:\n"
if native_anchor not in bridge:
    raise SystemExit("v0.11.7.54 Windows-native insertion anchor missing")

native_layer = r'''
# ---------------------------------------------------------------------------
# v0.11.7.54 Windows Native Access Foundation
# Raw window metadata is local/authenticated only. Public Remote Support emits
# capability booleans and counts, never titles/process details.
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
            rows.append({
                "hwnd": int(hwnd or 0),
                "pid": int(pid.value or 0),
                "title": title[:700],
                "class_name": str(class_buf.value or "")[:240],
            })
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
                [sc, "query", "WSearch"], stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, timeout=4,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            service_text = str(completed.stdout or "").upper()
            result["windows_search_service"] = completed.returncode == 0
            result["windows_search_running"] = "RUNNING" in service_text
    except Exception:
        pass
    try:
        from pathlib import Path as _Path
        windir = _Path(os.environ.get("WINDIR") or r"C:\Windows")
        result["sapi_speech"] = any(path.exists() for path in [
            windir / "Speech" / "Common" / "sapisvr.exe",
            windir / "System32" / "Speech" / "Common" / "sapisvr.exe",
            windir / "SysWOW64" / "Speech" / "Common" / "sapisvr.exe",
        ])
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
bridge = bridge.replace('"agent_runtime_bundle": "0.11.7.53"', '"agent_runtime_bundle": "0.11.7.54"', 1)

# Remote Support component version advances because it now understands the .53
# project-learning supervisor and .54 Windows capability surface.
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

# Wrap the proven snapshot function rather than depending on its evolving internals.
snapshot_wrapper_anchor = "def gh_api("
snapshot_wrapper = r'''_v11754_collect_snapshot_base = collect_snapshot


def collect_snapshot(include_doctor: bool = False, deep: bool = False) -> dict:
    snap = _v11754_collect_snapshot_base(include_doctor=include_doctor, deep=deep)
    snap["autolearn"] = autolearn_public(bridge_get("/autolearn/status", timeout=12))
    snap["windows_native"] = windows_native_public(bridge_get("/windows/capabilities", timeout=10))
    return snap


'''
if "_v11754_collect_snapshot_base = collect_snapshot" not in remote:
    if snapshot_wrapper_anchor not in remote:
        raise SystemExit("v0.11.7.54 Remote snapshot wrapper anchor missing")
    remote = remote.replace(snapshot_wrapper_anchor, snapshot_wrapper + snapshot_wrapper_anchor, 1)

# Likewise wrap the proven command dispatcher; old commands remain untouched.
command_wrapper_anchor = "def parse_command("
command_wrapper = r'''_v11754_execute_command_base = execute_command


def execute_command(command: dict, allow_maintenance: bool) -> dict:
    action = str(command.get("action") or "").strip().lower()
    if action == "autolearn_status":
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
    return _v11754_execute_command_base(command, allow_maintenance)


'''
if "_v11754_execute_command_base = execute_command" not in remote:
    if command_wrapper_anchor not in remote:
        raise SystemExit("v0.11.7.54 Remote command wrapper anchor missing")
    remote = remote.replace(command_wrapper_anchor, command_wrapper + command_wrapper_anchor, 1)

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
    '"agent_runtime_bundle": "0.11.7.54"', '"version": "0.11.7.39"',
    "def _windows_native_capabilities(", "def _windows_native_visible_windows(",
    'parsed.path == "/windows/capabilities"', 'parsed.path == "/windows/windows"',
    'parsed.path == "/autolearn/status"', 'name="VexAutonomousLearningSupervisor"',
]:
    if marker not in bridge:
        raise SystemExit(f"v0.11.7.54 Bridge marker missing: {marker}")
for marker in [
    'VERSION = "0.11.7.54"', "def autolearn_public(", "def windows_native_public(",
    'action == "autolearn_status"', 'action == "autolearn_run"',
    'action == "autolearn_queue"', 'action == "windows_capabilities"',
    'bridge_get("/autolearn/status"', 'bridge_get("/windows/capabilities"',
]:
    if marker not in remote:
        raise SystemExit(f"v0.11.7.54 Remote Support marker missing: {marker}")
for marker in [
    'BUNDLE_VERSION = "0.11.7.54"', 'REMOTE_VERSION = "0.11.7.54"',
    "Vex Agent Runtime v0.11.7.54 installed.", "Keep VexNative v0.11.7.49 on the iPhone",
]:
    if marker not in installer:
        raise SystemExit(f"v0.11.7.54 installer marker missing: {marker}")

for forbidden in [
    'bridge_get("/windows/windows"', '"recent_proposals":', '"source_url":',
    '"artifact_path":', '"window_title":',
]:
    if forbidden in remote:
        raise SystemExit(f"v0.11.7.54 public relay privacy boundary violated: {forbidden}")

print("Applied v0.11.7.54 Windows-native access + autonomous supervisor remote control v2")
