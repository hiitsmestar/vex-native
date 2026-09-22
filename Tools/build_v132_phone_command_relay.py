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

run("Tools/build_v131_ios_timeout_ui_hotfix.py")
run("Tools/apply_v132_phone_command_relay.py")

content = (ROOT / "VexNative" / "ContentView.swift").read_text(encoding="utf-8")
networking = (ROOT / "VexNative" / "VexNativeApp.swift").read_text(encoding="utf-8")
app_model = (ROOT / "VexNative" / "AppModel.swift").read_text(encoding="utf-8")

for marker in [
    'V132_PHONE_COMMAND_RELAY = "v0.13.2-phone-command-relay-v1"',
    "private final class PhoneRemoteCommandRelay",
    'relayURL(path: "/phone/next")',
    'relayURL(path: "/phone/result")',
    "PhoneRemoteCommandRelay.shared.run(app: app)",
    "PhoneToolRouter.tryHandle(routed, app: app)",
    "parts.port = 8771",
    "PCArtRouter.tryHandle",
    "PhoneToolRouter.tryHandle",
    "import Vision",
    "CameraCaptureView",
]:
    if marker not in content:
        raise SystemExit(f"v0.13.2 content marker missing: {marker}")

for marker in [
    "challenge.protectionSpace.port == 8771",
    "[8765, 8771].contains(port)",
    "configuration.timeoutIntervalForRequest = 95",
    "configuration.timeoutIntervalForResource = 100",
]:
    if marker not in networking:
        raise SystemExit(f"v0.13.2 networking marker missing: {marker}")

if 'V127_INLINE_STAGE_DIRECTION_FIX_IOS = "v0.12.7-inline-stage-direction-v1"' not in app_model:
    raise SystemExit("v0.12.7 dialogue fix missing")

print("PASS v0.13.2 VexNative phone-command-relay chain")
