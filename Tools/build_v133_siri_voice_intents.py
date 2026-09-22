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

for marker in [
    "import AppIntents",
    "enum VexQuickAction: String, AppEnum",
    "struct VexQuickActionIntent: AppIntent",
    "struct VexVoiceCommandIntent: AppIntent",
    "struct VexAppShortcuts: AppShortcutsProvider",
    '"Hey \\(.applicationName) \\(\\.$action)"',
    '"Ask \\(.applicationName) to \\(\\.$action)"',
    '"Ask \\(.applicationName)"',
    "UIScreen.main.brightness",
    "AVCaptureDevice.default(for: .video)",
    "UIPasteboard.general.string",
]:
    if marker not in voice:
        raise SystemExit(f"v0.13.3 voice marker missing: {marker}")

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

print("PASS v0.13.3 Siri voice/App Intents chain")
