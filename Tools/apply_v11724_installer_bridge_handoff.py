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
    ('Bridge', bridge, '"version": "0.11.7.23"'),
    ('Remote', remote, 'VERSION = "0.11.7.23"'),
    ('Doctor', doctor, 'VERSION = "0.11.7.23"'),
    ('Installer', installer, "VERSION='0.11.7.23'"),
]:
    if marker not in text:
        raise SystemExit(f'v0.11.7.24 expected {label} v0.11.7.23 marker missing')

bridge = bridge.replace('"version": "0.11.7.23"', '"version": "0.11.7.24"')
remote = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.24"', remote, count=1, flags=re.M)
doctor = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.24"', doctor, count=1, flags=re.M)
installer = installer.replace("VERSION='0.11.7.23'", "VERSION='0.11.7.24'", 1)
watchdog = watchdog.replace('0.11.7.23', '0.11.7.24')

# A normal Bridge launch must never block on an interactive folder picker before
# the local control listener can bind. Folder selection is explicit --setup only.
old_setup = '''    if args.setup or not config.get("folders"):\n        config["folders"] = choose_folders(config.get("folders", []))\n        save_config(config)\n'''
new_setup = '''    if args.setup:\n        config["folders"] = choose_folders(config.get("folders", []))\n        save_config(config)\n    elif not isinstance(config.get("folders"), list):\n        config["folders"] = []\n        save_config(config)\n'''
if old_setup not in bridge:
    raise SystemExit('v0.11.7.24 interactive startup-folder anchor missing')
bridge = bridge.replace(old_setup, new_setup, 1)

# Installation should hand control to Remote Support + watchdog even if the first
# Bridge health probe is still red. Remote Support is now an independent Bridge
# supervisor, so treating that transient as a fatal install error creates a dead end.
old_main = '''        subprocess.Popen([str(home/'VexBridge.exe')],cwd=str(home))\n        wait_bridge_version(VERSION,seconds=90)\n        subprocess.Popen([str(home/'VexRemoteSupport.exe')],cwd=str(home))\n        wait_remote_identity(VERSION,seconds=20)\n        watchdog=home/'VexBridgeWatchdog.ps1'\n        subprocess.Popen(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(watchdog)],cwd=str(home),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))\n        messagebox.showinfo('Vex Install',f'Vex {VERSION} installed and Bridge verified. Remote Support now self-recovers a missing Bridge process in addition to the external watchdog.\\n\\nStart a fresh 2-hour support session.')\n'''
new_main = '''        subprocess.Popen([str(home/'VexBridge.exe')],cwd=str(home))\n        bridge_warning = None\n        try:\n            wait_bridge_version(VERSION,seconds=25)\n        except Exception as exc:\n            bridge_warning = exc.__class__.__name__\n        subprocess.Popen([str(home/'VexRemoteSupport.exe')],cwd=str(home))\n        wait_remote_identity(VERSION,seconds=20)\n        watchdog=home/'VexBridgeWatchdog.ps1'\n        subprocess.Popen(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(watchdog)],cwd=str(home),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))\n        if bridge_warning:\n            messagebox.showinfo('Vex Install',f'Vex {VERSION} installed. Remote Support is live and Bridge recovery has been handed to Remote Support + watchdog.\\n\\nStart a fresh 2-hour support session.')\n        else:\n            messagebox.showinfo('Vex Install',f'Vex {VERSION} installed and Bridge verified.\\n\\nStart a fresh 2-hour support session.')\n'''
if old_main not in installer:
    raise SystemExit('v0.11.7.24 installer Bridge-verification anchor missing')
installer = installer.replace(old_main, new_main, 1)

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
    '"version": "0.11.7.24"',
    'if args.setup:',
    'elif not isinstance(config.get("folders"), list):',
]:
    if marker not in bridge:
        raise SystemExit(f'v0.11.7.24 Bridge verifier missing: {marker}')
for marker in [
    "VERSION='0.11.7.24'",
    'bridge_warning = None',
    'wait_bridge_version(VERSION,seconds=25)',
    'Bridge recovery has been handed to Remote Support + watchdog',
]:
    if marker not in installer:
        raise SystemExit(f'v0.11.7.24 installer verifier missing: {marker}')
if 'VERSION = "0.11.7.24"' not in remote:
    raise SystemExit('v0.11.7.24 Remote version missing')
if '0.11.7.24' not in watchdog:
    raise SystemExit('v0.11.7.24 watchdog version missing')

print('Applied v0.11.7.24 nonblocking Bridge bootstrap + installer recovery handoff')
