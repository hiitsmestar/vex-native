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
run("Tools/apply_v138_background_agent_foundation.py")

bg = (ROOT / "VexNative" / "VexBackgroundAgent.swift").read_text(encoding="utf-8")
app = (ROOT / "VexNative" / "VexNativeApp.swift").read_text(encoding="utf-8")
voice = (ROOT / "VexNative" / "VexVoiceIntents.swift").read_text(encoding="utf-8")
pbx = (ROOT / "VexNative.xcodeproj" / "project.pbxproj").read_text(encoding="utf-8")

for marker in [
    "BGTaskScheduler.shared.register",
    "BGAppRefreshTaskRequest",
    "BGProcessingTaskRequest",
    "VexPhoneBackgroundWorker.runOnce",
    "VexHeadlessBrain.reply",
    'parts.port = 8771',
]:
    if marker not in bg:
        raise SystemExit(f"v0.13.8 background marker missing: {marker}")

for marker in [
    "@UIApplicationDelegateAdaptor(VexAppDelegate.self)",
    "challenge.protectionSpace.port == 8771",
]:
    if marker not in app:
        raise SystemExit(f"v0.13.8 app marker missing: {marker}")

if "VexHeadlessBrain.reply(to: command)" not in voice:
    raise SystemExit("v0.13.8 voice headless route missing")
quick = voice.split("struct VexQuickActionIntent: AppIntent", 1)[1].split("struct VexVoiceCommandIntent: AppIntent", 1)[0]
command_intent = voice.split("struct VexVoiceCommandIntent: AppIntent", 1)[1]
if "static var openAppWhenRun = false" not in quick:
    raise SystemExit("v0.13.8 quick actions must remain background-first")
if "V146_FOREGROUND_COMMAND_HANDOFF" in voice and "static var openAppWhenRun = true" not in command_intent:
    raise SystemExit("v0.14.6 Ask Vex must foreground for app handoff")
if "VexBackgroundAgent.swift in Sources" not in pbx:
    raise SystemExit("v0.13.8 background source not in Xcode project")

print("PASS v0.13.8 background agent foundation chain")
