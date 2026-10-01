#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "VexNative" / "ContentView.swift"
MARKER = 'V160_A2A_ROUTE_FALLBACK = "v0.16.0-a2a-route-fallback-v1"'

text = CONTENT.read_text(encoding="utf-8")

if MARKER in text:
    print("PASS v0.16.0 A2A route fallback already applied")
    raise SystemExit(0)

anchor = 'private let V159_IPHONE_A2A_AUTONOMY = "v0.15.9-iphone-a2a-autonomy-v1"'
if anchor not in text:
    raise SystemExit("v0.16.0 requires v0.15.9 autonomy base")
text = text.replace(anchor, anchor + "\nprivate let " + MARKER, 1)

old = r'''    private func relayURL(path: String) -> URL? {
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

    private func request(
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

new = r'''    private func relayURLs(path: String) -> [URL] {
        let defaults = UserDefaults.standard
        let candidates = [
            defaults.string(forKey: WebBrain.searxEndpointKey) ?? "",
            defaults.string(forKey: "vex.pc.cognition.lastGoodEndpoint.v1") ?? "",
            defaults.string(forKey: WebBrain.secondaryBridgeEndpointKey) ?? ""
        ]

        var seen = Set<String>()
        var urls: [URL] = []

        for raw in candidates {
            let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty,
                  let root = URL(string: trimmed),
                  VexBridgeNetworking.isBridgeURL(root),
                  var parts = URLComponents(url: root, resolvingAgainstBaseURL: false)
            else { continue }

            let host = (root.host ?? "").lowercased()
            let isPrivateLAN =
                host == "localhost" ||
                host == "127.0.0.1" ||
                host.hasPrefix("10.") ||
                host.hasPrefix("192.168.") ||
                host.hasSuffix(".local") ||
                (host.hasPrefix("172.") && {
                    let pieces = host.split(separator: ".")
                    guard pieces.count > 1, let second = Int(pieces[1]) else { return false }
                    return (16...31).contains(second)
                }())

            if isPrivateLAN {
                parts.port = 8771
            } else {
                parts.port = root.port
            }
            parts.path = path

            if let url = parts.url {
                let key = url.absoluteString
                if seen.insert(key).inserted {
                    urls.append(url)
                }
            }
        }
        return urls
    }

    private func request(
        path: String,
        method: String = "GET",
        body: [String: Any]? = nil,
        timeout: TimeInterval = 20
    ) async throws -> [String: Any] {
        let urls = relayURLs(path: path)
        guard !urls.isEmpty else { throw ClientError.noRelay }

        var lastError: Error = ClientError.noRelay

        for url in urls {
            do {
                var request = URLRequest(url: url)
                request.httpMethod = method
                request.timeoutInterval = timeout
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                if let body {
                    request.httpBody = try JSONSerialization.data(withJSONObject: body)
                }

                let (data, response) = try await VexBridgeNetworking.data(for: request)
                guard let http = response as? HTTPURLResponse else {
                    throw ClientError.badResponse
                }
                guard (200...299).contains(http.statusCode) else {
                    throw ClientError.http(http.statusCode)
                }
                guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                    throw ClientError.badResponse
                }
                return object
            } catch {
                lastError = error
                continue
            }
        }

        throw lastError
    }
'''

if old not in text:
    raise SystemExit("v0.16.0 request-routing anchor missing")

text = text.replace(old, new, 1)
CONTENT.write_text(text, encoding="utf-8")

final = CONTENT.read_text(encoding="utf-8")
for marker in [
    MARKER,
    "private func relayURLs(path: String) -> [URL]",
    'host.hasPrefix("192.168.")',
    "parts.port = 8771",
    "parts.port = root.port",
    "for url in urls",
    "lastError = error",
    'V159_IPHONE_A2A_AUTONOMY',
]:
    if marker not in final:
        raise SystemExit(f"missing v0.16.0 marker: {marker}")

print("PASS v0.16.0 A2A route fallback patch")
