#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BG = ROOT / "VexNative" / "VexBackgroundAgent.swift"
CONTENT = ROOT / "VexNative" / "ContentView.swift"

bg = BG.read_text(encoding="utf-8")
content = CONTENT.read_text(encoding="utf-8")

if "V143_ROAMING_RELAY_FALLBACK" in bg and "V143_ROAMING_RELAY_FALLBACK" in content:
    print("PASS v0.14.3 roaming relay fallback already applied")
    raise SystemExit(0)

old_run = r'''    static func runOnce() async -> Bool {
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
    }'''

new_run = r'''    private static let V143_ROAMING_RELAY_FALLBACK = "v0.14.3-roaming-relay-fallback-v1"

    static func runOnce() async -> Bool {
        guard !Task.isCancelled else { return false }
        let urls = relayURLs(path: "/phone/next")
        guard !urls.isEmpty else { return false }

        var lastError = "no relay succeeded"
        for url in urls {
            guard !Task.isCancelled else { return false }
            var request = URLRequest(url: url)
            request.timeoutInterval = 12

            do {
                let (data, response) = try await VexBridgeNetworking.data(for: request)
                guard let http = response as? HTTPURLResponse,
                      (200..<300).contains(http.statusCode)
                else {
                    lastError = "relay returned a non-success status"
                    continue
                }

                let envelope = try JSONDecoder().decode(NextEnvelope.self, from: data)
                guard envelope.ok else {
                    lastError = "relay returned ok=false"
                    continue
                }
                guard let remote = envelope.command else {
                    UserDefaults.standard.set(Date(), forKey: "vex.phone.background.lastRun")
                    return true
                }

                let outcome = await execute(remote.command)
                await postResult(id: remote.id, ok: outcome.ok, result: outcome.result)
                UserDefaults.standard.set(Date(), forKey: "vex.phone.background.lastRun")
                return outcome.ok
            } catch {
                lastError = String(describing: error)
                continue
            }
        }

        UserDefaults.standard.set(lastError, forKey: "vex.phone.background.lastError")
        return false
    }'''

if old_run not in bg:
    raise SystemExit("v0.14.3 runOnce anchor missing")
bg = bg.replace(old_run, new_run, 1)

old_post = r'''    private static func postResult(id: String, ok: Bool, result: String) async {
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
    }'''

new_post = r'''    private static func postResult(id: String, ok: Bool, result: String) async {
        for url in relayURLs(path: "/phone/result") {
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.timeoutInterval = 12
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try? JSONEncoder().encode(
                ResultPayload(id: id, ok: ok, result: result)
            )
            do {
                let (_, response) = try await VexBridgeNetworking.data(for: request)
                if let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) {
                    return
                }
            } catch {
                continue
            }
        }
    }

    private static func relayURLs(path: String) -> [URL] {
        let endpoints = VexHeadlessBrain.configuredEndpoints()
        let primaryToken = endpoints.compactMap { raw -> String? in
            guard let url = URL(string: raw),
                  let parts = URLComponents(url: url, resolvingAgainstBaseURL: false)
            else { return nil }
            return parts.queryItems?.first(where: { $0.name.lowercased() == "token" })?.value
        }.first

        let ordered = endpoints.sorted { lhs, rhs in
            let l = URL(string: lhs).map(VexBridgeNetworking.isRemoteRelayURL) ?? false
            let r = URL(string: rhs).map(VexBridgeNetworking.isRemoteRelayURL) ?? false
            return l && !r
        }

        var urls: [URL] = []
        for raw in ordered {
            guard let root = URL(string: raw),
                  VexBridgeNetworking.isBridgeURL(root),
                  var parts = URLComponents(url: root, resolvingAgainstBaseURL: false)
            else { continue }

            if VexBridgeNetworking.isRemoteRelayURL(root) {
                parts.port = nil
                var items = parts.queryItems ?? []
                if items.first(where: { $0.name.lowercased() == "token" }) == nil,
                   let primaryToken, !primaryToken.isEmpty {
                    items.append(URLQueryItem(name: "token", value: primaryToken))
                }
                parts.queryItems = items
            } else {
                parts.port = 8771
            }
            parts.path = path
            if let url = parts.url, !urls.contains(url) {
                urls.append(url)
            }
        }
        return urls
    }'''

if old_post not in bg:
    raise SystemExit("v0.14.3 post/relay anchor missing")
bg = bg.replace(old_post, new_post, 1)

old_content = r'''        let candidates = [
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

            if VexBridgeNetworking.isRemoteRelayURL(root) {
                parts.port = nil
            } else {
                parts.port = 8771
            }
            parts.path = path
            return parts.url
        }
        return nil'''

new_content = r'''        let primary = defaults.string(forKey: WebBrain.searxEndpointKey) ?? ""
        let secondary = defaults.string(forKey: WebBrain.secondaryBridgeEndpointKey) ?? ""
        let primaryToken = [primary, secondary].compactMap { raw -> String? in
            guard let url = URL(string: raw),
                  let parts = URLComponents(url: url, resolvingAgainstBaseURL: false)
            else { return nil }
            return parts.queryItems?.first(where: { $0.name.lowercased() == "token" })?.value
        }.first

        let candidates = [primary, secondary].sorted { lhs, rhs in
            let l = URL(string: lhs).map(VexBridgeNetworking.isRemoteRelayURL) ?? false
            let r = URL(string: rhs).map(VexBridgeNetworking.isRemoteRelayURL) ?? false
            return l && !r
        }

        for raw in candidates {
            let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty,
                  let root = URL(string: trimmed),
                  VexBridgeNetworking.isBridgeURL(root),
                  var parts = URLComponents(url: root, resolvingAgainstBaseURL: false)
            else { continue }

            if VexBridgeNetworking.isRemoteRelayURL(root) {
                parts.port = nil
                var items = parts.queryItems ?? []
                if items.first(where: { $0.name.lowercased() == "token" }) == nil,
                   let primaryToken, !primaryToken.isEmpty {
                    items.append(URLQueryItem(name: "token", value: primaryToken))
                }
                parts.queryItems = items
            } else {
                parts.port = 8771
            }
            parts.path = path
            return parts.url
        }
        return nil'''

if old_content not in content:
    raise SystemExit("v0.14.3 ContentView relay anchor missing")
content = content.replace(old_content, new_content, 1)

content = content.replace(
    'private let V142_REMOTE_ROAMING_RELAY = "v0.14.2-remote-roaming-relay-v1"',
    'private let V142_REMOTE_ROAMING_RELAY = "v0.14.2-remote-roaming-relay-v1"\nprivate let V143_ROAMING_RELAY_FALLBACK = "v0.14.3-roaming-relay-fallback-v1"',
    1,
)

BG.write_text(bg, encoding="utf-8")
CONTENT.write_text(content, encoding="utf-8")

for p, markers in [
    (BG, ["V143_ROAMING_RELAY_FALLBACK", "relayURLs(path:", "isRemoteRelayURL", "primaryToken", "parts.port = nil"]),
    (CONTENT, ["V143_ROAMING_RELAY_FALLBACK", "primaryToken", "isRemoteRelayURL", "parts.port = nil"]),
]:
    final = p.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in final:
            raise SystemExit(f"missing v0.14.3 marker {marker} in {p.name}")

print("PASS v0.14.3 roaming relay fallback")
