#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOICE = ROOT / "VexNative" / "VexVoiceIntents.swift"
APP = ROOT / "VexNative" / "VexNativeApp.swift"
PBX = ROOT / "VexNative.xcodeproj" / "project.pbxproj"

VOICE_SOURCE = r'''import AppIntents
import AVFoundation
import Foundation
import UIKit

private enum VexVoiceActionResult {
    case completed
    case needsValue
    case unsupported
    case failed
}

@MainActor
private enum VexVoicePhoneExecutor {
    static func perform(_ original: String) async -> VexVoiceActionResult {
        let lower = normalize(original)

        if lower.contains("brightness") {
            guard let percent = firstNumber(in: lower) else { return .needsValue }
            UIScreen.main.brightness = CGFloat(max(0, min(100, percent)) / 100.0)
            return .completed
        }
        if lower.contains("flashlight") || lower.contains("torch") {
            return setTorch(lower) ? .completed : .failed
        }

        if lower.contains("clipboard") && (lower.contains("copy ") || lower.contains("put ")) {
            guard let payload = clipboardPayload(original) else { return .needsValue }
            UIPasteboard.general.string = payload
            return .completed
        }

        if lower.contains("settings") {
            let opened = await open(URL(string: UIApplication.openSettingsURLString)!)
            return opened ? .completed : .failed
        }

        if wantsOpen(lower), let url = knownURL(lower: lower, original: original) {
            let opened = await open(url)
            return opened ? .completed : .failed
        }

        return .unsupported
    }

    private static func firstNumber(in text: String) -> Double? {
        var current = ""
        var seenDigit = false
        for ch in text {
            if ch.isNumber || (ch == "." && seenDigit) {
                current.append(ch)
                seenDigit = seenDigit || ch.isNumber
            } else if seenDigit {
                break
            }
        }
        return Double(current)
    }
    private static func setTorch(_ lower: String) -> Bool {
        guard let device = AVCaptureDevice.default(for: .video), device.hasTorch else {
            return false
        }
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

    private static func clipboardPayload(_ original: String) -> String? {
        let lower = original.lowercased()
        for marker in ["copy ", "put "] {
            guard let range = lower.range(of: marker) else { continue }
            var value = String(original[range.upperBound...])
                .trimmingCharacters(in: .whitespacesAndNewlines)
            let suffixes = [
                " to the clipboard", " on the clipboard", " to clipboard",
                " on clipboard", " to my iphone clipboard", " on my iphone clipboard"
            ]
            for suffix in suffixes where value.lowercased().hasSuffix(suffix) {
                value = String(value.dropLast(suffix.count))
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                break
            }
            if !value.isEmpty { return value }
        }
        return nil
    }

    private static func wantsOpen(_ lower: String) -> Bool {
        ["open ", "open up ", "launch ", "go to ", "bring up ", "show me "]
            .contains(where: { lower.contains($0) })
    }

    private static func knownURL(lower: String, original: String) -> URL? {
        let known: [(String, String)] = [
            ("youtube", "https://www.youtube.com"),
            ("google", "https://www.google.com"),
            ("gmail", "https://mail.google.com"),
            ("spotify", "https://open.spotify.com"),
            ("reddit", "https://www.reddit.com"),
            ("github", "https://github.com"),
            ("maps", "https://maps.apple.com")
        ]
        if let hit = known.first(where: { lower.contains($0.0) }) {
            return URL(string: hit.1)
        }

        let words = original.split(whereSeparator: { $0.isWhitespace }).map(String.init)
        if let raw = words.first(where: {
            $0.lowercased().hasPrefix("https://") || $0.lowercased().hasPrefix("http://")
        }) {
            let clean = raw.trimmingCharacters(in: CharacterSet(charactersIn: ",.;!?)\"]}"))
            return URL(string: clean)
        }
        return nil
    }
    private static func open(_ url: URL) async -> Bool {
        await withCheckedContinuation { continuation in
            UIApplication.shared.open(url, options: [:]) { opened in
                continuation.resume(returning: opened)
            }
        }
    }

    private static func normalize(_ text: String) -> String {
        text.lowercased()
            .replacingOccurrences(of: "’", with: "'")
            .replacingOccurrences(of: "‘", with: "'")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

struct VexVoiceCommandIntent: AppIntent {
    static var title: LocalizedStringResource = "Ask Vex"
    static var description = IntentDescription("Give Vex a spoken iPhone command.")
    static var openAppWhenRun = false

    @Parameter(
        title: "Command",
        requestValueDialog: IntentDialog("What should Vex do?")
    )
    var command: String

    static var parameterSummary: some ParameterSummary {
        Summary("Ask Vex to \(\.$command)")
    }

    @MainActor
    func perform() async throws -> some IntentResult & ProvidesDialog {
        switch await VexVoicePhoneExecutor.perform(command) {
        case .completed:
            return .result(dialog: "Done.")
        case .needsValue:
            return .result(dialog: "I need a little more detail for that command.")
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
            intent: VexVoiceCommandIntent(),
            phrases: [
                "\(.applicationName) \(\.$command)",
                "Hey \(.applicationName) \(\.$command)",
                "Ask \(.applicationName) to \(\.$command)",
                "Tell \(.applicationName) to \(\.$command)"
            ],
            shortTitle: "Ask Vex",
            systemImageName: "waveform"
        )
    }
}
'''

VOICE.write_text(VOICE_SOURCE, encoding="utf-8")

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

checks = [
    VOICE.exists(),
    "VexVoiceCommandIntent" in VOICE.read_text(encoding="utf-8"),
    "VexAppShortcuts.updateAppShortcutParameters()" in APP.read_text(encoding="utf-8"),
    "VexVoiceIntents.swift in Sources" in PBX.read_text(encoding="utf-8"),
]
if not all(checks):
    raise SystemExit("v0.13.3 patch verification failed")

print("PASS v0.13.3 Siri voice intents patch")