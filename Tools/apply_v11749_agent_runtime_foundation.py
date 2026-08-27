#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
REMOTE = Path("Tools/VexRemoteSupport.py")

bridge = BRIDGE.read_text(encoding="utf-8")
remote = REMOTE.read_text(encoding="utf-8")

# v0.11.7.49 Agent Runtime Foundation
#
# The full source chain already contains persistent memory, adaptive learning,
# autonomous improvement and initiative. Two deployment/runtime problems kept
# important pieces dark on the field machine:
#
# 1. Persistent memory was assigned loopback port 8766. The later unified local
#    control plane also prefers external Bridge port + 1 (8766) and starts first.
#    That makes VexMemoryWorker fail to bind whenever Bridge owns its normal local
#    control port. Move the local-only memory worker outside the Bridge control
#    port ring (8766-8777).
# 2. The recent cognition-helper deployment shipped only Bridge + runtime, so the
#    companion Memory/Doctor/Toolbox binaries were absent from that update. The
#    new Agent Runtime packaging workflow restores those binaries; this patch
#    makes the source explicitly verify the required integration markers.

if '"version": "0.11.7.39"' not in bridge:
    raise SystemExit("v0.11.7.49 expected Bridge v0.11.7.39 source")

old_port = "MEMORY_WORKER_PORT = 8766"
new_port = "MEMORY_WORKER_PORT = 8786"
if old_port in bridge:
    bridge = bridge.replace(old_port, new_port, 1)
elif new_port not in bridge:
    raise SystemExit("v0.11.7.49 persistent-memory port marker missing")

# Keep the deployed Bridge protocol/version identity at .39 so the proven .48
# iPhone pairing and status contract remain unchanged. Publish a separate bundle
# marker for diagnostics without lying about the Bridge protocol revision.
status_anchor = '"local_control_protocol": "vex-local-v1",'
if status_anchor in bridge and '"agent_runtime_bundle": "0.11.7.49"' not in bridge:
    bridge = bridge.replace(
        status_anchor,
        status_anchor + '\n                "agent_runtime_bundle": "0.11.7.49",',
        1,
    )

# The isolated background worker patch must still be present after the entire
# Windows patch chain. Fail the build rather than silently shipping a bundle that
# can chat but cannot learn or take low-risk initiative in the background.
required_bridge_markers = [
    "MEMORY_WORKER_BASE",
    "VexMemoryWorker.exe",
    'parsed.path == "/memory/status"',
    'parsed.path == "/memory/sync"',
    "def _adaptive_worker_cycle(",
    "def _autonomy_worker_loop(",
    "def _initiative_scheduler_loop(",
    'name="VexAdaptiveLearning"',
    'name="VexAutonomousImprovement"',
    'name="VexInitiativeScheduler"',
    "IDLE_AUTONOMY_HARD_FLOOR_BYTES",
    "IDLE_AUTONOMY_PLANNER_FLOOR_BYTES",
    '"version": "0.11.7.39"',
]
for marker in required_bridge_markers:
    if marker not in bridge:
        raise SystemExit(f"v0.11.7.49 Bridge capability regressed: {marker}")

# Remote Support remains the single recovery owner from the proven Defender-safe
# line. It must retain the modern local-control/status commands used for unattended
# diagnosis. The bundle does not publish private local config or support state.
for marker in [
    'VERSION = "0.11.7.29"',
    'action == "learning_status"',
    'action == "maintenance_status"',
    'action == "adaptive_status"',
]:
    if marker not in remote:
        raise SystemExit(f"v0.11.7.49 Remote Support capability regressed: {marker}")

BRIDGE.write_text(bridge, encoding="utf-8")
compile(bridge, str(BRIDGE), "exec")
compile(remote, str(REMOTE), "exec")

print("Applied v0.11.7.49 Agent Runtime foundation: memory port collision fixed and capability graph verified")
