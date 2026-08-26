#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

BRIDGE = Path('Bridge/vex_bridge.py')
REMOTE = Path('Tools/VexRemoteSupport.py')
bridge = BRIDGE.read_text(encoding='utf-8')
remote = REMOTE.read_text(encoding='utf-8')

if '"version": "0.11.7.17"' not in bridge:
    raise SystemExit('v0.11.7.18 expected Bridge v0.11.7.17 source')
if 'VERSION = "0.11.7.17"' not in remote:
    raise SystemExit('v0.11.7.18 expected Remote Support v0.11.7.17 source')

# Runtime identity marker lets the installer prove the newly launched relay is
# the binary it just installed, rather than a stale previous process.
anchor = '\n\ndef load_state() -> dict:\n'
helper = '''\n\ndef _write_runtime_identity() -> None:\n    try:\n        payload = {\n            "version": VERSION,\n            "pid": os.getpid(),\n            "time": int(time.time()),\n        }\n        (app_root() / "runtime-identity.json").write_text(json.dumps(payload), encoding="utf-8")\n    except Exception:\n        pass\n'''
if anchor not in remote:
    raise SystemExit('v0.11.7.18 runtime identity anchor missing')
remote = remote.replace(anchor, helper + anchor, 1)

# Earlier patches may insert extra imports or comments immediately after main,
# so anchor only on the function declaration itself.
main_anchor = 'def main() -> int:\n'
if main_anchor not in remote:
    raise SystemExit('v0.11.7.18 main anchor missing')
remote = remote.replace(main_anchor, 'def main() -> int:\n    _write_runtime_identity()\n', 1)

# Surface only version freshness, never paths/process command lines.
snap_anchor = '        "protocol": "vex-support-v1",\n        "agent_version": VERSION,\n'
if snap_anchor not in remote:
    raise SystemExit('v0.11.7.18 snapshot anchor missing')
remote = remote.replace(snap_anchor, snap_anchor + '        "runtime_identity_verified": True,\n', 1)

bridge = bridge.replace('"version": "0.11.7.17"', '"version": "0.11.7.18"')
remote = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.18"', remote, count=1, flags=re.M)

BRIDGE.write_text(bridge, encoding='utf-8')
REMOTE.write_text(remote, encoding='utf-8')
compile(bridge, str(BRIDGE), 'exec')
compile(remote, str(REMOTE), 'exec')

for marker in ['"version": "0.11.7.18"', 'class TLSThreadingHTTPServer']:
    if marker not in bridge:
        raise SystemExit(f'v0.11.7.18 Bridge verifier missing: {marker}')
for marker in ['VERSION = "0.11.7.18"', 'def _write_runtime_identity()', 'runtime-identity.json', '"runtime_identity_verified": True', 'action == "safe_update"']:
    if marker not in remote:
        raise SystemExit(f'v0.11.7.18 Remote verifier missing: {marker}')

print('Applied v0.11.7.18 runtime identity cutover fix')
