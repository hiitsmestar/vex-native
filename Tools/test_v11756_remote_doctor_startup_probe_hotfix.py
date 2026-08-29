#!/usr/bin/env python3
from __future__ import annotations

import ast
import os
import tempfile
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

for marker in [
    '"agent_runtime_bundle": "0.11.7.56"',
    "PROJECT_PROPOSAL_PER_TASK_CAP = 6",
    "def _windows_native_powershell_windows(",
    "_v11756_project_supervisor_status_base",
    "_v11756_windows_native_capabilities_base",
]:
    if marker not in bridge:
        raise SystemExit(f"v0.11.7.56 Bridge regression marker missing: {marker}")

for marker in [
    'VERSION = "0.11.7.56"',
    'base.parent / "VexDoctor.exe"',
    "_v11756_collect_snapshot_base = collect_snapshot",
    'bridge_get("/windows/capabilities", timeout=12)',
]:
    if marker not in remote:
        raise SystemExit(f"v0.11.7.56 Remote regression marker missing: {marker}")

for marker in [
    'BUNDLE_VERSION = "0.11.7.56"',
    'REMOTE_VERSION = "0.11.7.56"',
    "Vex Agent Runtime v0.11.7.56 installed.",
]:
    if marker not in installer:
        raise SystemExit(f"v0.11.7.56 installer regression marker missing: {marker}")


def latest_function_source(text: str, name: str) -> str:
    tree = ast.parse(text)
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if not nodes:
        raise SystemExit(f"function not found: {name}")
    node = nodes[-1]
    lines = text.splitlines()
    return "\n".join(lines[node.lineno - 1:node.end_lineno]) + "\n"


# Reproduce the real installed layout seen in the field:
# <home>/VexDoctor.exe and <home>/VexRemoteSupportRuntime/VexRemoteSupport.exe.
with tempfile.TemporaryDirectory(prefix="Vex11756Doctor-") as td:
    home = Path(td) / "VexHome"
    remote_dir = home / "VexRemoteSupportRuntime"
    remote_dir.mkdir(parents=True)
    doctor = home / "VexDoctor.exe"
    doctor.write_bytes(b"field-doctor")
    frozen_exe = remote_dir / "VexRemoteSupport.exe"
    frozen_exe.write_bytes(b"remote")

    ns = {
        "Path": Path,
        "sys": types.SimpleNamespace(frozen=True, executable=str(frozen_exe)),
    }
    exec(compile(latest_function_source(remote, "doctor_path"), "<v11756-doctor-path>", "exec"), ns)
    found = ns["doctor_path"]()
    # Windows may spell the same Temp path using an 8.3 short-name component
    # (RUNNER~1 vs runneradmin). Compare file identity, not path-string spelling.
    if found is None or not found.exists() or not os.path.samefile(str(found), str(doctor)):
        raise SystemExit(f"v0.11.7.56 Doctor parent lookup failed: expected {doctor}, got {found}")


# Reproduce the startup race: inherited snapshot sees false once; two subsequent
# Bridge probes return false then true. The .56 wrapper must recover the snapshot.
base_calls = []
probe_calls = []

def fake_base(include_doctor=False, deep=False):
    base_calls.append((include_doctor, deep))
    return {"windows_native": {"ok": False, "version": None, "visible_window_count": 0}}


def fake_bridge_get(path, timeout=0):
    probe_calls.append((path, timeout))
    ok = len(probe_calls) >= 2
    return {
        "ok": ok,
        "version": "0.11.7.56" if ok else None,
        "visible_window_count": 9 if ok else 0,
        "interactive_session_match": ok,
        "input_desktop_accessible": ok,
        "window_inventory_method": "powershell-mainwindow" if ok else None,
    }


def fake_public(value):
    return dict(value)

snap_ns = {
    "_v11756_collect_snapshot_base": fake_base,
    "bridge_get": fake_bridge_get,
    "windows_native_public": fake_public,
    "time": types.SimpleNamespace(sleep=lambda _seconds: None),
}
exec(compile(latest_function_source(remote, "collect_snapshot"), "<v11756-snapshot>", "exec"), snap_ns)
snap = snap_ns["collect_snapshot"]()
native = snap.get("windows_native") or {}
if native.get("ok") is not True:
    raise SystemExit(f"v0.11.7.56 startup capability retry failed: {snap}")
if native.get("visible_window_count") != 9 or native.get("window_inventory_method") != "powershell-mainwindow":
    raise SystemExit(f"v0.11.7.56 startup capability recovery returned wrong telemetry: {native}")
if len(probe_calls) != 2:
    raise SystemExit(f"v0.11.7.56 startup retry count regression: {probe_calls}")

# Public relay must never fetch the local raw window-list route or expose titles.
for forbidden in [
    'bridge_get("/windows/windows"',
    '"window_title":',
    '"recent_proposals":',
    '"source_url":',
    '"artifact_path":',
]:
    if forbidden in remote:
        raise SystemExit(f"v0.11.7.56 privacy regression: {forbidden}")

print("v0.11.7.56 regressions passed: Doctor installed-layout lookup + startup capability retry + privacy")
