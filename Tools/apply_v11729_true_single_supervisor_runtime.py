#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

BRIDGE = Path('Bridge/vex_bridge.py')
REMOTE = Path('Tools/VexRemoteSupport.py')
DOCTOR = Path('Tools/VexDoctor.py')
INSTALLER = Path('Tools/VexInstall11722.py')

bridge = BRIDGE.read_text(encoding='utf-8')
remote = REMOTE.read_text(encoding='utf-8')
doctor = DOCTOR.read_text(encoding='utf-8')
installer = INSTALLER.read_text(encoding='utf-8')

for label, text, marker in [
    ('Bridge', bridge, '"version": "0.11.7.28"'),
    ('Remote', remote, 'VERSION = "0.11.7.28"'),
    ('Doctor', doctor, 'VERSION = "0.11.7.28"'),
    ('Installer', installer, "VERSION='0.11.7.28'"),
]:
    if marker not in text:
        raise SystemExit(f'v0.11.7.29 expected {label} v0.11.7.28 marker missing')

bridge = bridge.replace('"version": "0.11.7.28"', '"version": "0.11.7.29"')
remote = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.29"', remote, count=1, flags=re.M)
doctor = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.29"', doctor, count=1, flags=re.M)
installer = installer.replace("VERSION='0.11.7.28'", "VERSION='0.11.7.29'", 1)

# Field evidence from the first v0.11.7.28 install showed two remaining defects:
# 1) an already-running legacy PowerShell watchdog survived the installer cutover;
# 2) Remote Support still retained the old watchdog fallback and old-folder discovery.
# Make the installed Remote Support executable's own directory authoritative and
# make recovery direct-only. No code path may launch the retired watchdog again.

project_home_pattern = re.compile(
    r'def _vex_project_home\(\) -> Path \| None:\n.*?\n\ndef _project_process_count\(image_name: str\) -> int:',
    re.S,
)
project_home_match = project_home_pattern.search(remote)
if not project_home_match:
    raise SystemExit('v0.11.7.29 project-home function anchor missing')
project_home_replacement = '''def _vex_project_home() -> Path | None:
    # Installed Remote Support and Bridge are coordinated siblings. Prefer the
    # running relay's own directory so stale extracted builds under Downloads
    # can never become the recovery target.
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent)
    else:
        candidates.append(Path(__file__).resolve().parent.parent)
    downloads = Path.home() / "Downloads"
    try:
        for child in downloads.iterdir():
            if child.is_dir() and (child / "VexBridge.exe").exists() and (child / "VexRemoteSupport.exe").exists():
                candidates.append(child)
    except Exception:
        pass
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        if (candidate / "VexBridge.exe").exists():
            return candidate
    return None


def _project_process_count(image_name: str) -> int:'''
remote = remote[:project_home_match.start()] + project_home_replacement + remote[project_home_match.end():]

runtime_dir_pattern = re.compile(
    r'def bridge_runtime_dir\(\) -> Path \| None:\n.*?\n\ndef bridge_process_count\(\) -> int:',
    re.S,
)
runtime_dir_match = runtime_dir_pattern.search(remote)
if not runtime_dir_match:
    raise SystemExit('v0.11.7.29 bridge_runtime_dir anchor missing')
runtime_dir_replacement = '''def bridge_runtime_dir() -> Path | None:
    # Never search legacy self-heal folders first. The active Remote Support
    # binary's sibling Bridge is the single recovery target.
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent)
    else:
        candidates.append(Path(__file__).resolve().parent.parent)
    for candidate in candidates:
        if (candidate / "VexBridge.exe").exists():
            return candidate
    return _vex_project_home()


def bridge_process_count() -> int:'''
remote = remote[:runtime_dir_match.start()] + runtime_dir_replacement + remote[runtime_dir_match.end():]

# Harden watchdog termination to catch versioned watchdog scripts and launcher
# shells, not only the historical exact VexBridgeWatchdog.ps1 filename.
watch_stop_pattern = re.compile(
    r'def _stop_bridge_watchdogs\(\) -> int:\n.*?\n\ndef _wait_bridge_listener\(seconds: float\) -> dict:',
    re.S,
)
watch_stop_match = watch_stop_pattern.search(remote)
if not watch_stop_match:
    raise SystemExit('v0.11.7.29 watchdog-stop helper anchor missing')
watch_stop_replacement = r'''def _stop_bridge_watchdogs() -> int:
    script = (
        "$items=Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | "
        "Where-Object {$_.CommandLine -and ("
        "$_.CommandLine -like '*VexBridgeWatchdog*' -or "
        "$_.CommandLine -like '*START-VEX-SELF-HEAL*')};"
        "$n=0; foreach($p in $items){try{Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop;$n++}catch{}};"
        "Write-Output $n"
    )
    try:
        result = run_quiet(["powershell.exe", "-NoProfile", "-Command", script], timeout=20)
        lines = [x.strip() for x in str(result.stdout or "").splitlines() if x.strip()]
        return int(lines[-1]) if lines else 0
    except Exception:
        return 0


def _wait_bridge_listener(seconds: float) -> dict:'''
remote = remote[:watch_stop_match.start()] + watch_stop_replacement + remote[watch_stop_match.end():]

recovery_pattern = re.compile(
    r'def _bounded_bridge_recovery\(\) -> dict:\n.*?\n\ndef _bridge_health_monitor\(worker\) -> None:',
    re.S,
)
recovery_match = recovery_pattern.search(remote)
if not recovery_match:
    raise SystemExit('v0.11.7.29 bounded recovery anchor missing')
recovery_replacement = '''def _bounded_bridge_recovery() -> dict:
    before = _bridge_health_public()
    watchdogs_stopped = _stop_bridge_watchdogs()
    stopped = _project_stop("bridge")

    deadline = time.time() + 12.0
    while _project_process_count("VexBridge.exe") > 0 and time.time() < deadline:
        time.sleep(0.5)

    direct = _project_start("bridge")
    direct_health = _wait_bridge_listener(90.0)
    return {
        "ok": bool(direct_health.get("reachable")),
        "reachable": bool(direct_health.get("reachable")),
        "mode": "remote_support_direct_only",
        "before_process_count": int(before.get("process_count") or 0),
        "after_process_count": _project_process_count("VexBridge.exe"),
        "watchdogs_stopped": watchdogs_stopped,
        "stop_ok": bool(stopped.get("ok")),
        "direct_start_ok": bool(direct.get("ok")),
        "bridge_version": direct_health.get("version"),
        "error_class": direct_health.get("error_class"),
        "scope": "single-remote-support-owner",
    }


def _bridge_health_monitor(worker) -> None:'''
remote = remote[:recovery_match.start()] + recovery_replacement + remote[recovery_match.end():]

# Disable the obsolete project-control watchdog start branch even if an old
# launcher file survives somewhere outside the active runtime directory.
watchdog_start_pattern = re.compile(
    r'    if key == "watchdog":\n.*?\n    image = PROJECT_PROCESS_NAMES.get\(key\)',
    re.S,
)
watchdog_start_match = watchdog_start_pattern.search(remote)
if not watchdog_start_match:
    raise SystemExit('v0.11.7.29 watchdog project-start branch missing')
watchdog_start_replacement = '''    if key == "watchdog":
        return {"ok": False, "error": "legacy watchdog retired in v0.11.7.29"}
    image = PROJECT_PROCESS_NAMES.get(key)'''
remote = remote[:watchdog_start_match.start()] + watchdog_start_replacement + remote[watchdog_start_match.end():]

# Safe self-updates must restart Bridge directly, never resurrect the retired
# START-VEX-SELF-HEAL launcher.
safe_update_old = "        f\"if (Test-Path -LiteralPath '{home_q}\\\\START-VEX-SELF-HEAL.cmd') {{ Start-Process -FilePath '{home_q}\\\\START-VEX-SELF-HEAL.cmd' -WorkingDirectory '{home_q}' }}\",\n"
safe_update_new = "        f\"if (Test-Path -LiteralPath '{home_q}\\\\VexBridge.exe') {{ Start-Process -FilePath '{home_q}\\\\VexBridge.exe' -WorkingDirectory '{home_q}' -WindowStyle Hidden }}\",\n"
if safe_update_old not in remote:
    raise SystemExit('v0.11.7.29 safe-update watchdog restart anchor missing')
remote = remote.replace(safe_update_old, safe_update_new, 1)

# Installer cutover must terminate an already-running legacy watchdog process,
# not merely rename its script and disable future scheduled launches.
retire_anchor = "    script=r'''$ErrorActionPreference='SilentlyContinue'\nGet-ScheduledTask | ForEach-Object {\n"
retire_replacement = "    script=r'''$ErrorActionPreference='SilentlyContinue'\nGet-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -and ($_.CommandLine -like '*VexBridgeWatchdog*' -or $_.CommandLine -like '*START-VEX-SELF-HEAL*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }\nStart-Sleep -Milliseconds 500\nGet-ScheduledTask | ForEach-Object {\n"
if retire_anchor not in installer:
    raise SystemExit('v0.11.7.29 installer retire process anchor missing')
installer = installer.replace(retire_anchor, retire_replacement, 1)

# Update the two installer notices without broad text churn.
installer = installer.replace(
    'single Bridge recovery owner during stabilization; legacy watchdog/self-heal launchers were retired.',
    'single Bridge recovery owner; live and scheduled legacy watchdog/self-heal supervisors were retired.',
)
installer = installer.replace(
    'Legacy watchdog/self-heal launchers were retired so Remote Support is the single Bridge recovery owner during stabilization.',
    'Live and scheduled legacy watchdog/self-heal supervisors were retired; Remote Support is the single Bridge recovery owner.',
)

BRIDGE.write_text(bridge, encoding='utf-8')
REMOTE.write_text(remote, encoding='utf-8')
DOCTOR.write_text(doctor, encoding='utf-8')
INSTALLER.write_text(installer, encoding='utf-8')

compile(bridge, str(BRIDGE), 'exec')
compile(remote, str(REMOTE), 'exec')
compile(doctor, str(DOCTOR), 'exec')
compile(installer, str(INSTALLER), 'exec')

for marker in [
    '"version": "0.11.7.29"',
    'Local\\\\VexBridge-v11726-single-instance',
]:
    if marker not in bridge:
        raise SystemExit(f'v0.11.7.29 Bridge verifier missing: {marker}')
for marker in [
    'VERSION = "0.11.7.29"',
    '"mode": "remote_support_direct_only"',
    '"scope": "single-remote-support-owner"',
    'legacy watchdog retired in v0.11.7.29',
    'return _vex_project_home()',
    "Path(sys.executable).resolve().parent",
]:
    if marker not in remote:
        raise SystemExit(f'v0.11.7.29 Remote verifier missing: {marker}')
for forbidden in [
    '"mode": "watchdog_fallback"',
    '_project_start("watchdog")',
    "START-VEX-SELF-HEAL.cmd' -WorkingDirectory",
]:
    if forbidden in remote:
        raise SystemExit(f'v0.11.7.29 retired watchdog path still present in Remote Support: {forbidden}')
for marker in [
    "VERSION='0.11.7.29'",
    "FILES=['VexBridge.exe','VexRemoteSupport.exe','VexDoctor.exe']",
    "Get-CimInstance Win32_Process",
    "'*VexBridgeWatchdog*'",
    'Disable-ScheduledTask',
]:
    if marker not in installer:
        raise SystemExit(f'v0.11.7.29 Installer verifier missing: {marker}')

print('Applied v0.11.7.29 true single-supervisor runtime + live watchdog retirement')
