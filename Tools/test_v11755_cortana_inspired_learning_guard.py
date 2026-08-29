#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import types
from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
REMOTE = Path("Tools/VexRemoteSupport.py")
INSTALLER = Path("Tools/VexAgentRuntimeInstall.py")

bridge = BRIDGE.read_text(encoding="utf-8")
remote = REMOTE.read_text(encoding="utf-8")
installer = INSTALLER.read_text(encoding="utf-8")
compile(bridge, str(BRIDGE), "exec")
compile(remote, str(REMOTE), "exec")
compile(installer, str(INSTALLER), "exec")

required_bridge = [
    '"agent_runtime_bundle": "0.11.7.55"',
    "PROJECT_PROPOSAL_PER_TASK_CAP = 6",
    "PROJECT_SAME_EVIDENCE_COOLDOWN_SECONDS = 6 * 3600",
    "PROJECT_TERMINAL_STATUSES",
    '"approval-required", "ready-for-review", "staged", "done", "blocked"',
    "def _project_v55_compact_duplicate_proposals(",
    "status='superseded-duplicate'",
    "def _project_v55_evidence_fingerprint_from_receipts(",
    "def _project_v55_gate_proposal(",
    "evidence has not materially changed since the existing proposal",
    "per-task proposal cap reached",
    "def _windows_native_session_state(",
    "ProcessIdToSessionId",
    "WTSGetActiveConsoleSessionId",
    "OpenInputDesktop",
    "def _windows_native_powershell_windows(",
    "MainWindowHandle",
    "powershell-mainwindow",
    '"version": "0.11.7.55", "count": len(rows), "windows": rows',
]
for marker in required_bridge:
    if marker not in bridge:
        raise SystemExit(f"v0.11.7.55 Bridge regression marker missing: {marker}")

for marker in [
    'VERSION = "0.11.7.55"',
    "proposal_dedupe",
    "evidence_change_required",
    "suppressed_duplicates",
    "interactive_session_match",
    "input_desktop_accessible",
    "window_inventory_method",
    "supported_windows_primitives",
    "cortana_private_api_dependency",
]:
    if marker not in remote:
        raise SystemExit(f"v0.11.7.55 Remote marker missing: {marker}")

for forbidden in [
    'bridge_get("/windows/windows"',
    '"recent_proposals":',
    '"source_url":',
    '"artifact_path":',
    '"window_title":',
    '"process_session_id": integer',
    '"active_console_session_id": integer',
]:
    if forbidden in remote:
        raise SystemExit(f"v0.11.7.55 Remote privacy regression: {forbidden}")

for marker in [
    'BUNDLE_VERSION = "0.11.7.55"',
    'REMOTE_VERSION = "0.11.7.55"',
    "Vex Agent Runtime v0.11.7.55 installed.",
    "Keep VexNative v0.11.7.49 on the iPhone",
]:
    if marker not in installer:
        raise SystemExit(f"v0.11.7.55 installer marker missing: {marker}")

for forbidden in ["Cortana.exe", "Microsoft.Windows.Cortana", "api.openai.com", "OPENAI_API_KEY"]:
    layer_start = bridge.find("# v0.11.7.55 Cortana-inspired Windows access + autonomous learning guard")
    layer_end = bridge.find("def _vex_background_services() -> None:", layer_start)
    if forbidden in bridge[layer_start:layer_end]:
        raise SystemExit(f"v0.11.7.55 unsupported dependency regression: {forbidden}")


def latest_function_source(text: str, name: str) -> str:
    tree = ast.parse(text)
    nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
    if not nodes:
        raise SystemExit(f"function not found: {name}")
    node = nodes[-1]
    lines = text.splitlines()
    return "\n".join(lines[node.lineno - 1: node.end_lineno]) + "\n"


# Evidence dedupe must ignore refresh timestamps. Same sources = same evidence;
# adding a genuinely new source must change the fingerprint.
fingerprint_src = latest_function_source(bridge, "_project_v55_evidence_fingerprint_from_receipts")
ns = {"json": json, "re": re}
exec(compile(fingerprint_src, "<v11755-fingerprint>", "exec"), ns)
fingerprint = ns["_project_v55_evidence_fingerprint_from_receipts"]
a = [
    {"url": "https://learn.microsoft.com/a#section", "title": "UI Automation", "retrieved_at": 1},
    {"url": "https://learn.microsoft.com/b", "title": "Sessions", "retrieved_at": 2},
]
b = [
    {"url": "https://learn.microsoft.com/a#other", "title": "UI Automation", "retrieved_at": 9999},
    {"url": "https://learn.microsoft.com/b", "title": "Sessions", "retrieved_at": 8888},
]
c = b + [{"url": "https://learn.microsoft.com/c", "title": "Windows Search", "retrieved_at": 7777}]
fa, fb, fc = fingerprint(a), fingerprint(b), fingerprint(c)
if not fa or fa != fb:
    raise SystemExit("v0.11.7.55 evidence fingerprint changes on timestamp/fragment-only refresh")
if fc == fa:
    raise SystemExit("v0.11.7.55 evidence fingerprint did not change for a new source")

# Recreate the field fallback path without needing an interactive GitHub desktop:
# force powershell discovery and return one synthetic MainWindow record.
powershell_src = latest_function_source(bridge, "_windows_native_powershell_windows")
win_ns = {"os": types.SimpleNamespace(name="nt"), "json": json}
exec(compile(powershell_src, "<v11755-window-fallback>", "exec"), win_ns)
window_fallback = win_ns["_windows_native_powershell_windows"]
orig_which = shutil.which
orig_run = subprocess.run
try:
    shutil.which = lambda name: r"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" if "powershell" in name.lower() else None
    subprocess.run = lambda *args, **kwargs: types.SimpleNamespace(
        returncode=0,
        stdout=json.dumps({"Id": 4242, "MainWindowHandle": 31337, "ProcessName": "Notepad", "MainWindowTitle": "Synthetic field window"}),
    )
    rows = window_fallback(limit=8)
finally:
    shutil.which = orig_which
    subprocess.run = orig_run

if len(rows) != 1 or rows[0].get("hwnd") != 31337 or rows[0].get("pid") != 4242:
    raise SystemExit(f"v0.11.7.55 PowerShell window fallback failed: {rows}")
if rows[0].get("title") != "Synthetic field window":
    raise SystemExit(f"v0.11.7.55 local window title parsing failed: {rows}")

# The fixed queue function must short-circuit an existing task instead of calling
# the legacy base path that reset approval-required -> research overnight.
queue_src = latest_function_source(bridge, "_project_queue_task")
if "deduplicated" not in queue_src or "terminal_preserved" not in queue_src:
    raise SystemExit("v0.11.7.55 queue dedupe short-circuit missing")
if queue_src.find("return {\n                \"ok\": True") > queue_src.find("return _v11755_project_queue_task_base(goal, category, detail, source_gap_id)"):
    raise SystemExit("v0.11.7.55 queue short-circuit ordering is wrong")

print("v0.11.7.55 field regressions passed: proposal anti-spam + Windows interactive fallback + privacy")
