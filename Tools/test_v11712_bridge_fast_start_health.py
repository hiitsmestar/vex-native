#!/usr/bin/env python3
from pathlib import Path

bridge = Path("Bridge/vex_bridge.py").read_text(encoding="utf-8")
remote = Path("Tools/VexRemoteSupport.py").read_text(encoding="utf-8")

required_bridge = [
    '"version": "0.11.7.12"',
    'def initial_index_rebuild()',
    'name="VexInitialIndex"',
    'target=initial_index_rebuild',
    'start_background_reindex(state)',
]
required_remote = [
    'VERSION = "0.11.7.12"',
    'def _bridge_health_public()',
    'def _bounded_bridge_recovery()',
    'def _bridge_health_monitor(worker)',
    'name="VexBridgeHealthMonitor"',
    'post_comment("bridge_health_changed", health)',
    'post_comment("health_heartbeat"',
    'post_comment("bridge_auto_recovery", recovery)',
    'now - unreachable_since >= 180',
    'now - last_recovery >= 600',
    'bool(worker.allow_maintenance())',
    'action == "bridge_health"',
    'action == "safe_update"',
    'http://127.0.0.1:11434/api/chat',
]

for marker in required_bridge:
    if marker not in bridge:
        raise SystemExit(f"missing Bridge marker: {marker}")
for marker in required_remote:
    if marker not in remote:
        raise SystemExit(f"missing Remote Support marker: {marker}")

needle = '    state.index.rebuild()\n    start_background_reindex(state)'
if needle in bridge:
    raise SystemExit("blocking initial Bridge rebuild still present")

for forbidden in ['action == "shell"', 'action == "exec"', 'action == "powershell"']:
    if forbidden in remote:
        raise SystemExit(f"unsafe generic remote action unexpectedly present: {forbidden}")

compile(bridge, "Bridge/vex_bridge.py", "exec")
compile(remote, "Tools/VexRemoteSupport.py", "exec")
print("v0.11.7.12 fast-start + autonomous health tests passed")
