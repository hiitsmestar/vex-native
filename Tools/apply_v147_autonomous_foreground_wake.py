#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOICE = ROOT / "VexNative" / "VexVoiceIntents.swift"

text = VOICE.read_text(encoding="utf-8")
if "V147_AUTONOMOUS_FOREGROUND_WAKE" in text:
    print("PASS v0.14.7 autonomous foreground wake already applied")
    raise SystemExit(0)

anchor = '''struct VexVoiceCommandIntent: AppIntent {
    static var title: LocalizedStringResource = "Ask Vex"
    static var description = IntentDescription("Give Vex a spoken iPhone command.")
    static var openAppWhenRun = false'''
replacement = '''struct VexVoiceCommandIntent: AppIntent {
    // V147_AUTONOMOUS_FOREGROUND_WAKE
    static var title: LocalizedStringResource = "Ask Vex"
    static var description = IntentDescription("Give Vex a spoken iPhone command.")
    static var openAppWhenRun = true'''
if anchor not in text:
    raise SystemExit("v0.14.7 Ask Vex foreground anchor missing")
text = text.replace(anchor, replacement, 1)

anchor = '''    @MainActor
    func perform() async throws -> some IntentResult & ProvidesDialog {
        switch await VexVoicePhoneExecutor.perform(command) {'''
replacement = '''    @MainActor
    func perform() async throws -> some IntentResult & ProvidesDialog {
        let wake = command.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        if wake == "wake and check remote relay" {
            _ = await VexPhoneBackgroundWorker.runOnce()
            return .result(dialog: "Ready.")
        }

        switch await VexVoicePhoneExecutor.perform(command) {'''
if anchor not in text:
    raise SystemExit("v0.14.7 Ask Vex perform anchor missing")
text = text.replace(anchor, replacement, 1)

VOICE.write_text(text, encoding="utf-8")
final = VOICE.read_text(encoding="utf-8")
for marker in [
    "V147_AUTONOMOUS_FOREGROUND_WAKE",
    "static var openAppWhenRun = true",
    'wake == "wake and check remote relay"',
    "await VexPhoneBackgroundWorker.runOnce()",
]:
    if marker not in final:
        raise SystemExit(f"missing v0.14.7 marker: {marker}")

print("PASS v0.14.7 autonomous foreground wake patch")
