#!/usr/bin/env python3
from pathlib import Path
import re

bridge_path = Path('Bridge/vex_bridge.py')
remote_path = Path('Tools/VexRemoteSupport.py')
bridge = bridge_path.read_text(encoding='utf-8')
remote = remote_path.read_text(encoding='utf-8')

bridge = bridge.replace('"version": "0.11.7.14"', '"version": "0.11.7.15"')
remote = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.15"', remote, count=1, flags=re.M)

bridge_path.write_text(bridge, encoding='utf-8')
remote_path.write_text(remote, encoding='utf-8')
compile(bridge, str(bridge_path), 'exec')
compile(remote, str(remote_path), 'exec')

if '"version": "0.11.7.15"' not in bridge:
    raise SystemExit('Bridge v0.11.7.15 marker missing')
if 'VERSION = "0.11.7.15"' not in remote:
    raise SystemExit('Remote Support v0.11.7.15 marker missing')
print('Applied v0.11.7.15 installer lock fix version bump')
