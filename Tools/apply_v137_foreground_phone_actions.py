#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOICE = ROOT / "VexNative" / "VexVoiceIntents.swift"

text = VOICE.read_text(encoding="utf-8")

if "V137_FOREGROUND_PHONE_ACTIONS" in text:
    print("PASS v0.13.7 foreground phone actions already applied")
    raise SystemExit(0)

if "import AVFoundation\n" not in text:
    text = text.replace("import AppIntents\n", "import AppIntents\nimport AVFoundation\n", 1)

text = text.replace(
    'private let V134_SIRI_HARDWARE_ROUTING = "v0.13.4-native-system-routing-v1"\n',
    'private let V134_SIRI_HARDWARE_ROUTING = "v0.13.4-native-system-routing-v1"\n'
    'private let V137_FOREGROUND_PHONE_ACTIONS = "v0.13.7-foreground-phone-actions-v1"\n',
    1,
)

text = text.replace(
    "enum VexQuickAction: String, AppEnum {\n",
    "enum VexQuickAction: String, AppEnum {\n    case flashlightOn\n    case flashlightOff\n",
    1,
)
text = text.replace(
    "    static var caseDisplayRepresentations: [VexQuickAction: DisplayRepresentation] = [\n",
    "    static var caseDisplayRepresentations: [VexQuickAction: DisplayRepresentation] = [\n"
    '        .flashlightOn: "turn on the flashlight",\n'
    '        .flashlightOff: "turn off the flashlight",\n',
    1,
)
text = text.replace(
    "        switch self {\n",
    "        switch self {\n"
    '        case .flashlightOn: return "turn on the flashlight on my phone"\n'
    '        case .flashlightOff: return "turn off the flashlight on my phone"\n',
    1,
)

old_flash = '''        if lower.contains("flashlight") || lower.contains("torch") {
            return .systemShortcutRequired
        }'''
new_flash = '''        if lower.contains("flashlight") || lower.contains("torch") {
            return setTorch(lower) ? .completed : .failed
        }'''
if old_flash not in text:
    raise SystemExit("v0.13.7 flashlight anchor missing")
text = text.replace(old_flash, new_flash, 1)

helper_anchor = "    private static func clipboardPayload(_ original: String) -> String? {"
helper = '''    private static func setTorch(_ lower: String) -> Bool {
        guard UIApplication.shared.applicationState == .active else { return false }
        guard let device = AVCaptureDevice.default(for: .video), device.hasTorch else { return false }
        do {
            try device.lockForConfiguration()
            defer { device.unlockForConfiguration() }
            let wantsOff = lower.contains(" off") || lower.hasSuffix("off")
            let wantsOn = lower.contains(" on") || lower.hasSuffix("on")
            if wantsOff {
                device.torchMode = .off
                return true
            }
            if wantsOn {
                try device.setTorchModeOn(level: 1.0)
                return true
            }
            if device.isTorchActive {
                device.torchMode = .off
            } else {
                try device.setTorchModeOn(level: 1.0)
            }
            return true
        } catch {
            return false
        }
    }

'''
if helper_anchor not in text:
    raise SystemExit("v0.13.7 helper anchor missing")
text = text.replace(helper_anchor, helper + helper_anchor, 1)

text = text.replace("static var openAppWhenRun = false", "static var openAppWhenRun = true")

VOICE.write_text(text, encoding="utf-8")

final = VOICE.read_text(encoding="utf-8")
for marker in [
    'V137_FOREGROUND_PHONE_ACTIONS = "v0.13.7-foreground-phone-actions-v1"',
    "case flashlightOn",
    "case flashlightOff",
    "private static func setTorch",
    "UIApplication.shared.applicationState == .active",
    "static var openAppWhenRun = true",
]:
    if marker not in final:
        raise SystemExit(f"v0.13.7 marker missing: {marker}")

if final.count("static var openAppWhenRun = true") < 2:
    raise SystemExit("v0.13.7 expected both intents to foreground the app")

print("PASS v0.13.7 foreground phone actions patch")
