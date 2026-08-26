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

bridge = bridge.replace('"version": "0.11.7.28"', '"version": "0.11.7.29"', 1)
remote = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.29"', remote, count=1, flags=re.M)
doctor = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.29"', doctor, count=1, flags=re.M)
installer = installer.replace("VERSION='0.11.7.28'", "VERSION='0.11.7.29'", 1)

# Remote Support is deliberately shipped as a PyInstaller one-folder runtime.
# This avoids the self-extracting one-file wrapper that Defender was objecting to
# while leaving Bridge and Doctor behavior unchanged from the proven .28 chain.
old_files = "FILES=['VexBridge.exe','VexRemoteSupport.exe','VexDoctor.exe']"
new_files = "FILES=['VexBridge.exe','VexDoctor.exe']\nREMOTE_RUNTIME_DIR='VexRemoteSupportRuntime'"
if old_files not in installer:
    raise SystemExit('v0.11.7.29 installer FILES anchor missing')
installer = installer.replace(old_files, new_files, 1)

verify_anchor = "        for name in FILES:\n            if not (pkg/name).exists(): raise RuntimeError(f'Package file missing: {name}')\n"
verify_replacement = verify_anchor + "        remote_src=pkg/REMOTE_RUNTIME_DIR\n        if not (remote_src/'VexRemoteSupport.exe').exists(): raise RuntimeError('Package folder missing: VexRemoteSupportRuntime')\n"
if verify_anchor not in installer:
    raise SystemExit('v0.11.7.29 package verification anchor missing')
installer = installer.replace(verify_anchor, verify_replacement, 1)

copy_anchor = "        for name in FILES:\n            dstname='VexBridgeWatchdog.ps1' if name.endswith('v11722.ps1') else name\n            replace_with_retry(pkg/name,home/dstname)\n"
copy_replacement = copy_anchor + "        old_remote=home/'VexRemoteSupport.exe'\n        if old_remote.exists():\n            disabled=home/'VexRemoteSupport.exe.disabled-v11729'\n            try:\n                if disabled.exists(): disabled.unlink()\n                old_remote.replace(disabled)\n            except Exception:\n                pass\n        remote_dst=home/REMOTE_RUNTIME_DIR\n        if remote_dst.exists(): shutil.rmtree(remote_dst,ignore_errors=True)\n        shutil.copytree(remote_src,remote_dst)\n"
if copy_anchor not in installer:
    raise SystemExit('v0.11.7.29 install copy anchor missing')
installer = installer.replace(copy_anchor, copy_replacement, 1)

old_launch = "        subprocess.Popen([str(home/'VexRemoteSupport.exe')],cwd=str(home))\n"
new_launch = "        subprocess.Popen([str(home/REMOTE_RUNTIME_DIR/'VexRemoteSupport.exe')],cwd=str(home/REMOTE_RUNTIME_DIR))\n"
if old_launch not in installer:
    raise SystemExit('v0.11.7.29 Remote Support launch anchor missing')
installer = installer.replace(old_launch, new_launch, 1)

# Keep .28 single-supervisor retirement semantics intact, but give the success
# text a precise packaging identity so field screenshots reveal the right build.
installer = installer.replace(
    'single Bridge recovery owner during stabilization.',
    'single Bridge recovery owner during stabilization. Remote Support is installed as a Defender-safer one-folder runtime.',
)

BRIDGE.write_text(bridge, encoding='utf-8')
REMOTE.write_text(remote, encoding='utf-8')
DOCTOR.write_text(doctor, encoding='utf-8')
INSTALLER.write_text(installer, encoding='utf-8')

for path in (BRIDGE, REMOTE, DOCTOR, INSTALLER):
    compile(path.read_text(encoding='utf-8'), str(path), 'exec')

for marker in ['"version": "0.11.7.29"', 'Local\\\\VexBridge-v11726-single-instance']:
    if marker not in bridge:
        raise SystemExit(f'v0.11.7.29 Bridge verifier missing: {marker}')
for marker in ['VERSION = "0.11.7.29"', 'Local\\\\VexRemoteSupport-v11727-single-instance', 'recovery_delay = 300 if listener_grace else 45']:
    if marker not in remote:
        raise SystemExit(f'v0.11.7.29 Remote verifier missing: {marker}')
for marker in [
    "VERSION='0.11.7.29'",
    "FILES=['VexBridge.exe','VexDoctor.exe']",
    "REMOTE_RUNTIME_DIR='VexRemoteSupportRuntime'",
    "remote_src=pkg/REMOTE_RUNTIME_DIR",
    "shutil.copytree(remote_src,remote_dst)",
    "home/REMOTE_RUNTIME_DIR/'VexRemoteSupport.exe'",
    'retire_legacy_supervisors(home)',
]:
    if marker not in installer:
        raise SystemExit(f'v0.11.7.29 installer verifier missing: {marker}')
if "subprocess.Popen([str(home/'VexRemoteSupport.exe')]" in installer:
    raise SystemExit('v0.11.7.29 legacy standalone Remote Support launch remains')

print('Applied v0.11.7.29 Defender-safe Remote Support one-folder packaging')
