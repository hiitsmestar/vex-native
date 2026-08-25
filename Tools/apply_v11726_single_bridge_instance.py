#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

BRIDGE = Path('Bridge/vex_bridge.py')
REMOTE = Path('Tools/VexRemoteSupport.py')
DOCTOR = Path('Tools/VexDoctor.py')
INSTALLER = Path('Tools/VexInstall11722.py')
WATCHDOG = Path('Tools/VexBridgeWatchdog-v11722.ps1')

bridge = BRIDGE.read_text(encoding='utf-8')
remote = REMOTE.read_text(encoding='utf-8')
doctor = DOCTOR.read_text(encoding='utf-8')
installer = INSTALLER.read_text(encoding='utf-8')
watchdog = WATCHDOG.read_text(encoding='utf-8')

for label, text, marker in [
    ('Bridge', bridge, '"version": "0.11.7.25"'),
    ('Remote', remote, 'VERSION = "0.11.7.25"'),
    ('Doctor', doctor, 'VERSION = "0.11.7.25"'),
    ('Installer', installer, "VERSION='0.11.7.25'"),
]:
    if marker not in text:
        raise SystemExit(f'v0.11.7.26 expected {label} v0.11.7.25 marker missing')

bridge = bridge.replace('"version": "0.11.7.25"', '"version": "0.11.7.26"')
remote = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.26"', remote, count=1, flags=re.M)
doctor = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.26"', doctor, count=1, flags=re.M)
installer = installer.replace("VERSION='0.11.7.25'", "VERSION='0.11.7.26'", 1)
watchdog = watchdog.replace('0.11.7.25', '0.11.7.26')

# Field evidence from v0.11.7.24 showed multiple Bridge launches while the
# watchdog and Remote Support were both trying to recover the same dead process.
# A Windows named mutex makes VexBridge itself the final authority: regardless
# of how many supervisors race, only one Bridge instance may stay alive.
state_anchor = 'STATE: BridgeState | None = None\n\n\n'
if state_anchor not in bridge:
    raise SystemExit('v0.11.7.26 Bridge STATE anchor missing')
instance_helper = r'''_BRIDGE_INSTANCE_HANDLE = None


def acquire_bridge_single_instance() -> bool:
    global _BRIDGE_INSTANCE_HANDLE
    if not sys.platform.startswith("win"):
        return True
    try:
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel32.CreateMutexW(None, 0, "Local\\VexBridge-v11726-single-instance")
        if not handle:
            return True
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            kernel32.CloseHandle(handle)
            return False
        _BRIDGE_INSTANCE_HANDLE = handle
        return True
    except Exception:
        # Never make mutex setup itself a startup blocker.
        return True


'''
bridge = bridge.replace(state_anchor, state_anchor + instance_helper, 1)

main_anchor = 'def main() -> None:\n    parser = argparse.ArgumentParser('
if main_anchor not in bridge:
    raise SystemExit('v0.11.7.26 Bridge main anchor missing')
bridge = bridge.replace(
    main_anchor,
    'def main() -> None:\n    if not acquire_bridge_single_instance():\n        return\n    parser = argparse.ArgumentParser(',
    1,
)

# Recheck after acquiring Remote Support's in-process recovery lock. This closes
# the small race where another supervisor launches Bridge between the initial
# process-count check and Popen().
remote_anchor = '''    try:\n        _BRIDGE_RECOVERY_LAST = time.time()\n        home = bridge_runtime_dir()\n'''
remote_replace = '''    try:\n        if bridge_process_count() > 0:\n            return {"launched": False, "reason": "already_running_after_lock"}\n        _BRIDGE_RECOVERY_LAST = time.time()\n        home = bridge_runtime_dir()\n'''
if remote_anchor not in remote:
    raise SystemExit('v0.11.7.26 Remote recovery-lock anchor missing')
remote = remote.replace(remote_anchor, remote_replace, 1)

# Give the watchdog a short post-launch settle period before the next health
# decision. The Bridge mutex handles cross-supervisor launch races; this avoids
# the watchdog immediately stacking another restart on a process still unpacking.
watch_anchor = "try{ Start-Process -FilePath $BridgeExe -WorkingDirectory $PSScriptRoot | Out-Null; Log 'Restarted VexBridge.exe.' }catch{ Log ('Launch error: '+$_.Exception.GetType().Name) }"
watch_replace = "try{ Start-Process -FilePath $BridgeExe -WorkingDirectory $PSScriptRoot -WindowStyle Hidden | Out-Null; Start-Sleep -Seconds 3; Log 'Restarted VexBridge.exe.' }catch{ Log ('Launch error: '+$_.Exception.GetType().Name) }"
if watch_anchor not in watchdog:
    raise SystemExit('v0.11.7.26 watchdog launch anchor missing')
watchdog = watchdog.replace(watch_anchor, watch_replace, 1)

BRIDGE.write_text(bridge, encoding='utf-8')
REMOTE.write_text(remote, encoding='utf-8')
DOCTOR.write_text(doctor, encoding='utf-8')
INSTALLER.write_text(installer, encoding='utf-8')
WATCHDOG.write_text(watchdog, encoding='utf-8')

compile(bridge, str(BRIDGE), 'exec')
compile(remote, str(REMOTE), 'exec')
compile(doctor, str(DOCTOR), 'exec')
compile(installer, str(INSTALLER), 'exec')

for marker in [
    '"version": "0.11.7.26"',
    'def acquire_bridge_single_instance() -> bool:',
    'Local\\\\VexBridge-v11726-single-instance',
    'if not acquire_bridge_single_instance():',
]:
    if marker not in bridge:
        raise SystemExit(f'v0.11.7.26 Bridge verifier missing: {marker}')
for marker in [
    'VERSION = "0.11.7.26"',
    'already_running_after_lock',
    'def bridge_open_ports(config: dict, connect_timeout: float = 0.035)',
]:
    if marker not in remote:
        raise SystemExit(f'v0.11.7.26 Remote verifier missing: {marker}')
if "VERSION='0.11.7.26'" not in installer:
    raise SystemExit('v0.11.7.26 Installer version missing')
if '0.11.7.26' not in watchdog or '-WindowStyle Hidden' not in watchdog:
    raise SystemExit('v0.11.7.26 Watchdog verifier missing')

print('Applied v0.11.7.26 single Bridge instance + supervisor race hardening')
