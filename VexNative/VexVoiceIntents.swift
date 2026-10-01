import AppIntents
import Foundation
import UIKit

private let V134_SIRI_HARDWARE_ROUTING = "v0.13.4-native-system-routing-v1"

private enum VexVoiceActionResult {
    case completed
    case needsValue
    case unsupported
    case systemShortcutRequired
    case failed
}

enum VexQuickAction: String, AppEnum {
    case brightness25
    case brightness50
    case brightness75
    case brightness100
    case openYouTube
    case openGoogle
    case openGmail
    case openSpotify
    case openReddit
    case openGitHub
    case openMaps
    case openSettings

    static var typeDisplayRepresentation = TypeDisplayRepresentation(name: "Vex Action")
    static var caseDisplayRepresentations: [VexQuickAction: DisplayRepresentation] = [
        .brightness25: "set brightness to 25 percent",
        .brightness50: "set brightness to 50 percent",
        .brightness75: "set brightness to 75 percent",
        .brightness100: "set brightness to 100 percent",
        .openYouTube: "open YouTube",
        .openGoogle: "open Google",
        .openGmail: "open Gmail",
        .openSpotify: "open Spotify",
        .openReddit: "open Reddit",
        .openGitHub: "open GitHub",
        .openMaps: "open Maps",
        .openSettings: "open Settings"
    ]

    var command: String {
        switch self {
        case .brightness25: return "set brightness on my phone to 25%"
        case .brightness50: return "set brightness on my phone to 50%"
        case .brightness75: return "set brightness on my phone to 75%"
        case .brightness100: return "set brightness on my phone to 100%"
        case .openYouTube: return "open YouTube on my phone"
        case .openGoogle: return "open Google on my phone"
        case .openGmail: return "open Gmail on my phone"
        case .openSpotify: return "open Spotify on my phone"
        case .openReddit: return "open Reddit on my phone"
        case .openGitHub: return "open GitHub on my phone"
        case .openMaps: return "open Maps on my phone"
        case .openSettings: return "open Settings on my phone"
        }
    }
}

@MainActor
private enum VexVoicePhoneExecutor {
    static func perform(_ original: String) async -> VexVoiceActionResult {
        let lower = normalize(original)

        if lower.contains("brightness") {
            guard let percent = firstNumber(in: lower) else { return .needsValue }
            let target = CGFloat(max(0, min(100, percent)) / 100.0)
            UIScreen.main.brightness = target
            try? await Task.sleep(nanoseconds: 150_000_000)
            return abs(UIScreen.main.brightness - target) <= 0.02 ? .completed : .failed
        }

        if lower.contains("flashlight") || lower.contains("torch") {
            return .systemShortcutRequired
        }

        if lower.contains("clipboard") && (lower.contains("copy ") || lower.contains("put ")) {
            guard let payload = clipboardPayload(original) else { return .needsValue }
            UIPasteboard.general.string = payload
            return UIPasteboard.general.string == payload ? .completed : .failed
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

struct VexQuickActionIntent: AppIntent {
    static var title: LocalizedStringResource = "Vex Quick Action"
    static var description = IntentDescription("Run a common Vex iPhone action immediately.")
    static var openAppWhenRun = false

    @Parameter(title: "Action")
    var action: VexQuickAction

    static var parameterSummary: some ParameterSummary {
        Summary("Have Vex \(\.$action)")
    }

    @MainActor
    func perform() async throws -> some IntentResult & ProvidesDialog {
        switch await VexVoicePhoneExecutor.perform(action.command) {
        case .completed:
            return .result(dialog: "Done.")
        case .needsValue:
            return .result(dialog: "I need a little more detail for that.")
        case .unsupported:
            return .result(dialog: "That Vex phone action is not wired in yet.")
        case .systemShortcutRequired:
            return .result(dialog: "That system control needs the native Vex Shortcut.")
        case .failed:
            return .result(dialog: "That phone action did not complete.")
        }
    }
}

struct VexVoiceCommandIntent: AppIntent {
    // V147_AUTONOMOUS_FOREGROUND_WAKE
    static var title: LocalizedStringResource = "Ask Vex"
    static var description = IntentDescription("Give Vex a spoken iPhone command.")
    static var openAppWhenRun = true

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
        let wake = command.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        if wake == "wake and check remote relay" {
            // V149_SERIALIZED_FOREGROUND_WAKE
            UserDefaults.standard.set(true, forKey: "vex.phone.foregroundWake.pending")
            VexBackgroundAgent.shared.stopForegroundLoop()
            if UIApplication.shared.applicationState == .active {
                VexBackgroundAgent.shared.handleForegroundWake()
            }
            return .result(dialog: "Ready.")
        }

        switch await VexVoicePhoneExecutor.perform(command) {
        case .completed:
            return .result(dialog: "Done.")
        case .needsValue:
            return .result(dialog: "I need a little more detail for that command.")
        case .unsupported, .systemShortcutRequired, .failed:
            if let reply = await VexHeadlessBrain.reply(to: command) {
                return .result(dialog: IntentDialog(stringLiteral: reply))
            }
            return .result(dialog: "That command needs a phone capability I do not have yet.")
        }
    }
}

struct VexAppShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: VexQuickActionIntent(),
            phrases: [
                "\(.applicationName) \(\.$action)",
                "Hey \(.applicationName) \(\.$action)",
                "Ask \(.applicationName) to \(\.$action)",
                "Tell \(.applicationName) to \(\.$action)"
            ],
            shortTitle: "Vex Quick Action",
            systemImageName: "bolt.circle"
        )

        AppShortcut(
            intent: VexVoiceCommandIntent(),
            phrases: [
                "Ask \(.applicationName)",
                "Hey \(.applicationName)",
                "Give \(.applicationName) a command"
            ],
            shortTitle: "Ask Vex",
            systemImageName: "waveform"
        )
    }
}