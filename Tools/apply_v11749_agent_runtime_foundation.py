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

# ---------------------------------------------------------------------------
# Repair a latent v0.11.7.34 bootstrap bug before adding Agent Runtime pieces.
# That patch inserted start_initial_reindex(), then used a broad substring replace
# for `state.index.rebuild()`. Because the same text appears inside the newly-added
# helper, some generated chains rewrote the helper into recursive thread spawning
# while leaving the real foreground rebuild in main(). Correct both explicitly.
# ---------------------------------------------------------------------------
bad_index_helper = '''def start_initial_reindex(state: BridgeState) -> None:\n    def work() -> None:\n        state.indexing = True\n        state.index_error = None\n        try:\n            start_initial_reindex(state)\n        except Exception as exc:\n            state.index_error = exc.__class__.__name__\n        finally:\n            state.indexing = False\n    threading.Thread(target=work, daemon=True, name="VexBridgeInitialIndex").start()\n'''
good_index_helper = '''def start_initial_reindex(state: BridgeState) -> None:\n    def work() -> None:\n        state.indexing = True\n        state.index_error = None\n        try:\n            state.index.rebuild()\n        except Exception as exc:\n            state.index_error = exc.__class__.__name__\n        finally:\n            state.indexing = False\n    threading.Thread(target=work, daemon=True, name="VexBridgeInitialIndex").start()\n'''
if bad_index_helper in bridge:
    bridge = bridge.replace(bad_index_helper, good_index_helper, 1)
elif good_index_helper not in bridge:
    raise SystemExit("v0.11.7.49 could not verify initial-index helper")

foreground_index = '''    print("\\nVex Bridge v0.7 — indexing selected folders…")\n    state.index.rebuild()\n    start_background_reindex(state)\n'''
nonblocking_index = '''    print("\\nVex Bridge v0.7 — indexing selected folders…")\n    start_initial_reindex(state)\n    start_background_reindex(state)\n'''
if foreground_index in bridge:
    bridge = bridge.replace(foreground_index, nonblocking_index, 1)
elif nonblocking_index not in bridge:
    raise SystemExit("v0.11.7.49 could not verify nonblocking initial-index call")

# Keep persistent memory clear of the Bridge local-control ring (8766-8797 in
# current runtime builds). Use a separate local-only port beyond that ring.
old_port = "MEMORY_WORKER_PORT = 8766"
new_port = "MEMORY_WORKER_PORT = 8806"
if old_port in bridge:
    bridge = bridge.replace(old_port, new_port, 1)
elif "MEMORY_WORKER_PORT = 8786" in bridge:
    bridge = bridge.replace("MEMORY_WORKER_PORT = 8786", new_port, 1)
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

# The dedicated LocalControlHandler was intentionally tiny and delegated every
# non-status request into the large LAN Handler. Keep that compatibility fallback,
# but route the two Agent Runtime health paths directly after authenticating them.
# This avoids LAN/TLS/request-hook behavior affecting local service supervision.
local_old = '''    def do_GET(self) -> None:\n        parsed = urllib.parse.urlparse(self.path)\n        if parsed.path not in ("/", "/status"):\n            return super().do_GET()\n        params = urllib.parse.parse_qs(parsed.query)\n        supplied = (params.get("token") or [""])[0]\n        state = STATE\n        if state is None or not secrets.compare_digest(supplied, str(state.config.get("token") or "")):\n'''
local_new = '''    def do_GET(self) -> None:\n        parsed = urllib.parse.urlparse(self.path)\n        params = urllib.parse.parse_qs(parsed.query)\n        supplied = (params.get("token") or [""])[0]\n        state = STATE\n        if state is None or not secrets.compare_digest(supplied, str(state.config.get("token") or "")):\n'''
if local_old in bridge:
    bridge = bridge.replace(local_old, local_new, 1)
elif local_new not in bridge:
    raise SystemExit("v0.11.7.49 LocalControlHandler auth anchor missing")

local_status_anchor = '''            self.wfile.write(body)\n            return\n        payload = {\n            "name": "Vex Bridge",\n'''
local_agent_routes = '''            self.wfile.write(body)\n            return\n        if parsed.path == "/memory/status":\n            health = _memory_worker_health(start_if_needed=True)\n            self._json(200 if health.get("ok") else 503, health)\n            return\n        if parsed.path == "/adaptive/status":\n            adaptive = _adaptive_status()\n            self._json(200 if adaptive.get("ok") else 503, adaptive)\n            return\n        if parsed.path not in ("/", "/status"):\n            return super().do_GET()\n        payload = {\n            "name": "Vex Bridge",\n'''
if local_status_anchor in bridge:
    bridge = bridge.replace(local_status_anchor, local_agent_routes, 1)
elif 'if parsed.path == "/memory/status":\n            health = _memory_worker_health(start_if_needed=True)' not in bridge:
    raise SystemExit("v0.11.7.49 direct local Agent Runtime route anchor missing")

# Preserve the proven Bridge protocol identity; expose bundle identity separately.
status_anchor = '"local_control_protocol": "vex-local-v1",'
if status_anchor in bridge and '"agent_runtime_bundle": "0.11.7.49"' not in bridge:
    bridge = bridge.replace(
        status_anchor,
        status_anchor + '\n                "agent_runtime_bundle": "0.11.7.49",',
        1,
    )

required_bridge_markers = [
    "MEMORY_WORKER_PORT = 8806",
    "MEMORY_WORKER_BASE",
    "VexMemoryWorkerRuntime",
    'parsed.path == "/memory/status"',
    'parsed.path == "/memory/sync"',
    'if parsed.path == "/adaptive/status"',
    "for _ in range(80)",
    'PYINSTALLER_RESET_ENVIRONMENT',
    'state.index.rebuild()',
    'start_initial_reindex(state)',
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

# The helper itself must no longer recurse.
helper_start = bridge.find("def start_initial_reindex(state: BridgeState) -> None:")
helper_end = bridge.find("\ndef start_background_reindex", helper_start)
helper_text = bridge[helper_start:helper_end] if helper_start >= 0 and helper_end > helper_start else ""
if "start_initial_reindex(state)" in helper_text:
    raise SystemExit("v0.11.7.49 recursive initial-index helper remains")
if "state.index.rebuild()" not in helper_text:
    raise SystemExit("v0.11.7.49 initial-index helper no longer rebuilds index")

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

print("Applied v0.11.7.49 Agent Runtime foundation: bootstrap repaired, direct local agent routes, dedicated memory runtime, collision fix, isolated learning graph")
