#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def run(path: str) -> None:
    print(f"==> {path}", flush=True)
    result = subprocess.run([sys.executable, path], cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(result.returncode)

run("Tools/build_v135_bad_query_probe.py")
run("Tools/apply_v136_container_child_probe.py")

pbx = (ROOT / "VexNative.xcodeproj" / "project.pbxproj").read_text(encoding="utf-8")
content = (ROOT / "VexNative" / "ContentView.swift").read_text(encoding="utf-8")
probe = (ROOT / "VexNative" / "VexContainerChildProbe.c").read_text(encoding="utf-8")
diagnostics = (ROOT / "VexNative" / "VexContainerChildDiagnostics.swift").read_text(encoding="utf-8")

for marker in [
    "VexContainerChildProbe.c in Sources",
    "VexContainerChildDiagnostics.swift in Sources",
    "VexContainerChildProbeView()",
    'buildMarker = "v0.13.6-read-only-child-container-probe-v1"',
    "vex_bad_query_list_children",
    "vex_bad_query_grant_read",
    "MCMMetadataIdentifier",
]:
    if marker not in pbx + "\n" + content + "\n" + probe + "\n" + diagnostics:
        raise SystemExit(f"v0.13.6 marker missing: {marker}")

for inherited in [
    'buildMarker = "v0.13.5-read-only-bad-query-probe-v1"',
    'V134_SIRI_HARDWARE_ROUTING = "v0.13.4-native-system-routing-v1"',
    "PhoneRemoteCommandRelay.shared.run(app: app)",
    "PCArtRouter.tryHandle",
]:
    inherited_text = (
        (ROOT / "VexNative" / "VexBadQueryDiagnostics.swift").read_text(encoding="utf-8")
        + "\n"
        + (ROOT / "VexNative" / "VexVoiceIntents.swift").read_text(encoding="utf-8")
        + "\n"
        + content
    )
    if inherited not in inherited_text:
        raise SystemExit(f"v0.13.6 inherited marker missing: {inherited}")

for forbidden in [
    "O_WRONLY", "O_RDWR", "unlink(", "rename(", "removeItem(",
    "createFile(", "replaceItem(", ".write(to:"
]:
    if forbidden in probe or forbidden in diagnostics:
        raise SystemExit(f"v0.13.6 mutation primitive forbidden: {forbidden}")

print("PASS v0.13.6 read-only child-container probe chain")
