#!/usr/bin/env python3
from pathlib import Path

p = Path("Tools/VexAgentRuntimeInstall.py")
text = p.read_text(encoding="utf-8")
bridge_path = Path("Bridge/vex_bridge.py")
bridge = bridge_path.read_text(encoding="utf-8")

text = text.replace('BUNDLE_VERSION = "0.11.7.71"', 'BUNDLE_VERSION = "0.11.7.72"')
text = text.replace('Vex Agent Runtime v0.11.7.71', 'Vex Agent Runtime v0.11.7.72')
bridge = bridge.replace('"agent_runtime_bundle": "0.11.7.71"', '"agent_runtime_bundle": "0.11.7.72"')

anchor = '''        for name in RUNTIME_DIRS:\n            replace_dir(pkg / name, home / name)\n'''
replacement = '''        standalone_remote = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "VexNative" / "RemoteSupport" / "VexRemoteSupport.exe"\n        for name in RUNTIME_DIRS:\n            # Remote Support is now a separately updated persistent service.\n            # Do not overwrite its legacy runtime folder when the standalone\n            # service exists; that folder can be locked by an older process and\n            # the Agent Runtime update does not need to replace it.\n            if name == "VexRemoteSupportRuntime" and standalone_remote.exists():\n                continue\n            replace_dir(pkg / name, home / name)\n'''
if anchor not in text:
    raise SystemExit("v0.11.7.72 runtime-dir replacement anchor missing")
text = text.replace(anchor, replacement, 1)

old_launch = '''        launch(home / "VexRemoteSupportRuntime" / "VexRemoteSupport.exe", home / "VexRemoteSupportRuntime")\n'''
new_launch = '''        if standalone_remote.exists():\n            launch(standalone_remote, standalone_remote.parent)\n        else:\n            launch(home / "VexRemoteSupportRuntime" / "VexRemoteSupport.exe", home / "VexRemoteSupportRuntime")\n'''
if old_launch not in text:
    raise SystemExit("v0.11.7.72 Remote Support launch anchor missing")
text = text.replace(old_launch, new_launch, 1)

p.write_text(text, encoding="utf-8")
bridge_path.write_text(bridge, encoding="utf-8")
compile(text, str(p), "exec")
compile(bridge, str(bridge_path), "exec")

for marker in [
    'BUNDLE_VERSION = "0.11.7.72"',
    'standalone_remote = Path(os.environ.get("LOCALAPPDATA")',
    'if name == "VexRemoteSupportRuntime" and standalone_remote.exists():',
    'launch(standalone_remote, standalone_remote.parent)',
]:
    if marker not in text:
        raise SystemExit(f"v0.11.7.72 verifier missing: {marker}")
if '"agent_runtime_bundle": "0.11.7.72"' not in bridge:
    raise SystemExit("v0.11.7.72 Bridge bundle identity missing")
print("Applied v0.11.7.72 installer standalone Remote Support handoff fix")
