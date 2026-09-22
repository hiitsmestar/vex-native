#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "Tools" / "VexVoiceIntents.swift"
VOICE = ROOT / "VexNative" / "VexVoiceIntents.swift"
APP = ROOT / "VexNative" / "VexNativeApp.swift"
PBX = ROOT / "VexNative.xcodeproj" / "project.pbxproj"

if not TEMPLATE.exists():
    raise SystemExit("v0.13.3 voice intent template missing")

VOICE.write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")

app = APP.read_text(encoding="utf-8")
if "import AppIntents" not in app:
    app = app.replace("import Foundation", "import AppIntents\nimport Foundation", 1)

old = """struct VexNativeApp: App {
    @StateObject private var appModel = AppModel()

    var body: some Scene {"""
new = """struct VexNativeApp: App {
    @StateObject private var appModel = AppModel()

    init() {
        VexAppShortcuts.updateAppShortcutParameters()
    }

    var body: some Scene {"""
if "VexAppShortcuts.updateAppShortcutParameters()" not in app:
    if old not in app:
        raise SystemExit("v0.13.3 app init anchor missing")
    app = app.replace(old, new, 1)
APP.write_text(app, encoding="utf-8")

pbx = PBX.read_text(encoding="utf-8")
if "VexVoiceIntents.swift in Sources" not in pbx:
    a = 'A000000000000000000004A /* BrainView.swift in Sources */ = {isa = PBXBuildFile; fileRef = A000000000000000000002A /* BrainView.swift */; };'
    b = a + '\n\t\tA000000000000000000004B /* VexVoiceIntents.swift in Sources */ = {isa = PBXBuildFile; fileRef = A000000000000000000002B /* VexVoiceIntents.swift */; };'
    if a not in pbx:
        raise SystemExit("v0.13.3 build file anchor missing")
    pbx = pbx.replace(a, b, 1)

    a = 'A000000000000000000002A /* BrainView.swift */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = BrainView.swift; sourceTree = "<group>"; };'
    b = a + '\n\t\tA000000000000000000002B /* VexVoiceIntents.swift */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = VexVoiceIntents.swift; sourceTree = "<group>"; };'
    if a not in pbx:
        raise SystemExit("v0.13.3 file ref anchor missing")
    pbx = pbx.replace(a, b, 1)
    a = '\t\t\t\tA0000000000000000000023 /* ContentView.swift */,'
    b = a + '\n\t\t\t\tA000000000000000000002B /* VexVoiceIntents.swift */,'
    pbx = pbx.replace(a, b, 1)

    a = '\t\t\t\tA000000000000000000004A /* BrainView.swift in Sources */,'
    b = a + '\n\t\t\t\tA000000000000000000004B /* VexVoiceIntents.swift in Sources */,'
    pbx = pbx.replace(a, b, 1)

PBX.write_text(pbx, encoding="utf-8")

voice = VOICE.read_text(encoding="utf-8")
checks = [
    "struct VexQuickActionIntent: AppIntent",
    "struct VexVoiceCommandIntent: AppIntent",
    "struct VexAppShortcuts: AppShortcutsProvider",
    "VexAppShortcuts.updateAppShortcutParameters()",
]
if not all(marker in voice or marker in APP.read_text(encoding="utf-8") for marker in checks):
    raise SystemExit("v0.13.3 patch verification failed")
if "VexVoiceIntents.swift in Sources" not in PBX.read_text(encoding="utf-8"):
    raise SystemExit("v0.13.3 Xcode source wiring missing")

print("PASS v0.13.3 Siri voice intents patch")