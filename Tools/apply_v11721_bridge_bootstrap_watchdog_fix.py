#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

BRIDGE = Path('Bridge/vex_bridge.py')
REMOTE = Path('Tools/VexRemoteSupport.py')
DOCTOR = Path('Tools/VexDoctor.py')
bridge = BRIDGE.read_text(encoding='utf-8')
remote = REMOTE.read_text(encoding='utf-8')
doctor = DOCTOR.read_text(encoding='utf-8')

if '"version": "0.11.7.20"' not in bridge:
    raise SystemExit('v0.11.7.21 expected Bridge v0.11.7.20 source')
if 'VERSION = "0.11.7.20"' not in remote:
    raise SystemExit('v0.11.7.21 expected Remote Support v0.11.7.20 source')

# v0.11.7.20 started loopback control only after the full file index rebuild.
# On this PC that can exceed the watchdog retry window after any restart, so the
# watchdog can repeatedly kill a healthy Bridge before it ever reaches listen().
# Start the local control plane immediately after STATE exists, then index in the
# foreground. Status/health remains responsive while indexing warms up.
old_state = '''    global STATE\n    STATE = state\n\n    print("\\nVex Bridge v0.7 — indexing selected folders…")\n'''
new_state = '''    global STATE\n    STATE = state\n    local_control_server = start_local_control_server(config)\n\n    print("\\nVex Bridge v0.7 — indexing selected folders…")\n'''
if old_state not in bridge:
    raise SystemExit('v0.11.7.21 STATE bootstrap anchor missing')
bridge = bridge.replace(old_state, new_state, 1)
old_late = '''    token = config["token"]\n    local_control_server = start_local_control_server(config)\n'''
new_late = '''    token = config["token"]\n'''
if old_late not in bridge:
    raise SystemExit('v0.11.7.21 late local listener anchor missing')
bridge = bridge.replace(old_late, new_late, 1)

bridge = bridge.replace('"version": "0.11.7.20"', '"version": "0.11.7.21"')
remote = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.21"', remote, count=1, flags=re.M)
doctor = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.21"', doctor, count=1, flags=re.M)

BRIDGE.write_text(bridge, encoding='utf-8')
REMOTE.write_text(remote, encoding='utf-8')
DOCTOR.write_text(doctor, encoding='utf-8')
compile(bridge, str(BRIDGE), 'exec')
compile(remote, str(REMOTE), 'exec')
compile(doctor, str(DOCTOR), 'exec')

for marker in [
    '"version": "0.11.7.21"',
    'STATE = state\n    local_control_server = start_local_control_server(config)',
    '"local_control_protocol": "vex-local-v1"',
]:
    if marker not in bridge:
        raise SystemExit(f'v0.11.7.21 Bridge verifier missing: {marker}')
if bridge.count('local_control_server = start_local_control_server(config)') != 1:
    raise SystemExit('v0.11.7.21 local control listener must start exactly once')
if 'VERSION = "0.11.7.21"' not in remote:
    raise SystemExit('v0.11.7.21 Remote Support verifier missing')
if 'VERSION = "0.11.7.21"' not in doctor:
    raise SystemExit('v0.11.7.21 Doctor verifier missing')

print('Applied v0.11.7.21 early loopback bootstrap fix')
