#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
VOICE = ROOT / "VexNative" / "VexVoiceIntents.swift"

text = VOICE.read_text(encoding="utf-8")

if "V134_SIRI_HARDWARE_ROUTING" in text:
    print("PASS v0.13.4 Siri hardware routing already applied")
    raise SystemExit(0)

text = text.replace("import AVFoundation\n", "", 1)
text = text.replace(
    "private enum VexVoiceActionResult {\n"
    "    case completed\n"
    "    case needsValue\n"
    "    case unsupported\n"
    "    case failed\n"
    "}",
    "private let V134_SIRI_HARDWARE_ROUTING = \"v0.13.4-native-system-routing-v1\"\n\n"
    "private enum VexVoiceActionResult {\n"
    "    case completed\n"
    "    case needsValue\n"
    "    case unsupported\n"
    "    case systemShortcutRequired\n"
    "    case failed\n"
    "}",
    1,
)

for snippet in [
    "    case flashlightOn\n",
    "    case flashlightOff\n",
    '        .flashlightOn: "turn on the flashlight",\n',
    '        .flashlightOff: "turn off the flashlight",\n',
    '        case .flashlightOn: return "turn on the flashlight on my phone"\n',
    '        case .flashlightOff: return "turn off the flashlight on my phone"\n',
]:
    text = text.replace(snippet, "")

old_brightness = '''        if lower.contains("brightness") {
            guard let percent = firstNumber(in: lower) else { return .needsValue }
            UIScreen.main.brightness = CGFloat(max(0, min(100, percent)) / 100.0)
            return .completed
        }'''
new_brightness = '''        if lower.contains("brightness") {
            guard let percent = firstNumber(in: lower) else { return .needsValue }
            let target = CGFloat(max(0, min(100, percent)) / 100.0)
            UIScreen.main.brightness = target
            try? await Task.sleep(nanoseconds: 150_000_000)
            return abs(UIScreen.main.brightness - target) <= 0.02 ? .completed : .failed
        }'''
if old_brightness not in text:
    raise SystemExit("v0.13.4 brightness anchor missing")
text = text.replace(old_brightness, new_brightness, 1)

old_flash = '''        if lower.contains("flashlight") || lower.contains("torch") {
            return setTorch(lower) ? .completed : .failed
        }'''
new_flash = '''        if lower.contains("flashlight") || lower.contains("torch") {
            return .systemShortcutRequired
        }'''
if old_flash not in text:
    raise SystemExit("v0.13.4 flashlight route anchor missing")
text = text.replace(old_flash, new_flash, 1)

pattern = re.compile(r'''\n    private static func setTorch\(_ lower: String\) -> Bool \{.*?\n    \}\n''', re.S)
text, count = pattern.subn("\n", text, count=1)
if count != 1:
    raise SystemExit("v0.13.4 setTorch removal failed")

old_clip = '''            UIPasteboard.general.string = payload
            return .completed'''
new_clip = '''            UIPasteboard.general.string = payload
            return UIPasteboard.general.string == payload ? .completed : .failed'''
if old_clip not in text:
    raise SystemExit("v0.13.4 clipboard anchor missing")
text = text.replace(old_clip, new_clip, 1)

text = text.replace(
    '''        case .unsupported:
            return .result(dialog: "That Vex phone action is not wired in yet.")
        case .failed:''',
    '''        case .unsupported:
            return .result(dialog: "That Vex phone action is not wired in yet.")
        case .systemShortcutRequired:
            return .result(dialog: "That system control needs the native Vex Shortcut.")
        case .failed:''',
)

VOICE.write_text(text, encoding="utf-8")

final = VOICE.read_text(encoding="utf-8")
for marker in [
    'V134_SIRI_HARDWARE_ROUTING = "v0.13.4-native-system-routing-v1"',
    "case systemShortcutRequired",
    "return .systemShortcutRequired",
    "abs(UIScreen.main.brightness - target) <= 0.02",
    "UIPasteboard.general.string == payload",
]:
    if marker not in final:
        raise SystemExit(f"v0.13.4 marker missing: {marker}")

for forbidden in [
    "case flashlightOn",
    "case flashlightOff",
    "private static func setTorch",
    "import AVFoundation",
]:
    if forbidden in final:
        raise SystemExit(f"v0.13.4 forbidden legacy marker remains: {forbidden}")

print("PASS v0.13.4 Siri hardware routing patch")
