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
    ('Bridge', bridge, '"version": "0.11.7.26"'),
    ('Remote', remote, 'VERSION = "0.11.7.26"'),
    ('Doctor', doctor, 'VERSION = "0.11.7.26"'),
    ('Installer', installer, "VERSION='0.11.7.26'"),
]:
    if marker not in text:
        raise SystemExit(f'v0.11.7.27 expected {label} v0.11.7.26 marker missing')
if '0.11.7.26' not in watchdog:
    raise SystemExit('v0.11.7.27 expected watchdog v0.11.7.26 marker missing')

bridge = bridge.replace('"version": "0.11.7.26"', '"version": "0.11.7.27"')
remote = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.27"', remote, count=1, flags=re.M)
doctor = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.27"', doctor, count=1, flags=re.M)
installer = installer.replace("VERSION='0.11.7.26'", "VERSION='0.11.7.27'", 1)
watchdog = watchdog.replace('0.11.7.26', '0.11.7.27')

# Field evidence from v0.11.7.26: the loopback listener accepts TCP and reports
# startup stage "listening", but the 1.25 s HTTP cap produces ReadTimeout on the
# older/low-memory Windows host. Recovery then restarts a Bridge that is alive
# but busy warming up, repeatedly resetting its startup age.
old_get_timeout = '_BRIDGE_SESSION.get(url, params=params, timeout=min(float(timeout), 1.25))'
new_get_timeout = '_BRIDGE_SESSION.get(url, params=params, timeout=min(max(float(timeout), 2.0), 4.0))'
if old_get_timeout not in remote:
    raise SystemExit('v0.11.7.27 bounded GET timeout anchor missing')
remote = remote.replace(old_get_timeout, new_get_timeout, 1)

old_recovery = '        if allowed and now - unreachable_since >= 45 and now - last_recovery >= 600:\n'
new_recovery = '''        listener_grace = bool(health.get("tcp_reachable")) and str(health.get("startup_stage") or "") in {"listening", "local_only"}\n        recovery_delay = 300 if listener_grace else 45\n        if allowed and now - unreachable_since >= recovery_delay and now - last_recovery >= 600:\n'''
if old_recovery not in remote:
    raise SystemExit('v0.11.7.27 recovery-delay anchor missing')
remote = remote.replace(old_recovery, new_recovery, 1)

# A second Remote Support window creates a second independent health monitor.
# Make the desktop relay single-instance too, so two monitors cannot alternate
# destructive Bridge recovery decisions. PyInstaller onefile's bootloader/child
# pair is one application; the mutex is acquired by the Python child.
main_match = re.search(r'(?m)^def main\(\) -> int:\s*$', remote)
if not main_match:
    raise SystemExit('v0.11.7.27 Remote main declaration missing')
remote_instance_helper = r'''_REMOTE_INSTANCE_HANDLE = None


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
        handle = kernel32.CreateMutexW(None, 0, "Local\\VexRemoteSupport-v11727-single-instance")
        if not handle:
            return True
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            kernel32.CloseHandle(handle)
            return False
        _REMOTE_INSTANCE_HANDLE = handle
        return True
    except Exception:
        return True


'''
remote = remote[:main_match.start()] + remote_instance_helper + remote[main_match.start():]
main_match = re.search(r'(?m)^def main\(\) -> int:\s*$', remote)
main_guard = 'def main() -> int:\n    if not acquire_remote_single_instance():\n        return 0'
remote = remote[:main_match.start()] + main_guard + remote[main_match.end():]

# The external watchdog gets the same patience. It still requires a real 200
# /status response, but it allows a five-minute warm-up window before killing a
# running process and gives each status request enough time on this host.
if '-TimeoutSec 3' not in watchdog:
    raise SystemExit('v0.11.7.27 watchdog HTTP timeout anchor missing')
watchdog = watchdog.replace('-TimeoutSec 3', '-TimeoutSec 6')
if 'AddSeconds(90)' not in watchdog:
    raise SystemExit('v0.11.7.27 watchdog restart grace anchor missing')
watchdog = watchdog.replace('AddSeconds(90)', 'AddSeconds(300)')

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
    '"version": "0.11.7.27"',
    'Local\\\\VexBridge-v11726-single-instance',
]:
    if marker not in bridge:
        raise SystemExit(f'v0.11.7.27 Bridge verifier missing: {marker}')
for marker in [
    'VERSION = "0.11.7.27"',
    'timeout=min(max(float(timeout), 2.0), 4.0)',
    'recovery_delay = 300 if listener_grace else 45',
    'def acquire_remote_single_instance() -> bool:',
    'Local\\\\VexRemoteSupport-v11727-single-instance',
    'if not acquire_remote_single_instance():',
]:
    if marker not in remote:
        raise SystemExit(f'v0.11.7.27 Remote verifier missing: {marker}')
if "VERSION='0.11.7.27'" not in installer:
    raise SystemExit('v0.11.7.27 Installer version missing')
for marker in ['0.11.7.27', '-TimeoutSec 6', 'AddSeconds(300)', '-WindowStyle Hidden']:
    if marker not in watchdog:
        raise SystemExit(f'v0.11.7.27 Watchdog verifier missing: {marker}')

print('Applied v0.11.7.27 patient Bridge health + single Remote Support instance')
