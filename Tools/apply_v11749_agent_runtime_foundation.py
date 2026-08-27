#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
REMOTE = Path("Tools/VexRemoteSupport.py")

bridge = BRIDGE.read_text(encoding="utf-8")
remote = REMOTE.read_text(encoding="utf-8")

# v0.11.7.49 Agent Runtime Foundation
#
# Restore the complete local Agent Runtime around the proven v0.11.7.39 Bridge
# without changing the working v0.11.7.48 iPhone pairing.

if '"version": "0.11.7.39"' not in bridge:
    raise SystemExit("v0.11.7.49 expected Bridge v0.11.7.39 source")

# Keep persistent memory clear of the Bridge local-control ring (8766-8777).
old_port = "MEMORY_WORKER_PORT = 8766"
new_port = "MEMORY_WORKER_PORT = 8786"
if old_port in bridge:
    bridge = bridge.replace(old_port, new_port, 1)
elif new_port not in bridge:
    raise SystemExit("v0.11.7.49 persistent-memory port marker missing")

# Give a cold frozen worker a bounded grace window while keeping memory best-effort.
old_grace = "        for _ in range(25):\n            time.sleep(0.12)\n"
new_grace = "        for _ in range(80):\n            time.sleep(0.15)\n"
if old_grace in bridge:
    bridge = bridge.replace(old_grace, new_grace, 1)
elif new_grace not in bridge:
    raise SystemExit("v0.11.7.49 memory startup grace marker missing")

# Do not transplant one frozen EXE onto Bridge's runtime. Ship Memory Worker as a
# complete independent onedir runtime and let Bridge find that packaged executable.
old_worker_exe = '''def _memory_worker_exe() -> Path:\n    # In the packaged build VexMemoryWorker.exe sits beside VexBridge.exe.\n    return Path(sys.executable).resolve().with_name("VexMemoryWorker.exe")\n'''
new_worker_exe = '''def _memory_worker_exe() -> Path:\n    base = Path(sys.executable).resolve().parent\n    packaged = base / "VexMemoryWorkerRuntime" / "VexMemoryWorker.exe"\n    if packaged.exists():\n        return packaged\n    # Backward-compatible fallback for older bundles while migrating to .49.\n    return base / "VexMemoryWorker.exe"\n'''
if old_worker_exe in bridge:
    bridge = bridge.replace(old_worker_exe, new_worker_exe, 1)
elif 'VexMemoryWorkerRuntime' not in bridge:
    raise SystemExit("v0.11.7.49 memory runtime locator anchor missing")

# A frozen parent launching a separately frozen child needs a clean PyInstaller
# environment. This is correct for the independent onedir worker too.
spawn_anchor = '''                subprocess.Popen(\n                    [str(exe), "--serve", "--port", str(MEMORY_WORKER_PORT)],\n                    cwd=str(exe.parent),\n                    stdout=subprocess.DEVNULL,\n                    stderr=subprocess.DEVNULL,\n                    creationflags=flags,\n                )\n'''
spawn_fixed = '''                child_env = os.environ.copy()\n                child_env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"\n                subprocess.Popen(\n                    [str(exe), "--serve", "--port", str(MEMORY_WORKER_PORT)],\n                    cwd=str(exe.parent),\n                    stdout=subprocess.DEVNULL,\n                    stderr=subprocess.DEVNULL,\n                    creationflags=flags,\n                    env=child_env,\n                )\n'''
if spawn_anchor in bridge:
    bridge = bridge.replace(spawn_anchor, spawn_fixed, 1)
elif 'PYINSTALLER_RESET_ENVIRONMENT' not in bridge:
    raise SystemExit("v0.11.7.49 memory child reset anchor missing")

# Preserve the proven Bridge protocol identity; expose bundle identity separately.
status_anchor = '"local_control_protocol": "vex-local-v1",'
if status_anchor in bridge and '"agent_runtime_bundle": "0.11.7.49"' not in bridge:
    bridge = bridge.replace(
        status_anchor,
        status_anchor + '\n                "agent_runtime_bundle": "0.11.7.49",',
        1,
    )

required_bridge_markers = [
    "MEMORY_WORKER_PORT = 8786",
    "MEMORY_WORKER_BASE",
    "VexMemoryWorkerRuntime",
    'parsed.path == "/memory/status"',
    'parsed.path == "/memory/sync"',
    "for _ in range(80)",
    'PYINSTALLER_RESET_ENVIRONMENT',
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

print("Applied v0.11.7.49 Agent Runtime foundation: dedicated memory runtime, collision fix, cold-start grace, isolated learning capability graph")
