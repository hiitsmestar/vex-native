#!/usr/bin/env python3
from pathlib import Path

CONTENT = Path("VexNative/ContentView.swift")
APP = Path("VexNative/VexNativeApp.swift")
MARKER = 'V132_PHONE_COMMAND_RELAY = "v0.13.2-phone-command-relay-v1"'

app = APP.read_text(encoding="utf-8")
if "challenge.protectionSpace.port == 8771" not in app:
    old = """              challenge.protectionSpace.port == 8765,
              let trust = challenge.protectionSpace.serverTrust,"""
    new = """              (challenge.protectionSpace.port == 8765 || challenge.protectionSpace.port == 8771),
              let trust = challenge.protectionSpace.serverTrust,"""
    if old not in app:
        raise SystemExit("v0.13.2 trust-port anchor missing")
    app = app.replace(old, new, 1)

if "[8765, 8771].contains(port)" not in app:
    old = """        guard url.scheme?.lowercased() == "https",
              url.port == 8765,
              let host = url.host?.lowercased()
        else { return false }"""
    new = """        guard url.scheme?.lowercased() == "https",
              let port = url.port,
              [8765, 8771].contains(port),
              let host = url.host?.lowercased()
        else { return false }"""
    if old not in app:
        raise SystemExit("v0.13.2 bridge-url anchor missing")
    app = app.replace(old, new, 1)

APP.write_text(app, encoding="utf-8")

text = CONTENT.read_text(encoding="utf-8")
if MARKER not in text:
    marker_anchor = 'private let V131_TIMEOUT_UI_HOTFIX = "v0.13.1-timeout-ui-v1"'
    if marker_anchor not in text:
        raise SystemExit("v0.13.2 version marker anchor missing")
    text = text.replace(
        marker_anchor,
        marker_anchor + '\nprivate let ' + MARKER,
        1,
    )

relay = r'''
@MainActor
private final class PhoneRemoteCommandRelay {
    static let shared = PhoneRemoteCommandRelay()

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

    private init() {}

    func run(app: AppModel) async {
        while !Task.isCancelled {
            if !app.isGenerating {
                await pollOnce(app: app)
            }
            try? await Task.sleep(nanoseconds: 2_000_000_000)
        }
    }

    private func pollOnce(app: AppModel) async {
        guard let url = relayURL(path: "/phone/next") else { return }

        var request = URLRequest(url: url)
        request.timeoutInterval = 8

        do {
            let (data, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse,
                  (200..<300).contains(http.statusCode)
            else { return }

            let envelope = try JSONDecoder().decode(NextEnvelope.self, from: data)
            guard envelope.ok, let remote = envelope.command else { return }

            let routed = phoneTargeted(remote.command)
            let before = app.profile.messages.count
            let handled = await PhoneToolRouter.tryHandle(routed, app: app)

            let resultText: String
            if handled, app.profile.messages.count > before {
                resultText = app.profile.messages.last?.content ?? "Phone action completed."
            } else if handled {
                resultText = "Phone action completed."
            } else {
                resultText = "That action is not exposed by the current iOS router."
            }

            await postResult(id: remote.id, ok: handled, result: resultText)
        } catch {
            return
        }
    }

    private func phoneTargeted(_ command: String) -> String {
        let lower = command.lowercased()
        let markers = [
            "iphone", "my phone", "the phone", "this phone",
            "on phone", "on the phone", "on my phone", "on this phone"
        ]
        if markers.contains(where: { lower.contains($0) }) {
            return command
        }
        return command + " on my phone"
    }

    private func postResult(id: String, ok: Bool, result: String) async {
        guard let url = relayURL(path: "/phone/result") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 8
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONEncoder().encode(
            ResultPayload(id: id, ok: ok, result: result)
        )
        _ = try? await VexBridgeNetworking.data(for: request)
    }

    private func relayURL(path: String) -> URL? {
        let defaults = UserDefaults.standard
        let candidates = [
            defaults.string(forKey: WebBrain.searxEndpointKey) ?? "",
            defaults.string(forKey: WebBrain.secondaryBridgeEndpointKey) ?? ""
        ]

        for raw in candidates {
            let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty,
                  let root = URL(string: trimmed),
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
'''

if "private final class PhoneRemoteCommandRelay" not in text:
    anchor = "// MARK: - Local PC image generation v0.9.4"
    if anchor not in text:
        raise SystemExit("v0.13.2 relay insertion anchor missing")
    text = text.replace(anchor, relay + "\n" + anchor, 1)

task_anchor = """        .toolbarBackground(.visible, for: .tabBar)
    }
}"""
task_new = """        .toolbarBackground(.visible, for: .tabBar)
        .task {
            await PhoneRemoteCommandRelay.shared.run(app: app)
        }
    }
}"""
if "PhoneRemoteCommandRelay.shared.run(app: app)" not in text:
    if task_anchor not in text:
        raise SystemExit("v0.13.2 root task anchor missing")
    text = text.replace(task_anchor, task_new, 1)

CONTENT.write_text(text, encoding="utf-8")

final_text = CONTENT.read_text(encoding="utf-8")
final_app = APP.read_text(encoding="utf-8")
for marker in [
    MARKER,
    "private final class PhoneRemoteCommandRelay",
    'relayURL(path: "/phone/next")',
    'relayURL(path: "/phone/result")',
    "PhoneRemoteCommandRelay.shared.run(app: app)",
    "PhoneToolRouter.tryHandle(routed, app: app)",
    "parts.port = 8771",
]:
    if marker not in final_text:
        raise SystemExit(f"v0.13.2 content invariant missing: {marker}")

for marker in [
    "challenge.protectionSpace.port == 8771",
    "[8765, 8771].contains(port)",
]:
    if marker not in final_app:
        raise SystemExit(f"v0.13.2 networking invariant missing: {marker}")

print("PASS v0.13.2 phone command relay patch")