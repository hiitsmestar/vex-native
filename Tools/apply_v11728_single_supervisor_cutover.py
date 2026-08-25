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
    ('Bridge', bridge, '"version": "0.11.7.27"'),
    ('Remote', remote, 'VERSION = "0.11.7.27"'),
    ('Doctor', doctor, 'VERSION = "0.11.7.27"'),
    ('Installer', installer, "VERSION='0.11.7.27'"),
]:
    if marker not in text:
        raise SystemExit(f'v0.11.7.28 expected {label} v0.11.7.27 marker missing')

bridge = bridge.replace('"version": "0.11.7.27"', '"version": "0.11.7.28"')
remote = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.28"', remote, count=1, flags=re.M)
doctor = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.28"', doctor, count=1, flags=re.M)
installer = installer.replace("VERSION='0.11.7.27'", "VERSION='0.11.7.28'", 1)

# Field evidence from v0.11.7.26: the legacy PowerShell watchdog/self-heal path
# repeatedly created visible console windows and competed with Remote Support's
# own Bridge recovery. Retire that duplicate supervisor while preserving the
# files under disabled names for rollback.
old_files = "FILES=['VexBridge.exe','VexRemoteSupport.exe','VexDoctor.exe','VexBridgeWatchdog-v11722.ps1']"
new_files = "FILES=['VexBridge.exe','VexRemoteSupport.exe','VexDoctor.exe']"
if old_files not in installer:
    raise SystemExit('v0.11.7.28 installer FILES anchor missing')
installer = installer.replace(old_files, new_files, 1)

old_find = "        if p.is_dir() and (p/'START-VEX-SELF-HEAL.cmd').exists() and (p/'VexBridge.exe').exists(): candidates.append(p)"
new_find = "        if p.is_dir() and (p/'VexBridge.exe').exists(): candidates.append(p)"
if old_find not in installer:
    raise SystemExit('v0.11.7.28 find_home anchor missing')
installer = installer.replace(old_find, new_find, 1)

insert_anchor = "def replace_with_retry(src:Path,dst:Path,seconds:int=35)->None:\n"
if insert_anchor not in installer:
    raise SystemExit('v0.11.7.28 replace helper anchor missing')
retire_code = r'''def retire_legacy_supervisors(home:Path)->None:
    # Disable only VexNative's known legacy supervisor entry points. Preserve
    # the files under explicit disabled names so this cutover is reversible.
    for name in ('VexBridgeWatchdog.ps1','VexBridgeWatchdog-v11722.ps1','START-VEX-SELF-HEAL.cmd'):
        p=home/name
        if not p.exists():
            continue
        disabled=p.with_name(p.name+'.disabled-v11728')
        try:
            if disabled.exists(): disabled.unlink()
            p.replace(disabled)
        except Exception:
            pass
    script=r'''$ErrorActionPreference='SilentlyContinue'
Get-ScheduledTask | ForEach-Object {
  $task=$_; $hit=$false
  foreach($a in @($task.Actions)) {
    $line=((([string]$a.Execute)+' '+([string]$a.Arguments))).ToLowerInvariant()
    if($line -like '*vexbridgewatchdog*' -or $line -like '*start-vex-self-heal.cmd*'){ $hit=$true }
  }
  if($hit){ Disable-ScheduledTask -InputObject $task -ErrorAction SilentlyContinue | Out-Null }
}
'''
    run_ps(script,timeout=30)

'''
installer = installer.replace(insert_anchor, retire_code + insert_anchor, 1)

main_anchor = "        stop_all_vex(home)\n        for name in FILES:\n"
main_replace = "        stop_all_vex(home)\n        retire_legacy_supervisors(home)\n        for name in FILES:\n"
if main_anchor not in installer:
    raise SystemExit('v0.11.7.28 installer cutover anchor missing')
installer = installer.replace(main_anchor, main_replace, 1)

watchdog_launch = "        watchdog=home/'VexBridgeWatchdog.ps1'\n        subprocess.Popen(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(watchdog)],cwd=str(home),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))\n"
if watchdog_launch not in installer:
    raise SystemExit('v0.11.7.28 watchdog launch anchor missing')
installer = installer.replace(watchdog_launch, '', 1)

old_message = "        messagebox.showinfo('Vex Install',f'Vex {VERSION} installed and Bridge verified. Remote Support now self-recovers a missing Bridge process in addition to the external watchdog.\\n\\nStart a fresh 2-hour support session.')"
new_message = "        messagebox.showinfo('Vex Install',f'Vex {VERSION} installed and Bridge verified. Legacy watchdog/self-heal launchers were retired so Remote Support is the single Bridge recovery owner during stabilization.\\n\\nStart a fresh 2-hour support session.')"
if old_message not in installer:
    raise SystemExit('v0.11.7.28 installer message anchor missing')
installer = installer.replace(old_message, new_message, 1)

BRIDGE.write_text(bridge, encoding='utf-8')
REMOTE.write_text(remote, encoding='utf-8')
DOCTOR.write_text(doctor, encoding='utf-8')
INSTALLER.write_text(installer, encoding='utf-8')

compile(bridge, str(BRIDGE), 'exec')
compile(remote, str(REMOTE), 'exec')
compile(doctor, str(DOCTOR), 'exec')
compile(installer, str(INSTALLER), 'exec')

for marker in ['"version": "0.11.7.28"', 'Local\\\\VexBridge-v11726-single-instance']:
    if marker not in bridge:
        raise SystemExit(f'v0.11.7.28 Bridge verifier missing: {marker}')
for marker in ['VERSION = "0.11.7.28"', 'Local\\\\VexRemoteSupport-v11727-single-instance', 'recovery_delay = 300 if listener_grace else 45']:
    if marker not in remote:
        raise SystemExit(f'v0.11.7.28 Remote verifier missing: {marker}')
for marker in [
    "VERSION='0.11.7.28'",
    "FILES=['VexBridge.exe','VexRemoteSupport.exe','VexDoctor.exe']",
    'def retire_legacy_supervisors(home:Path)->None:',
    "p.name+'.disabled-v11728'",
    'Disable-ScheduledTask',
    'retire_legacy_supervisors(home)',
]:
    if marker not in installer:
        raise SystemExit(f'v0.11.7.28 installer verifier missing: {marker}')
if "watchdog=home/'VexBridgeWatchdog.ps1'" in installer:
    raise SystemExit('v0.11.7.28 legacy watchdog launch still present')

print('Applied v0.11.7.28 single-supervisor cutover + legacy watchdog retirement')
