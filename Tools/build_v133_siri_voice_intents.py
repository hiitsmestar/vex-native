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

run("Tools/build_v132_phone_command_relay.py")
run("Tools/apply_v133_siri_voice_intents.py")

voice = (ROOT / "VexNative" / "VexVoiceIntents.swift").read_text(encoding="utf-8")
app = (ROOT / "VexNative" / "VexNativeApp.swift").read_text(encoding="utf-8")
pbx = (ROOT / "VexNative.xcodeproj" / "project.pbxproj").read_text(encoding="utf-8")
content = (ROOT / "VexNative" / "ContentView.swift").read_text(encoding="utf-8")
networking = app

for marker in [
    "import AppIntents",
    "enum VexQuickAction: String, AppEnum",
    "struct VexQuickActionIntent: AppIntent",
    "struct VexVoiceCommandIntent: AppIntent",
    "struct VexAppShortcuts: AppShortcutsProvider",
    '"\\(.applicationName) \\(\\.$action)"',
    '"Hey \\(.applicationName) \\(\\.$action)"',
    '"Ask \\(.applicationName)"',
    "static var openAppWhenRun = false",
    "UIScreen.main.brightness",
    "AVCaptureDevice.default(for: .video)",
    "UIPasteboard.general.string",
]:
    if marker not in voice:
        raise SystemExit(f"v0.13.3 voice marker missing: {marker}")

if '"Hey \\(.applicationName) \\(\\.$command)"' in voice:
    raise SystemExit("free-form String parameter leaked into App Shortcut phrase")

if "VexAppShortcuts.updateAppShortcutParameters()" not in app:
    raise SystemExit("v0.13.3 app shortcut registration missing")
if "VexVoiceIntents.swift in Sources" not in pbx:
    raise SystemExit("v0.13.3 Xcode source wiring missing")

for marker in [
    'V132_PHONE_COMMAND_RELAY = "v0.13.2-phone-command-relay-v1"',
    "PhoneRemoteCommandRelay.shared.run(app: app)",
    "PhoneToolRouter.tryHandle",
    "PCArtRouter.tryHandle",
]:
    if marker not in content:
        raise SystemExit(f"v0.13.2 inherited marker missing: {marker}")

for marker in [
    "challenge.protectionSpace.port == 8771",
    "[8765, 8771].contains(port)",
    "configuration.timeoutIntervalForRequest = 95",
]:
    if marker not in networking:
        raise SystemExit(f"v0.13.2 networking marker missing: {marker}")

print("PASS v0.13.3 Siri voice/App Intents chain")
