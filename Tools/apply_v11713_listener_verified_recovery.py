#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

REMOTE = Path("Tools/VexRemoteSupport.py")
remote = REMOTE.read_text(encoding="utf-8")

if 'VERSION = "0.11.7.12"' not in remote:
    raise SystemExit("v0.11.7.13 expected Remote Support v0.11.7.12 source")

# v0.11.7.12 incorrectly declared recovery successful when a Bridge process
# existed, even if nothing was listening. Replace that with listener-verified
# recovery and explicitly remove stale watchdog/Bridge duplicates first.
start = remote.find("def _bounded_bridge_recovery() -> dict:\n")
end = remote.find("\ndef _bridge_health_monitor(worker) -> None:\n", start)
if start < 0 or end < 0:
    raise SystemExit("v0.11.7.13 recovery function anchor missing")

replacement = r'''def _stop_bridge_watchdogs() -> int:
    script = (
        "$items=Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | "
        "Where-Object {$_.CommandLine -and $_.CommandLine -like '*VexBridgeWatchdog.ps1*'};"
        "$n=0; foreach($p in $items){try{Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop;$n++}catch{}};"
        "Write-Output $n"
    )
    try:
        result = run_quiet(["powershell.exe", "-NoProfile", "-Command", script], timeout=20)
        lines = [x.strip() for x in str(result.stdout or "").splitlines() if x.strip()]
        return int(lines[-1]) if lines else 0
    except Exception:
        return 0


def _wait_bridge_listener(seconds: float) -> dict:
    deadline = time.time() + max(1.0, float(seconds))
    last = _bridge_health_public()
    while time.time() < deadline:
        if bool(last.get("reachable")):
            return last
        time.sleep(1.0)
        last = _bridge_health_public()
    return last


def _bounded_bridge_recovery() -> dict:
    before = _bridge_health_public()
    watchdogs_stopped = _stop_bridge_watchdogs()
    stopped = _project_stop("bridge")

    deadline = time.time() + 10.0
    while _project_process_count("VexBridge.exe") > 0 and time.time() < deadline:
        time.sleep(0.5)

    # Start exactly one Bridge directly. Do not use process existence as health;
    # the HTTPS listener must answer /status with a 2xx response.
    direct = _project_start("bridge")
    direct_health = _wait_bridge_listener(30.0)
    if bool(direct_health.get("reachable")):
        return {
            "ok": True,
            "reachable": True,
            "mode": "direct_single_bridge",
            "before_process_count": int(before.get("process_count") or 0),
            "after_process_count": _project_process_count("VexBridge.exe"),
            "watchdogs_stopped": watchdogs_stopped,
            "stop_ok": bool(stopped.get("ok")),
            "direct_start_ok": bool(direct.get("ok")),
            "bridge_version": direct_health.get("version"),
            "error_class": None,
            "scope": "VexBridge-and-watchdog-only",
        }

    # If a direct launch did not produce a listener, make one clean watchdog
    # attempt so its normal crash/circuit-breaker behavior can capture the fault.
    _project_stop("bridge")
    watchdog = _project_start("watchdog")
    watchdog_health = _wait_bridge_listener(30.0)
    return {
        "ok": bool(watchdog_health.get("reachable")),
        "reachable": bool(watchdog_health.get("reachable")),
        "mode": "watchdog_fallback",
        "before_process_count": int(before.get("process_count") or 0),
        "after_process_count": _project_process_count("VexBridge.exe"),
        "watchdogs_stopped": watchdogs_stopped,
        "stop_ok": bool(stopped.get("ok")),
        "direct_start_ok": bool(direct.get("ok")),
        "watchdog_start_ok": bool(watchdog.get("ok")),
        "bridge_version": watchdog_health.get("version"),
        "error_class": watchdog_health.get("error_class"),
        "scope": "VexBridge-and-watchdog-only",
    }

'''
remote = remote[:start] + replacement + remote[end + 1:]

# The first listener recovery should not waste three minutes after startup.
remote = remote.replace(
    'if allowed and now - unreachable_since >= 180 and now - last_recovery >= 600:',
    'if allowed and now - unreachable_since >= 45 and now - last_recovery >= 600:',
    1,
)

# Make the health report explicit that the listener, not merely a process, is
# what constitutes successful Bridge recovery.
health_marker = '        "fast_start_expected": True,\n'
if health_marker not in remote:
    raise SystemExit("v0.11.7.13 health marker missing")
remote = remote.replace(
    health_marker,
    '        "fast_start_expected": True,\n        "listener_verified": reachable,\n',
    1,
)

remote = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.13"', remote, count=1, flags=re.M)
REMOTE.write_text(remote, encoding="utf-8")
compile(remote, str(REMOTE), "exec")

for marker in [
    'VERSION = "0.11.7.13"',
    'def _stop_bridge_watchdogs()',
    'def _wait_bridge_listener(seconds: float)',
    '"listener_verified": reachable',
    'now - unreachable_since >= 45',
    '"mode": "direct_single_bridge"',
    '"mode": "watchdog_fallback"',
    '"scope": "VexBridge-and-watchdog-only"',
    'action == "safe_update"',
]:
    if marker not in remote:
        raise SystemExit(f"v0.11.7.13 verifier missing: {marker}")

print("Applied v0.11.7.13 listener-verified Bridge recovery")
