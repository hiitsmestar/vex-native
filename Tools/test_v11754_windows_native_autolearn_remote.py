#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "Bridge" / "vex_bridge.py"
REMOTE = ROOT / "Tools" / "VexRemoteSupport.py"
INSTALLER = ROOT / "Tools" / "VexAgentRuntimeInstall.py"

bridge = BRIDGE.read_text(encoding="utf-8")
remote = REMOTE.read_text(encoding="utf-8")
installer = INSTALLER.read_text(encoding="utf-8")
for path, source in [(BRIDGE, bridge), (REMOTE, remote), (INSTALLER, installer)]:
    compile(source, str(path), "exec")

checks = {
    "proven bridge protocol": '"version": "0.11.7.39"' in bridge,
    "bundle version": '"agent_runtime_bundle": "0.11.7.54"' in bridge,
    "proven .53 autonomous engine": '"version": "0.11.7.53"' in bridge and 'name="VexAutonomousLearningSupervisor"' in bridge,
    "autolearn status route": 'parsed.path == "/autolearn/status"' in bridge,
    "autolearn queue route": 'parsed.path == "/autolearn/queue"' in bridge,
    "autolearn run route": 'parsed.path == "/autolearn/run"' in bridge,
    "native capability function": "def _windows_native_capabilities(" in bridge,
    "native window inventory": "def _windows_native_visible_windows(" in bridge,
    "native capability route": 'parsed.path == "/windows/capabilities"' in bridge,
    "local raw window route": 'parsed.path == "/windows/windows"' in bridge,
    "UI Automation detection": 'UIAutomationCore.dll' in bridge,
    "MSAA detection": 'oleacc.dll' in bridge,
    "Shell COM detection": 'ole32.dll' in bridge,
    "Windows Search detection": '"WSearch"' in bridge,
    "SAPI detection": "sapisvr.exe" in bridge,
    "Remote Support .54": 'VERSION = "0.11.7.54"' in remote,
    "sanitized autolearn helper": "def autolearn_public(" in remote,
    "sanitized Windows helper": "def windows_native_public(" in remote,
    "remote autolearn status": 'action == "autolearn_status"' in remote,
    "remote autolearn queue": 'action == "autolearn_queue"' in remote,
    "remote autolearn run": 'action == "autolearn_run"' in remote,
    "remote Windows capabilities": 'action == "windows_capabilities"' in remote,
    "installer bundle .54": 'BUNDLE_VERSION = "0.11.7.54"' in installer,
    "installer Remote Support .54": 'REMOTE_VERSION = "0.11.7.54"' in installer,
    "correct iPhone field text": "Keep VexNative v0.11.7.49 on the iPhone" in installer,
    "memory correction preserved": '"explicit-personal-memory-correction-v11752"' in bridge,
    "memory write preserved": '"explicit-personal-memory-write-v11751"' in bridge,
}

missing = [name for name, ok in checks.items() if not ok]
for name, ok in checks.items():
    print(("PASS " if ok else "FAIL ") + name)
if missing:
    raise SystemExit("v0.11.7.54 missing regressions: " + ", ".join(missing))

# The public relay must never fetch raw local window titles or emit raw proposal,
# evidence, path, token, IP, or personal-memory structures.
for forbidden in [
    'bridge_get("/windows/windows"',
    '"recent_proposals":',
    '"source_url":',
    '"artifact_path":',
    '"window_title":',
]:
    if forbidden in remote:
        raise SystemExit(f"public relay privacy regression: {forbidden}")
print("PASS public relay raw-data boundary")

# Import the generated Remote Support module and prove sanitization behavior with
# deliberately over-rich fake local responses.
spec = importlib.util.spec_from_file_location("vex_remote_support_v11754", REMOTE)
if spec is None or spec.loader is None:
    raise SystemExit("could not import generated Remote Support")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

calls: list[tuple[str, str, object]] = []


def fake_get(path: str, timeout: int = 8):
    calls.append(("GET", path, None))
    if path == "/autolearn/status":
        return {
            "ok": True,
            "version": "0.11.7.53",
            "mode": "autonomous-source-grounded-project-learning",
            "worker_started": True,
            "worker_alive": True,
            "tasks": 9,
            "pending": 2,
            "proposals": 4,
            "ready_for_review": 2,
            "approval_required": 1,
            "recent_proposals": [{"goal": "PRIVATE GOAL", "artifact_path": r"C:\\Users\\Private\\proposal.json"}],
            "source_url": "https://example.invalid/private-source",
            "token": "DO-NOT-LEAK",
        }
    if path == "/windows/capabilities":
        return {
            "ok": True,
            "version": "0.11.7.54",
            "windows": True,
            "ui_automation_api": True,
            "msaa_accessibility_api": True,
            "shell_com_api": True,
            "windows_search_service": True,
            "windows_search_running": True,
            "sapi_speech": True,
            "powershell": True,
            "native_window_inventory": True,
            "visible_window_count": 7,
            "windows": [{"title": "PRIVATE WINDOW TITLE"}],
            "private_ip": "192.168.1.9",
        }
    return {"ok": True}


def fake_post(path: str, payload=None, timeout: int = 180):
    calls.append(("POST", path, payload))
    if path == "/autolearn/run":
        return {
            "ok": True,
            "task_id": 4,
            "proposal_id": 8,
            "status": "ready-for-review",
            "risk": "low",
            "confidence": 0.81,
            "detail": "PRIVATE RAW DETAIL",
            "artifact_path": r"C:\\Users\\Private\\proposal.json",
            "http_status": 200,
        }
    if path == "/autolearn/queue":
        return {
            "ok": True,
            "task_id": 5,
            "public_topic": "generic public technical topic",
            "goal": "PRIVATE RAW GOAL",
            "http_status": 200,
        }
    return {"ok": True, "http_status": 200}


module.bridge_get = fake_get
module.bridge_post = fake_post

status = module.execute_command({"action": "autolearn_status"}, allow_maintenance=False)
status_text = repr(status)
for forbidden in ["PRIVATE GOAL", "proposal.json", "private-source", "DO-NOT-LEAK", "recent_proposals", "source_url", "artifact_path"]:
    if forbidden in status_text:
        raise SystemExit(f"autolearn status leaked raw field {forbidden}: {status}")
if status.get("autolearn", {}).get("proposals") != 4:
    raise SystemExit(f"autolearn count missing: {status}")
print("PASS sanitized autolearn status")

native = module.execute_command({"action": "windows_capabilities"}, allow_maintenance=False)
native_text = repr(native)
for forbidden in ["PRIVATE WINDOW TITLE", "192.168.1.9", "windows': [", '"windows": [']:
    if forbidden in native_text:
        raise SystemExit(f"Windows capability relay leaked raw local data {forbidden}: {native}")
if native.get("windows_native", {}).get("visible_window_count") != 7:
    raise SystemExit(f"Windows capability count missing: {native}")
print("PASS sanitized Windows-native telemetry")

queued = module.execute_command(
    {"action": "autolearn_queue", "topic": "Windows UI Automation architecture and accessibility API testing"},
    allow_maintenance=False,
)
if queued.get("ok") is not True or queued.get("task_id") != 5 or queued.get("queued_for_research") is not True:
    raise SystemExit(f"autolearn queue failed: {queued}")
if not any(method == "POST" and path == "/autolearn/queue" for method, path, _ in calls):
    raise SystemExit("autolearn queue did not reach the authenticated Bridge route")
print("PASS sanitized remote autolearn queue")

run = module.execute_command({"action": "autolearn_run"}, allow_maintenance=False)
run_text = repr(run)
if run.get("ok") is not True or run.get("proposal_id") != 8:
    raise SystemExit(f"autolearn run failed: {run}")
for forbidden in ["PRIVATE RAW DETAIL", "proposal.json", "artifact_path"]:
    if forbidden in run_text:
        raise SystemExit(f"autolearn run leaked {forbidden}: {run}")
print("PASS sanitized remote autolearn run")

rejected = module.execute_command({"action": "autolearn_queue", "topic": "my private relationship memories"}, allow_maintenance=False)
if rejected.get("ok") is not False:
    raise SystemExit(f"nontechnical/private autolearn topic should be rejected: {rejected}")
print("PASS generic-technical queue gate")

print("v0.11.7.54 Windows-native + autolearn Remote Support regressions verified")
