#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
REMOTE = Path("Tools/VexRemoteSupport.py")
INSTALLER = Path("Tools/VexAgentRuntimeInstall.py")

bridge = BRIDGE.read_text(encoding="utf-8")
remote = REMOTE.read_text(encoding="utf-8")
installer = INSTALLER.read_text(encoding="utf-8")

for label, text, marker in [
    ("Bridge bundle", bridge, '"agent_runtime_bundle": "0.11.7.55"'),
    ("Autolearn guard", bridge, "PROJECT_PROPOSAL_PER_TASK_CAP = 6"),
    ("Windows field recovery", bridge, "def _windows_native_powershell_windows("),
    ("Remote Support", remote, 'VERSION = "0.11.7.55"'),
    ("Installer", installer, 'BUNDLE_VERSION = "0.11.7.55"'),
]:
    if marker not in text:
        raise SystemExit(f"v0.11.7.56 expected {label} marker missing: {marker}")

# Keep the runtime bundle identity coherent while preserving the proven Bridge
# protocol/version identity used by the phone pairing and local control plane.
bridge = bridge.replace('"agent_runtime_bundle": "0.11.7.55"', '"agent_runtime_bundle": "0.11.7.56"', 1)

anchor = "def _vex_background_services() -> None:\n"
if anchor not in bridge:
    raise SystemExit("v0.11.7.56 Bridge wrapper anchor missing")
bridge_layer = r'''
# ---------------------------------------------------------------------------
# v0.11.7.56 field identity wrappers
# .55 logic is unchanged; .56 advances the exposed component identity so the
# installer/Remote Support/Bridge field diagnostics agree on the active bundle.
# ---------------------------------------------------------------------------
_v11756_project_supervisor_status_base = _project_supervisor_status


def _project_supervisor_status() -> dict:
    result = _v11756_project_supervisor_status_base()
    result["version"] = "0.11.7.56"
    return result


_v11756_windows_native_capabilities_base = _windows_native_capabilities


def _windows_native_capabilities() -> dict:
    result = _v11756_windows_native_capabilities_base()
    result["version"] = "0.11.7.56"
    return result


'''
if "_v11756_windows_native_capabilities_base" not in bridge:
    bridge = bridge.replace(anchor, bridge_layer + anchor, 1)

remote = re.sub(r'^VERSION = "0\.11\.7\.55"', 'VERSION = "0.11.7.56"', remote, count=1, flags=re.M)

# Field install layout is:
#   <home>/VexDoctor.exe
#   <home>/VexRemoteSupportRuntime/VexRemoteSupport.exe
# The frozen lookup previously searched only the Remote Support child folder.
doctor_old = '    candidates = [base / "VexDoctor.exe", base / "dist" / "VexDoctor.exe"]'
doctor_new = '''    candidates = [
        base / "VexDoctor.exe",
        base.parent / "VexDoctor.exe",
        base / "dist" / "VexDoctor.exe",
        base.parent / "dist" / "VexDoctor.exe",
    ]'''
if doctor_old not in remote:
    raise SystemExit("v0.11.7.56 Remote Doctor lookup anchor missing")
remote = remote.replace(doctor_old, doctor_new, 1)

# The first session snapshot can race the Bridge route table for a few seconds
# immediately after install. Retry only the sanitized Windows capability probe;
# do not expose raw windows/titles or delay later command dispatch.
snapshot_anchor = "def gh_api("
snapshot_layer = r'''_v11756_collect_snapshot_base = collect_snapshot


def collect_snapshot(include_doctor: bool = False, deep: bool = False) -> dict:
    snap = _v11756_collect_snapshot_base(include_doctor=include_doctor, deep=deep)
    native = snap.get("windows_native") if isinstance(snap.get("windows_native"), dict) else {}
    if not bool(native.get("ok")):
        for _attempt in range(3):
            time.sleep(0.6)
            probe = windows_native_public(bridge_get("/windows/capabilities", timeout=12))
            if bool(probe.get("ok")):
                snap["windows_native"] = probe
                break
    return snap


'''
if "_v11756_collect_snapshot_base = collect_snapshot" not in remote:
    if snapshot_anchor not in remote:
        raise SystemExit("v0.11.7.56 Remote snapshot wrapper anchor missing")
    remote = remote.replace(snapshot_anchor, snapshot_layer + snapshot_anchor, 1)

installer = installer.replace('BUNDLE_VERSION = "0.11.7.55"', 'BUNDLE_VERSION = "0.11.7.56"', 1)
installer = installer.replace('REMOTE_VERSION = "0.11.7.55"', 'REMOTE_VERSION = "0.11.7.56"', 1)
installer = installer.replace("Vex Agent Runtime v0.11.7.55 installed.", "Vex Agent Runtime v0.11.7.56 installed.", 1)

BRIDGE.write_text(bridge, encoding="utf-8")
REMOTE.write_text(remote, encoding="utf-8")
INSTALLER.write_text(installer, encoding="utf-8")

for path, text in [(BRIDGE, bridge), (REMOTE, remote), (INSTALLER, installer)]:
    compile(text, str(path), "exec")

for marker in [
    '"agent_runtime_bundle": "0.11.7.56"',
    "_v11756_project_supervisor_status_base",
    "_v11756_windows_native_capabilities_base",
    'result["version"] = "0.11.7.56"',
]:
    if marker not in bridge:
        raise SystemExit(f"v0.11.7.56 Bridge marker missing: {marker}")
for marker in [
    'VERSION = "0.11.7.56"',
    'base.parent / "VexDoctor.exe"',
    "_v11756_collect_snapshot_base = collect_snapshot",
    'bridge_get("/windows/capabilities", timeout=12)',
]:
    if marker not in remote:
        raise SystemExit(f"v0.11.7.56 Remote marker missing: {marker}")
for marker in [
    'BUNDLE_VERSION = "0.11.7.56"',
    'REMOTE_VERSION = "0.11.7.56"',
    "Vex Agent Runtime v0.11.7.56 installed.",
]:
    if marker not in installer:
        raise SystemExit(f"v0.11.7.56 installer marker missing: {marker}")

# Public relay remains sanitized: capability/count telemetry only.
for forbidden in [
    'bridge_get("/windows/windows"',
    '"window_title":',
    '"recent_proposals":',
    '"source_url":',
    '"artifact_path":',
]:
    if forbidden in remote:
        raise SystemExit(f"v0.11.7.56 Remote privacy regression: {forbidden}")

print("Applied v0.11.7.56 Remote Doctor lookup + startup Windows probe hotfix")
