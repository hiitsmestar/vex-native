#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOICE = ROOT / "VexNative" / "VexVoiceIntents.swift"

text = VOICE.read_text(encoding="utf-8")

marker = 'private static let V146_AUTONOMOUS_FOREGROUND_HANDOFF = "v0.14.6-autonomous-foreground-handoff-v1"'
if marker in text:
    print("PASS v0.14.6 autonomous foreground handoff already applied")
    raise SystemExit(0)

anchor = '''struct VexVoiceCommandIntent: AppIntent {
    static var title: LocalizedStringResource = "Ask Vex"
    static var description = IntentDescription("Give Vex a spoken iPhone command.")
    static var openAppWhenRun = false'''
replacement = '''struct VexVoiceCommandIntent: AppIntent {
    private static let V146_AUTONOMOUS_FOREGROUND_HANDOFF = "v0.14.6-autonomous-foreground-handoff-v1"
    static var title: LocalizedStringResource = "Ask Vex"
    static var description = IntentDescription("Give Vex a spoken iPhone command.")
    static var openAppWhenRun = true'''

if anchor not in text:
    raise SystemExit("v0.14.6 Ask Vex foreground anchor missing")

text = text.replace(anchor, replacement, 1)
VOICE.write_text(text, encoding="utf-8")

final = VOICE.read_text(encoding="utf-8")
for required in [
    "V146_AUTONOMOUS_FOREGROUND_HANDOFF",
    "struct VexVoiceCommandIntent: AppIntent",
    "static var openAppWhenRun = true",
]:
    if required not in final:
        raise SystemExit(f"missing v0.14.6 marker: {required}")

print("PASS v0.14.6 autonomous foreground handoff patch")
