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

run("Tools/build_v133_siri_voice_intents.py")
run("Tools/apply_v134_siri_hardware_routing.py")

voice = (ROOT / "VexNative" / "VexVoiceIntents.swift").read_text(encoding="utf-8")
content = (ROOT / "VexNative" / "ContentView.swift").read_text(encoding="utf-8")
app = (ROOT / "VexNative" / "VexNativeApp.swift").read_text(encoding="utf-8")

for marker in [
    'V134_SIRI_HARDWARE_ROUTING = "v0.13.4-native-system-routing-v1"',
    "case systemShortcutRequired",
    "return .systemShortcutRequired",
    "abs(UIScreen.main.brightness - target) <= 0.02",
    "UIPasteboard.general.string == payload",
    "struct VexQuickActionIntent: AppIntent",
    "struct VexVoiceCommandIntent: AppIntent",
    "struct VexAppShortcuts: AppShortcutsProvider",
]:
    if marker not in voice:
        raise SystemExit(f"v0.13.4 voice marker missing: {marker}")

for forbidden in [
    "case flashlightOn",
    "case flashlightOff",
    "private static func setTorch",
]:
    if forbidden in voice:
        raise SystemExit(f"v0.13.4 forbidden marker remains: {forbidden}")

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
    if marker not in app:
        raise SystemExit(f"v0.13.2 networking marker missing: {marker}")

print("PASS v0.13.4 Siri hardware routing chain")
