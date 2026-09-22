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

run("Tools/build_v134_siri_hardware_routing.py")
run("Tools/apply_v135_bad_query_probe.py")

pbx = (ROOT / "VexNative.xcodeproj" / "project.pbxproj").read_text(encoding="utf-8")
content = (ROOT / "VexNative" / "ContentView.swift").read_text(encoding="utf-8")
probe = (ROOT / "VexNative" / "VexBadQueryProbe.c").read_text(encoding="utf-8")
diagnostics = (ROOT / "VexNative" / "VexBadQueryDiagnostics.swift").read_text(encoding="utf-8")

for marker in [
    "VexBadQueryProbe.c in Sources",
    "VexBadQueryDiagnostics.swift in Sources",
]:
    if marker not in pbx:
        raise SystemExit(f"v0.13.5 Xcode source marker missing: {marker}")

for marker in [
    "VexBadQueryProbeView()",
    'buildMarker = "v0.13.5-read-only-bad-query-probe-v1"',
    '@_silgen_name("vex_bad_query_grant_read")',
    "vex_bad_query_grant_read",
    "vex_bad_query_release",
    "version.majorVersion == 26",
    "version.patchVersion <= 1",
]:
    if marker not in content + "\n" + diagnostics + "\n" + probe:
        raise SystemExit(f"v0.13.5 probe marker missing: {marker}")

for inherited in [
    'V134_SIRI_HARDWARE_ROUTING = "v0.13.4-native-system-routing-v1"',
    "PhoneRemoteCommandRelay.shared.run(app: app)",
    "PCArtRouter.tryHandle",
]:
    inherited_text = (
        (ROOT / "VexNative" / "VexVoiceIntents.swift").read_text(encoding="utf-8")
        + "\n"
        + content
    )
    if inherited not in inherited_text:
        raise SystemExit(f"v0.13.5 inherited marker missing: {inherited}")

for forbidden in [
    "O_WRONLY",
    "O_RDWR",
    "unlink(",
    "rename(",
    "removeItem(",
    "createFile(",
    "replaceItem(",
    ".write(to:",
]:
    if forbidden in probe or forbidden in diagnostics:
        raise SystemExit(f"v0.13.5 mutation primitive forbidden: {forbidden}")

print("PASS v0.13.5 read-only bad_query probe chain")
