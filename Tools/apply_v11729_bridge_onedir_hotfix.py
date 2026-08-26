#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path

INSTALLER = Path('Tools/VexInstall11722.py')
installer = INSTALLER.read_text(encoding='utf-8')

marker = "REMOTE_RUNTIME_DIR='VexRemoteSupportRuntime'"
if marker not in installer:
    raise SystemExit('v0.11.7.29 Remote runtime marker missing')
installer = installer.replace(marker, marker + "\nBRIDGE_RUNTIME_DIR='VexBridgeRuntime'", 1)

verify_anchor = "        remote_src=pkg/REMOTE_RUNTIME_DIR\n        if not (remote_src/'VexRemoteSupport.exe').exists(): raise RuntimeError('Package folder missing: VexRemoteSupportRuntime')\n"
verify_extra = verify_anchor + "        bridge_runtime_src=pkg/BRIDGE_RUNTIME_DIR\n        if not bridge_runtime_src.exists(): raise RuntimeError('Package folder missing: VexBridgeRuntime')\n"
if verify_anchor not in installer:
    raise SystemExit('Bridge hotfix package verification anchor missing')
installer = installer.replace(verify_anchor, verify_extra, 1)

copy_anchor = "        remote_dst=home/REMOTE_RUNTIME_DIR\n        if remote_dst.exists(): shutil.rmtree(remote_dst,ignore_errors=True)\n        shutil.copytree(remote_src,remote_dst)\n"
copy_extra = copy_anchor + "        bridge_runtime_dst=home/BRIDGE_RUNTIME_DIR\n        if bridge_runtime_dst.exists(): shutil.rmtree(bridge_runtime_dst,ignore_errors=True)\n        shutil.copytree(bridge_runtime_src,bridge_runtime_dst)\n"
if copy_anchor not in installer:
    raise SystemExit('Bridge hotfix install-copy anchor missing')
installer = installer.replace(copy_anchor, copy_extra, 1)

INSTALLER.write_text(installer, encoding='utf-8')
compile(installer, str(INSTALLER), 'exec')

for required in [
    "BRIDGE_RUNTIME_DIR='VexBridgeRuntime'",
    "bridge_runtime_src=pkg/BRIDGE_RUNTIME_DIR",
    "bridge_runtime_dst=home/BRIDGE_RUNTIME_DIR",
    "shutil.copytree(bridge_runtime_src,bridge_runtime_dst)",
]:
    if required not in installer:
        raise SystemExit(f'Bridge hotfix verifier missing: {required}')

print('Applied v0.11.7.29 Bridge onedir runtime hotfix')
