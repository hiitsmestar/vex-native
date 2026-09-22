#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "VexNative" / "VexNativeApp.swift"
CONTENT = ROOT / "VexNative" / "ContentView.swift"
VOICE = ROOT / "VexNative" / "VexVoiceIntents.swift"
BG = ROOT / "VexNative" / "VexBackgroundAgent.swift"
PBX = ROOT / "VexNative.xcodeproj" / "project.pbxproj"

bg_source = r'''import BackgroundTasks
import Foundation
import UIKit

final class VexAppDelegate: NSObject, UIApplicationDelegate {
    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        VexBackgroundAgent.shared.register()
        VexBackgroundAgent.shared.schedule()
        return true
    }

    func applicationDidEnterBackground(_ application: UIApplication) {
        VexBackgroundAgent.shared.schedule()
    }
}

final class VexBackgroundAgent {
    static let shared = VexBackgroundAgent()
    static let refreshIdentifier = "local.star.vexnative.background.refresh"
    static let processingIdentifier = "local.star.vexnative.background.processing"

    private var registered = false
    private init() {}

    func register() {
        guard !registered else { return }
        registered = true

        BGTaskScheduler.shared.register(
            forTaskWithIdentifier: Self.refreshIdentifier,
            using: nil
        ) { task in
            guard let task = task as? BGAppRefreshTask else {
                task.setTaskCompleted(success: false)
                return
            }
            self.handle(task)
        }

        BGTaskScheduler.shared.register(
            forTaskWithIdentifier: Self.processingIdentifier,
            using: nil
        ) { task in
            guard let task = task as? BGProcessingTask else {
                task.setTaskCompleted(success: false)
                return
            }
            self.handle(task)
        }
    }

    func schedule() {
        let refresh = BGAppRefreshTaskRequest(identifier: Self.refreshIdentifier)
        refresh.earliestBeginDate = Date(timeIntervalSinceNow: 15 * 60)
        try? BGTaskScheduler.shared.submit(refresh)

        let processing = BGProcessingTaskRequest(identifier: Self.processingIdentifier)
        processing.earliestBeginDate = Date(timeIntervalSinceNow: 20 * 60)
        processing.requiresNetworkConnectivity = true
        processing.requiresExternalPower = false
        try? BGTaskScheduler.shared.submit(processing)
    }

    private func handle(_ backgroundTask: BGTask) {
        schedule()
        let work = Task {
            let ok = await VexPhoneBackgroundWorker.runOnce()
            backgroundTask.setTaskCompleted(success: ok)
        }
        backgroundTask.expirationHandler = {
            work.cancel()
        }
    }
}

enum VexPhoneBackgroundWorker {
    private struct RemoteCommand: Decodable {
        let id: String
        let command: String
    }

    private struct NextEnvelope: Decodable {
        let ok: Bool
        let command: RemoteCommand?
    }

    private struct ResultPayload: Encodable {
        let id: String
        let ok: Bool
        let result: String
    }

    static func runOnce() async -> Bool {
        guard !Task.isCancelled else { return false }
        guard let url = relayURL(path: "/phone/next") else { return false }

        var request = URLRequest(url: url)
        request.timeoutInterval = 12

        do {
            let (data, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse,
                  (200..<300).contains(http.statusCode)
            else { return false }

            let envelope = try JSONDecoder().decode(NextEnvelope.self, from: data)
            guard envelope.ok else { return false }
            guard let remote = envelope.command else { return true }

            let outcome = await execute(remote.command)
            await postResult(id: remote.id, ok: outcome.ok, result: outcome.result)
            UserDefaults.standard.set(Date(), forKey: "vex.phone.background.lastRun")
            return outcome.ok
        } catch {
            UserDefaults.standard.set(String(describing: error), forKey: "vex.phone.background.lastError")
            return false
        }
    }

    @MainActor
    private static func execute(_ command: String) async -> (ok: Bool, result: String) {
        let app = AppModel()
        let targeted = phoneTargeted(command)
        let before = app.profile.messages.count
        let handled = await PhoneToolRouter.tryHandle(targeted, app: app)

        if handled {
            let result = app.profile.messages.count > before
                ? (app.profile.messages.last?.content ?? "Phone action completed.")
                : "Phone action completed."
            return (true, result)
        }

        if let reply = await VexHeadlessBrain.reply(to: command) {
            return (true, reply)
        }

        return (false, "No current phone capability completed that command.")
    }

    private static func phoneTargeted(_ command: String) -> String {
        let lower = command.lowercased()
        let markers = [
            "iphone", "my phone", "the phone", "this phone",
            "on phone", "on the phone", "on my phone", "on this phone"
        ]
        return markers.contains(where: { lower.contains($0) })
            ? command
            : command + " on my phone"
    }

    private static func postResult(id: String, ok: Bool, result: String) async {
        guard let url = relayURL(path: "/phone/result") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 12
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONEncoder().encode(
            ResultPayload(id: id, ok: ok, result: result)
        )
        _ = try? await VexBridgeNetworking.data(for: request)
    }

    private static func relayURL(path: String) -> URL? {
        for raw in VexHeadlessBrain.configuredEndpoints() {
            guard let root = URL(string: raw),
                  VexBridgeNetworking.isBridgeURL(root),
                  var parts = URLComponents(url: root, resolvingAgainstBaseURL: false)
            else { continue }
            parts.port = 8771
            parts.path = path
            return parts.url
        }
        return nil
    }
}

enum VexHeadlessBrain {
    private struct OverlayReply: Decodable {
        let ok: Bool
        let reply: String?
    }

    static func configuredEndpoints() -> [String] {
        let defaults = UserDefaults.standard
        let primary = defaults.string(forKey: "vex.web.searxngEndpoint") ?? ""
        let secondary = defaults.string(forKey: "vex.web.secondaryBridgeEndpoint") ?? ""
        var endpoints: [String] = []
        if !primary.isEmpty { endpoints.append(primary) }
        if !secondary.isEmpty, secondary != primary { endpoints.append(secondary) }
        return endpoints
    }

    static func reply(to command: String) async -> String? {
        for endpoint in configuredEndpoints() {
            guard let root = URL(string: endpoint),
                  var parts = URLComponents(url: root, resolvingAgainstBaseURL: false)
            else { continue }
            parts.path = "/llm/chat"
            guard let url = parts.url else { continue }

            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.timeoutInterval = 90
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            let body: [String: Any] = [
                "message": String(command.prefix(5000)),
                "history": [],
                "persona": "",
                "user_profile": "",
                "state": ["mode": "iphone-background-agent"]
            ]
            request.httpBody = try? JSONSerialization.data(withJSONObject: body)

            do {
                let (data, response) = try await VexBridgeNetworking.data(for: request)
                guard let http = response as? HTTPURLResponse,
                      (200...299).contains(http.statusCode),
                      let decoded = try? JSONDecoder().decode(OverlayReply.self, from: data),
                      decoded.ok,
                      let reply = decoded.reply?.trimmingCharacters(in: .whitespacesAndNewlines),
                      !reply.isEmpty
                else { continue }
                return reply
            } catch {
                continue
            }
        }
        return nil
    }
}
'''
BG.write_text(bg_source, encoding="utf-8")

content = CONTENT.read_text(encoding="utf-8")
content = content.replace(
    "@MainActor\nprivate enum PhoneToolRouter {",
    "@MainActor\nenum PhoneToolRouter {",
    1
)
if "@MainActor\nenum PhoneToolRouter {" not in content:
    raise SystemExit("v0.13.8 PhoneToolRouter visibility anchor missing")
CONTENT.write_text(content, encoding="utf-8")

app = APP.read_text(encoding="utf-8")
old = '''@main
struct VexNativeApp: App {
    @StateObject private var appModel = AppModel()
'''
new = '''@main
struct VexNativeApp: App {
    @UIApplicationDelegateAdaptor(VexAppDelegate.self) private var appDelegate
    @StateObject private var appModel = AppModel()
'''
if "@UIApplicationDelegateAdaptor(VexAppDelegate.self)" not in app:
    if old not in app:
        raise SystemExit("v0.13.8 App delegate anchor missing")
    app = app.replace(old, new, 1)
APP.write_text(app, encoding="utf-8")

voice = VOICE.read_text(encoding="utf-8")
voice = voice.replace("static var openAppWhenRun = false", "static var openAppWhenRun = false")
old_perform = '''    @MainActor
    func perform() async throws -> some IntentResult & ProvidesDialog {
        switch await VexVoicePhoneExecutor.perform(command) {
        case .completed:
            return .result(dialog: "Done.")
        case .needsValue:
            return .result(dialog: "I need a little more detail for that command.")
        case .unsupported:
            return .result(dialog: "That Vex phone action is not wired in yet.")
        case .systemShortcutRequired:
            return .result(dialog: "That system control needs the native Vex Shortcut.")
        case .failed:
            return .result(dialog: "That phone action did not complete.")
        }
    }'''
new_perform = '''    @MainActor
    func perform() async throws -> some IntentResult & ProvidesDialog {
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
    }'''
if old_perform not in voice:
    raise SystemExit("v0.13.8 voice intent anchor missing")
voice = voice.replace(old_perform, new_perform, 1)
VOICE.write_text(voice, encoding="utf-8")

pbx = PBX.read_text(encoding="utf-8")
if "VexBackgroundAgent.swift in Sources" not in pbx:
    a = 'A000000000000000000004B /* VexVoiceIntents.swift in Sources */ = {isa = PBXBuildFile; fileRef = A000000000000000000002B /* VexVoiceIntents.swift */; };'
    b = a + '\n\t\tA000000000000000000004C /* VexBackgroundAgent.swift in Sources */ = {isa = PBXBuildFile; fileRef = A000000000000000000002C /* VexBackgroundAgent.swift */; };'
    if a not in pbx:
        raise SystemExit("v0.13.8 PBX build anchor missing")
    pbx = pbx.replace(a, b, 1)

    a = 'A000000000000000000002B /* VexVoiceIntents.swift */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = VexVoiceIntents.swift; sourceTree = "<group>"; };'
    b = a + '\n\t\tA000000000000000000002C /* VexBackgroundAgent.swift */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = VexBackgroundAgent.swift; sourceTree = "<group>"; };'
    if a not in pbx:
        raise SystemExit("v0.13.8 PBX ref anchor missing")
    pbx = pbx.replace(a, b, 1)

    a = '\t\t\t\tA000000000000000000002B /* VexVoiceIntents.swift */,'
    b = a + '\n\t\t\t\tA000000000000000000002C /* VexBackgroundAgent.swift */,'
    if a not in pbx:
        raise SystemExit("v0.13.8 PBX group anchor missing")
    pbx = pbx.replace(a, b, 1)

    a = '\t\t\t\tA000000000000000000004B /* VexVoiceIntents.swift in Sources */,'
    b = a + '\n\t\t\t\tA000000000000000000004C /* VexBackgroundAgent.swift in Sources */,'
    if a not in pbx:
        raise SystemExit("v0.13.8 PBX sources anchor missing")
    pbx = pbx.replace(a, b, 1)

PBX.write_text(pbx, encoding="utf-8")

for marker in [
    "BGTaskScheduler.shared.register",
    "VexPhoneBackgroundWorker.runOnce",
    "VexHeadlessBrain.reply",
    'parts.port = 8771',
]:
    if marker not in BG.read_text(encoding="utf-8"):
        raise SystemExit(f"v0.13.8 background marker missing: {marker}")

if "@UIApplicationDelegateAdaptor(VexAppDelegate.self)" not in APP.read_text(encoding="utf-8"):
    raise SystemExit("v0.13.8 App delegate wiring missing")
if "VexBackgroundAgent.swift in Sources" not in PBX.read_text(encoding="utf-8"):
    raise SystemExit("v0.13.8 Xcode source wiring missing")
if "VexHeadlessBrain.reply(to: command)" not in VOICE.read_text(encoding="utf-8"):
    raise SystemExit("v0.13.8 Siri headless brain wiring missing")

print("PASS v0.13.8 background agent foundation patch")
