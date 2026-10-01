#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "VexNative" / "ContentView.swift"
MARKER = 'V160_A2A_ROAMING_FALLBACK = "v0.16.0-a2a-roaming-fallback-v1"'

text = CONTENT.read_text(encoding="utf-8")
if MARKER in text:
    print("PASS v0.16.0 A2A roaming fallback already applied")
    raise SystemExit(0)

anchor = 'private let V159_IPHONE_A2A_AUTONOMY = "v0.15.9-iphone-a2a-autonomy-v1"'
if anchor not in text:
    raise SystemExit("v0.16.0 requires v0.15.9")
text = text.replace(anchor, anchor + '\nprivate let ' + MARKER, 1)

old_request = '''    private func request(
        path: String,
        method: String = "GET",
        body: [String: Any]? = nil,
        timeout: TimeInterval = 20
    ) async throws -> [String: Any] {
        guard let url = relayURL(path: path) else { throw ClientError.noRelay }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = timeout
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let body {
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let (data, response) = try await VexBridgeNetworking.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw ClientError.badResponse }
        guard (200...299).contains(http.statusCode) else { throw ClientError.http(http.statusCode) }
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw ClientError.badResponse
        }
        return object
    }
'''

new_request = '''    private func request(
        path: String,
        method: String = "GET",
        body: [String: Any]? = nil,
        timeout: TimeInterval = 20
    ) async throws -> [String: Any] {
        let urls = relayURLs(path: path)
        guard !urls.isEmpty else { throw ClientError.noRelay }

        var lastError: Error = ClientError.badResponse
        for url in urls {
            var request = URLRequest(url: url)
            request.httpMethod = method
            request.timeoutInterval = timeout
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            if let body {
                request.httpBody = try JSONSerialization.data(withJSONObject: body)
            }

            do {
                let (data, response) = try await VexBridgeNetworking.data(for: request)
                guard let http = response as? HTTPURLResponse else {
                    lastError = ClientError.badResponse
                    continue
                }
                guard (200...299).contains(http.statusCode) else {
                    lastError = ClientError.http(http.statusCode)
                    continue
                }
                guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                    lastError = ClientError.badResponse
                    continue
                }
                return object
            } catch {
                lastError = error
            }
        }
        throw lastError
    }
'''

if old_request not in text:
    raise SystemExit("v0.16.0 request anchor missing")
text = text.replace(old_request, new_request, 1)

old_relay = '''    private func relayURL(path: String) -> URL? {
        let defaults = UserDefaults.standard
        let candidates = [
            defaults.string(forKey: WebBrain.searxEndpointKey) ?? "",
            defaults.string(forKey: "vex.pc.cognition.lastGoodEndpoint.v1") ?? "",
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
'''

new_relay = '''    private func relayURLs(path: String) -> [URL] {
        let defaults = UserDefaults.standard
        let primary = defaults.string(forKey: WebBrain.searxEndpointKey) ?? ""
        let cognition = defaults.string(forKey: "vex.pc.cognition.lastGoodEndpoint.v1") ?? ""
        let secondary = defaults.string(forKey: WebBrain.secondaryBridgeEndpointKey) ?? ""
        let discovered = defaults.string(forKey: "vex.phone.remoteRelay.discoveredEndpoint") ?? ""

        let primaryToken = [primary, cognition, secondary].compactMap { raw -> String? in
            guard let root = URL(string: raw),
                  let parts = URLComponents(url: root, resolvingAgainstBaseURL: false)
            else { return nil }
            return parts.queryItems?.first(where: { $0.name.lowercased() == "token" })?.value
        }.first

        var ordered: [String] = []
        for raw in [discovered, secondary, primary, cognition] {
            let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            if !trimmed.isEmpty && !ordered.contains(trimmed) {
                ordered.append(trimmed)
            }
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
    }
'''

if old_relay not in text:
    raise SystemExit("v0.16.0 relay anchor missing")
text = text.replace(old_relay, new_relay, 1)

CONTENT.write_text(text, encoding="utf-8")

final = CONTENT.read_text(encoding="utf-8")
for marker in [
    MARKER,
    "private func relayURLs(path:",
    '"vex.phone.remoteRelay.discoveredEndpoint"',
    "isRemoteRelayURL",
    "parts.port = 8771",
    "parts.port = nil",
    "let urls = relayURLs(path: path)",
    'V159_IPHONE_A2A_AUTONOMY',
]:
    if marker not in final:
        raise SystemExit(f"missing v0.16.0 marker: {marker}")

print("PASS v0.16.0 A2A roaming fallback patch")
