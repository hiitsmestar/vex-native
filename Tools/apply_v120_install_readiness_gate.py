#!/usr/bin/env python3
from __future__ import annotations

import runpy
from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
INSTALLER = Path("Tools/VexAgentRuntimeInstall.py")

bridge = BRIDGE.read_text(encoding="utf-8")
installer = INSTALLER.read_text(encoding="utf-8")
if (
    '"agent_runtime_bundle": "0.12.0"' not in bridge
    or 'BUNDLE_VERSION = "0.12.0"' not in installer
    or 'def _v120_agent_owns_turn(message: str) -> bool:' not in bridge
):
    runpy.run_path("Tools/apply_v120_conversation_route_entry.py", run_name="__main__")

installer = INSTALLER.read_text(encoding="utf-8")
if "def stop_processes_using_install_path(" not in installer:
    runpy.run_path("Tools/apply_v120_installer_lock_fix.py", run_name="__main__")

bridge = BRIDGE.read_text(encoding="utf-8")
if (
    "_OLLAMA_MODEL_CACHE_TTL_SECONDS = 120.0" not in bridge
    or "One bounded second-chance selection" not in bridge
):
    runpy.run_path("Tools/apply_v120_cognition_model_resilience.py", run_name="__main__")

installer = INSTALLER.read_text(encoding="utf-8")
bridge = BRIDGE.read_text(encoding="utf-8")
for marker in [
    'BUNDLE_VERSION = "0.12.0"',
    "def stop_processes_using_install_path(",
]:
    if marker not in installer:
        raise SystemExit(f"v0.12 readiness gate missing installer prerequisite: {marker}")
for marker in [
    '"agent_runtime_bundle": "0.12.0"',
    'def _v120_agent_owns_turn(message: str) -> bool:',
    "_OLLAMA_MODEL_CACHE_TTL_SECONDS = 120.0",
    "One bounded second-chance selection",
]:
    if marker not in bridge:
        raise SystemExit(f"v0.12 readiness gate missing Bridge prerequisite: {marker}")

anchor = "\n\ndef wait_direct_memory(seconds: int = 30) -> dict:\n"
helper = r'''

def recover_bridge_for_cognition(home: Path) -> None:
    """Bounded recovery for a Bridge that passed startup and then disappeared during cognition warmup."""
    script = "Stop-Process -Name 'VexBridge' -Force -ErrorAction SilentlyContinue"
    try:
        run_powershell(script, timeout=10)
    except Exception:
        pass
    time.sleep(0.8)
    launch(home / "VexBridge.exe", home)
    wait_bridge(seconds=35)


def wait_cognition(home: Path, seconds: int = 150) -> dict:
    """Require a live deployed PC model, recovering a dropped Bridge instead of retrying a dead endpoint."""
    deadline = time.time() + seconds
    last = "no response"
    failures = 0
    recoveries = 0
    while time.time() < deadline:
        try:
            status = local_bridge_get("/status", timeout=3.0)
            bundle = str(status.get("agent_runtime_bundle") or "")
            if bundle != BUNDLE_VERSION:
                last = f"runtime bundle is {bundle or 'missing'}, expected {BUNDLE_VERSION}"
                failures += 1
            else:
                value = local_bridge_get("/llm/status", timeout=5.0)
                model = str(value.get("model") or "").strip()
                count = int(value.get("available_model_count") or 0)
                if bool(value.get("ok")) and model and count > 0:
                    return value
                last = str(value.get("error") or f"model={model or 'none'} count={count}")
                failures += 1
        except Exception as exc:
            last = f"{exc.__class__.__name__}: {exc}"
            failures += 1

        if failures >= 4 and recoveries < 3 and time.time() < deadline:
            try:
                recover_bridge_for_cognition(home)
                recoveries += 1
                failures = 0
                continue
            except Exception as exc:
                last = f"Bridge cognition recovery failed: {exc}"
                recoveries += 1
                failures = 0
        time.sleep(1.0)
    raise RuntimeError(f"PC cognition did not become ready after v0.12 install: {last}")
'''
if "def wait_cognition(" not in installer:
    if anchor not in installer:
        raise SystemExit("v0.12 readiness gate could not find memory-wait anchor")
    installer = installer.replace(anchor, helper + anchor, 1)

# Keep Remote Support alive before cognition verification so a failed warmup still
# leaves the machine diagnosable instead of cutting off the only remote telemetry.
remote_launch = '        launch(home / "VexRemoteSupportRuntime" / "VexRemoteSupport.exe", home / "VexRemoteSupportRuntime")\n'
bridge_launch = '        launch(home / "VexBridge.exe", home)\n'
if remote_launch in installer and installer.find(remote_launch) > installer.find("cognition = wait_cognition"):
    installer = installer.replace(remote_launch, "", 1)
    if bridge_launch not in installer:
        raise SystemExit("v0.12 readiness gate could not find Bridge launch anchor")
    installer = installer.replace(bridge_launch, remote_launch + bridge_launch, 1)

main_anchor = "        launch(home / \"VexBridge.exe\", home)\n        wait_bridge()\n        memory = wait_memory()\n"
main_replacement = "        launch(home / \"VexBridge.exe\", home)\n        wait_bridge()\n        cognition = wait_cognition(home)\n        memory = wait_memory()\n"
if main_anchor in installer:
    installer = installer.replace(main_anchor, main_replacement, 1)
elif "        cognition = wait_cognition(home)\n" not in installer:
    raise SystemExit("v0.12 readiness gate could not attach cognition check")

old = '            "Vex Agent Runtime v0.12.0 installed.\\n\\n"\n'
new = '            f"Vex Agent Runtime {BUNDLE_VERSION} installed and verified.\\n\\n"\n'
if old in installer:
    installer = installer.replace(old, new, 1)
elif "installed and verified" not in installer:
    import re
    installer, n = re.subn(r'            "Vex Agent Runtime v[^"\\n]+ installed\\.\\n\\n"\\n', new, installer, count=1)
    if n == 0:
        raise SystemExit("v0.12 readiness gate could not normalize success dialog")

model_line = '            f"Bridge {BRIDGE_VERSION}: ready\\n"\n'
model_replacement = model_line + '            f"PC cognition: ready ({cognition.get(\'model\') or \'local model\'})\\n"\n'
if "PC cognition: ready" not in installer:
    if model_line not in installer:
        raise SystemExit("v0.12 readiness gate could not find success-dialog Bridge line")
    installer = installer.replace(model_line, model_replacement, 1)

INSTALLER.write_text(installer, encoding="utf-8")
compile(installer, str(INSTALLER), "exec")

for marker in [
    "def recover_bridge_for_cognition(home: Path)",
    "def wait_cognition(home: Path, seconds: int = 150)",
    'status.get("agent_runtime_bundle")',
    'local_bridge_get("/llm/status"',
    "cognition = wait_cognition(home)",
    "recover_bridge_for_cognition(home)",
    "installed and verified",
    "PC cognition: ready",
    "def stop_processes_using_install_path(",
]:
    if marker not in installer:
        raise SystemExit(f"v0.12 readiness gate missing marker: {marker}")

if installer.find(remote_launch) > installer.find("cognition = wait_cognition(home)"):
    raise SystemExit("v0.12 readiness gate failed to move Remote Support before cognition verification")

print("Applied v0.12 cognition startup recovery + pre-gate Remote Support diagnostics")
