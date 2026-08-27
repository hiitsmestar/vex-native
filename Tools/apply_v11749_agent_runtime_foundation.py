#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
REMOTE = Path("Tools/VexRemoteSupport.py")

bridge = BRIDGE.read_text(encoding="utf-8")
remote = REMOTE.read_text(encoding="utf-8")

if '"version": "0.11.7.39"' not in bridge:
    raise SystemExit("v0.11.7.49 expected Bridge v0.11.7.39 source")

bad_index_helper = '''def start_initial_reindex(state: BridgeState) -> None:\n    def work() -> None:\n        state.indexing = True\n        state.index_error = None\n        try:\n            start_initial_reindex(state)\n        except Exception as exc:\n            state.index_error = exc.__class__.__name__\n        finally:\n            state.indexing = False\n    threading.Thread(target=work, daemon=True, name="VexBridgeInitialIndex").start()\n'''
good_index_helper = '''def start_initial_reindex(state: BridgeState) -> None:\n    def work() -> None:\n        state.indexing = True\n        state.index_error = None\n        try:\n            state.index.rebuild()\n        except Exception as exc:\n            state.index_error = exc.__class__.__name__\n        finally:\n            state.indexing = False\n    threading.Thread(target=work, daemon=True, name="VexBridgeInitialIndex").start()\n'''
if bad_index_helper in bridge:
    bridge = bridge.replace(bad_index_helper, good_index_helper, 1)
elif good_index_helper not in bridge:
    raise SystemExit("v0.11.7.49 could not verify initial-index helper")

main_start = bridge.find("def main()")
if main_start < 0:
    raise SystemExit("v0.11.7.49 Bridge main() missing")
main_text = bridge[main_start:]
if "state.index.rebuild()" in main_text:
    main_text = main_text.replace("state.index.rebuild()", "start_initial_reindex(state)", 1)
    bridge = bridge[:main_start] + main_text
elif "start_initial_reindex(state)" not in main_text:
    raise SystemExit("v0.11.7.49 could not verify nonblocking initial-index call in main")

if "MEMORY_WORKER_PORT = 8766" in bridge:
    bridge = bridge.replace("MEMORY_WORKER_PORT = 8766", "MEMORY_WORKER_PORT = 8806", 1)
elif "MEMORY_WORKER_PORT = 8786" in bridge:
    bridge = bridge.replace("MEMORY_WORKER_PORT = 8786", "MEMORY_WORKER_PORT = 8806", 1)
elif "MEMORY_WORKER_PORT = 8806" not in bridge:
    raise SystemExit("v0.11.7.49 persistent-memory port marker missing")

old_grace = "        for _ in range(25):\n            time.sleep(0.12)\n"
new_grace = "        for attempt in range(80):\n            time.sleep(0.15)\n"
if old_grace in bridge:
    bridge = bridge.replace(old_grace, new_grace, 1)
elif new_grace not in bridge and "for _ in range(80):" in bridge:
    bridge = bridge.replace("        for _ in range(80):\n            time.sleep(0.15)\n", new_grace, 1)
elif new_grace not in bridge:
    raise SystemExit("v0.11.7.49 memory startup grace marker missing")

old_worker_exe = '''def _memory_worker_exe() -> Path:\n    # In the packaged build VexMemoryWorker.exe sits beside VexBridge.exe.\n    return Path(sys.executable).resolve().with_name("VexMemoryWorker.exe")\n'''
new_worker_exe = '''def _memory_worker_exe() -> Path:\n    base = Path(sys.executable).resolve().parent\n    packaged = base / "VexMemoryWorkerRuntime" / "VexMemoryWorker.exe"\n    if packaged.exists():\n        return packaged\n    return base / "VexMemoryWorker.exe"\n'''
if old_worker_exe in bridge:
    bridge = bridge.replace(old_worker_exe, new_worker_exe, 1)
elif 'VexMemoryWorkerRuntime' not in bridge:
    raise SystemExit("v0.11.7.49 memory runtime locator anchor missing")

spawn_anchor = '''                subprocess.Popen(\n                    [str(exe), "--serve", "--port", str(MEMORY_WORKER_PORT)],\n                    cwd=str(exe.parent),\n                    stdout=subprocess.DEVNULL,\n                    stderr=subprocess.DEVNULL,\n                    creationflags=flags,\n                )\n'''
spawn_fixed = '''                child_env = os.environ.copy()\n                child_env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"\n                subprocess.Popen(\n                    [str(exe), "--serve", "--port", str(MEMORY_WORKER_PORT)],\n                    cwd=str(exe.parent),\n                    stdout=subprocess.DEVNULL,\n                    stderr=subprocess.DEVNULL,\n                    creationflags=flags,\n                    env=child_env,\n                    close_fds=True,\n                )\n'''
if spawn_anchor in bridge:
    bridge = bridge.replace(spawn_anchor, spawn_fixed, 1)
elif 'PYINSTALLER_RESET_ENVIRONMENT' not in bridge:
    raise SystemExit("v0.11.7.49 memory child reset anchor missing")

# If a frozen Bridge child launch returns but the worker never binds, retry once
# through Windows Start-Process. This is intentionally bounded and only occurs in
# memory recovery; normal conversation never shells out on every turn.
retry_anchor = '''        for attempt in range(80):\n            time.sleep(0.15)\n            try:\n'''
retry_block = '''        for attempt in range(80):\n            time.sleep(0.15)\n            if attempt == 20:\n                try:\n                    ps_exe = str(exe).replace("'", "''")\n                    ps_cwd = str(exe.parent).replace("'", "''")\n                    ps = (\n                        "$ErrorActionPreference='Stop'; "\n                        f"Start-Process -FilePath '{ps_exe}' -WorkingDirectory '{ps_cwd}' "\n                        f"-ArgumentList '--serve','--port','{MEMORY_WORKER_PORT}' -WindowStyle Hidden"\n                    )\n                    subprocess.Popen(\n                        ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", ps],\n                        stdout=subprocess.DEVNULL,\n                        stderr=subprocess.DEVNULL,\n                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),\n                    )\n                except Exception:\n                    pass\n            try:\n'''
if retry_anchor in bridge:
    bridge = bridge.replace(retry_anchor, retry_block, 1)
elif "Start-Process -FilePath" not in bridge:
    raise SystemExit("v0.11.7.49 memory recovery fallback anchor missing")

bg_marker = '''def _vex_background_services() -> None:\n'''
if bg_marker not in bridge:
    raise SystemExit("v0.11.7.49 background service anchor missing")
if 'name="VexPersistentMemoryWarmup"' not in bridge:
    bg_insert = '''def _vex_background_services() -> None:\n    threading.Thread(\n        target=lambda: _memory_worker_health(start_if_needed=True),\n        daemon=True,\n        name="VexPersistentMemoryWarmup",\n    ).start()\n'''
    bridge = bridge.replace(bg_marker, bg_insert, 1)

local_old = '''    def do_GET(self) -> None:\n        parsed = urllib.parse.urlparse(self.path)\n        if parsed.path not in ("/", "/status"):\n            return super().do_GET()\n        params = urllib.parse.parse_qs(parsed.query)\n        supplied = (params.get("token") or [""])[0]\n        state = STATE\n        if state is None or not secrets.compare_digest(supplied, str(state.config.get("token") or "")):\n'''
local_new = '''    def do_GET(self) -> None:\n        parsed = urllib.parse.urlparse(self.path)\n        params = urllib.parse.parse_qs(parsed.query)\n        supplied = (params.get("token") or [""])[0]\n        state = STATE\n        if state is None or not secrets.compare_digest(supplied, str(state.config.get("token") or "")):\n'''
if local_old in bridge:
    bridge = bridge.replace(local_old, local_new, 1)
elif local_new not in bridge:
    raise SystemExit("v0.11.7.49 LocalControlHandler auth anchor missing")

local_status_anchor = '''            self.wfile.write(body)\n            return\n        payload = {\n            "name": "Vex Bridge",\n'''
local_agent_routes = '''            self.wfile.write(body)\n            return\n        if parsed.path == "/memory/status":\n            health = _memory_worker_health(start_if_needed=False)\n            if not health.get("ok"):\n                threading.Thread(\n                    target=lambda: _memory_worker_health(start_if_needed=True),\n                    daemon=True,\n                    name="VexPersistentMemoryRecovery",\n                ).start()\n            self._json(200 if health.get("ok") else 503, health)\n            return\n        if parsed.path == "/adaptive/status":\n            adaptive = _adaptive_status()\n            self._json(200 if adaptive.get("ok") else 503, adaptive)\n            return\n        if parsed.path not in ("/", "/status"):\n            return super().do_GET()\n        payload = {\n            "name": "Vex Bridge",\n'''
if local_status_anchor in bridge:
    bridge = bridge.replace(local_status_anchor, local_agent_routes, 1)
elif 'name="VexPersistentMemoryRecovery"' not in bridge:
    raise SystemExit("v0.11.7.49 direct local Agent Runtime route anchor missing")

status_anchor = '"local_control_protocol": "vex-local-v1",'
if status_anchor in bridge and '"agent_runtime_bundle": "0.11.7.49"' not in bridge:
    bridge = bridge.replace(status_anchor, status_anchor + '\n                "agent_runtime_bundle": "0.11.7.49",', 1)

required_bridge_markers = [
    "MEMORY_WORKER_PORT = 8806",
    "MEMORY_WORKER_BASE",
    "VexMemoryWorkerRuntime",
    'parsed.path == "/memory/status"',
    'parsed.path == "/memory/sync"',
    'if parsed.path == "/adaptive/status"',
    "for attempt in range(80)",
    'PYINSTALLER_RESET_ENVIRONMENT',
    'Start-Process -FilePath',
    'name="VexPersistentMemoryWarmup"',
    'name="VexPersistentMemoryRecovery"',
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

helper_start = bridge.find("def start_initial_reindex(state: BridgeState) -> None:")
helper_end = bridge.find("\ndef start_background_reindex", helper_start)
helper_text = bridge[helper_start:helper_end] if helper_start >= 0 and helper_end > helper_start else ""
if "start_initial_reindex(state)" in helper_text:
    raise SystemExit("v0.11.7.49 recursive initial-index helper remains")
if "state.index.rebuild()" not in helper_text:
    raise SystemExit("v0.11.7.49 initial-index helper no longer rebuilds index")
main_start = bridge.find("def main()")
if "start_initial_reindex(state)" not in bridge[main_start:]:
    raise SystemExit("v0.11.7.49 main still blocks on initial indexing")

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
print("Applied v0.11.7.49 Agent Runtime foundation: hardened memory sidecar recovery, nonblocking bootstrap, direct health routes, isolated learning graph")
