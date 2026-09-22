#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOICE = ROOT / "VexNative" / "VexVoiceIntents.swift"

text = VOICE.read_text(encoding="utf-8")

start = text.find("struct VexAppShortcuts: AppShortcutsProvider {")
if start < 0:
    raise SystemExit("v0.13.3.1 AppShortcuts anchor missing")

text = text[:start].rstrip() + "\n\n"

replacement = r'''enum VexQuickAction: String, AppEnum {
    case flashlightOn
    case flashlightOff
    case brightness25
    case brightness50
    case brightness75
    case brightness100
    case openSettings
    case openYouTube
    case openSpotify
    case openGmail
    case openMaps

    static var typeDisplayRepresentation = TypeDisplayRepresentation(name: "Vex action")

    static var caseDisplayRepresentations: [VexQuickAction: DisplayRepresentation] = [
        .flashlightOn: "turn flashlight on",
        .flashlightOff: "turn flashlight off",
        .brightness25: "set brightness to 25 percent",
        .brightness50: "set brightness to 50 percent",
        .brightness75: "set brightness to 75 percent",
        .brightness100: "set brightness to 100 percent",
        .openSettings: "open settings",
        .openYouTube: "open YouTube",
        .openSpotify: "open Spotify",
        .openGmail: "open Gmail",
        .openMaps: "open Maps"
    ]

    var command: String {
        switch self {
        case .flashlightOn: return "turn flashlight on"
        case .flashlightOff: return "turn flashlight off"
        case .brightness25: return "set brightness to 25 percent"
        case .brightness50: return "set brightness to 50 percent"
        case .brightness75: return "set brightness to 75 percent"
        case .brightness100: return "set brightness to 100 percent"
        case .openSettings: return "open settings"
        case .openYouTube: return "open YouTube"
        case .openSpotify: return "open Spotify"
        case .openGmail: return "open Gmail"
        case .openMaps: return "open Maps"
        }
    }
}

struct VexQuickActionIntent: AppIntent {
    static var title: LocalizedStringResource = "Vex Quick Action"
    static var description = IntentDescription("Run a supported Vex iPhone action immediately.")
    static var openAppWhenRun = false

    @Parameter(title: "Action")
    var action: VexQuickAction

    static var parameterSummary: some ParameterSummary {
        Summary("\(\.$action)")
    }

    @MainActor
    func perform() async throws -> some IntentResult & ProvidesDialog {
        switch await VexVoicePhoneExecutor.perform(action.command) {
        case .completed:
            return .result(dialog: "Done.")
        case .needsValue:
            return .result(dialog: "I need a little more detail.")
        case .unsupported:
            return .result(dialog: "That Vex phone action is not wired in yet.")
        case .failed:
            return .result(dialog: "That phone action did not complete.")
        }
    }
}

struct VexAppShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: VexQuickActionIntent(),
            phrases: [
                "\(.applicationName) \(\.$action)",
                "Ask \(.applicationName) to \(\.$action)"
            ],
            shortTitle: "Vex Quick Action",
            systemImageName: "bolt.fill"
        )

        AppShortcut(
            intent: VexVoiceCommandIntent(),
            phrases: [
                "Hey \(.applicationName)",
                "Ask \(.applicationName)",
                "Talk to \(.applicationName)"
            ],
            shortTitle: "Ask Vex",
            systemImageName: "waveform"
        )
    }
}
'''

text += replacement
VOICE.write_text(text, encoding="utf-8")

final = VOICE.read_text(encoding="utf-8")
for marker in [
    "enum VexQuickAction: String, AppEnum",
    "struct VexQuickActionIntent: AppIntent",
    '"\(.applicationName) \(\.$action)"',
    '"Hey \(.applicationName)"',
    "VexVoiceCommandIntent()",
]:
    if marker not in final:
        raise SystemExit(f"v0.13.3.1 marker missing: {marker}")

if '"Hey \(.applicationName) \(\.$command)"' in final:
    raise SystemExit("free-form String parameter still appears in App Shortcut phrase")

print("PASS v0.13.3.1 Siri phrase hotfix")
