#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BG = ROOT / "VexNative" / "VexBackgroundAgent.swift"

text = BG.read_text(encoding="utf-8")
if "V144_STABLE_RELAY_DISCOVERY" in text:
    print("PASS v0.14.4 stable relay discovery already applied")
    raise SystemExit(0)

text = text.replace(
    'private static let V143_ROAMING_RELAY_FALLBACK = "v0.14.3-roaming-relay-fallback-v1"',
    'private static let V143_ROAMING_RELAY_FALLBACK = "v0.14.3-roaming-relay-fallback-v1"\n'
    '    private static let V144_STABLE_RELAY_DISCOVERY = "v0.14.4-stable-relay-discovery-v1"\n'
    '    private static let remoteRelayDiscoveryKey = "vex.phone.remoteRelay.discoveredEndpoint"\n'
    '    private static let remoteRelayDiscoveryAttemptKey = "vex.phone.remoteRelay.discoveryAttemptAt"\n'
    '    private static let remoteRelayDiscoveryURL = "https://gist.githubusercontent.com/hiitsmestar/4795f38563dfc5e4349d292bdb13689f/raw/vex-relay.json"',
    1,
)

text = text.replace(
'''    static func runOnce() async -> Bool {
        guard !Task.isCancelled else { return false }
        let urls = relayURLs(path: "/phone/next")''',
'''    static func runOnce() async -> Bool {
        guard !Task.isCancelled else { return false }
        await refreshRemoteRelayDiscovery()
        let urls = relayURLs(path: "/phone/next")''',
1)

anchor = '''    private static func relayURLs(path: String) -> [URL] {
        let endpoints = VexHeadlessBrain.configuredEndpoints()
        let primaryToken = endpoints.compactMap { raw -> String? in'''

insert = '''    private struct RelayDiscoveryEnvelope: Decodable {
        let endpoint: String
    }

    private static func refreshRemoteRelayDiscovery() async {
        let defaults = UserDefaults.standard
        if let last = defaults.object(forKey: remoteRelayDiscoveryAttemptKey) as? Date,
           Date().timeIntervalSince(last) < 60 {
            return
        }
        defaults.set(Date(), forKey: remoteRelayDiscoveryAttemptKey)

        guard var components = URLComponents(string: remoteRelayDiscoveryURL) else { return }
        components.queryItems = [
            URLQueryItem(name: "v", value: String(Int(Date().timeIntervalSince1970 / 60)))
        ]
        guard let url = components.url else { return }

        var request = URLRequest(url: url)
        request.timeoutInterval = 10
        request.cachePolicy = .reloadIgnoringLocalAndRemoteCacheData
        request.setValue("no-cache", forHTTPHeaderField: "Cache-Control")
        request.setValue("VexNative/0.14.4", forHTTPHeaderField: "User-Agent")

        do {
            let (rawData, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse,
                  (200..<300).contains(http.statusCode)
            else { return }

            var data = rawData
            if data.count >= 3,
               data[data.startIndex] == 0xEF,
               data[data.index(data.startIndex, offsetBy: 1)] == 0xBB,
               data[data.index(data.startIndex, offsetBy: 2)] == 0xBF {
                data.removeFirst(3)
            }

            let envelope = try JSONDecoder().decode(RelayDiscoveryEnvelope.self, from: data)
            let value = envelope.endpoint.trimmingCharacters(in: .whitespacesAndNewlines)
            guard let discovered = URL(string: value),
                  VexBridgeNetworking.isRemoteRelayURL(discovered)
            else { return }

            defaults.set(value, forKey: remoteRelayDiscoveryKey)
            defaults.set(Date(), forKey: "vex.phone.remoteRelay.discoverySuccessAt")
        } catch {
            defaults.set(String(describing: error), forKey: "vex.phone.remoteRelay.discoveryLastError")
        }
    }

    private static func relayURLs(path: String) -> [URL] {
        let configured = VexHeadlessBrain.configuredEndpoints()
        let discovered = UserDefaults.standard.string(forKey: remoteRelayDiscoveryKey) ?? ""
        var endpoints: [String] = []
        for value in [discovered] + configured where !value.isEmpty && !endpoints.contains(value) {
            endpoints.append(value)
        }
        let primaryToken = configured.compactMap { raw -> String? in'''

if anchor not in text:
    raise SystemExit("v0.14.4 relayURLs anchor missing")
text = text.replace(anchor, insert, 1)

BG.write_text(text, encoding="utf-8")

final = BG.read_text(encoding="utf-8")
for marker in [
    "V144_STABLE_RELAY_DISCOVERY",
    "remoteRelayDiscoveryURL",
    "refreshRemoteRelayDiscovery()",
    "reloadIgnoringLocalAndRemoteCacheData",
    "vex.phone.remoteRelay.discoveredEndpoint",
    "RelayDiscoveryEnvelope",
]:
    if marker not in final:
        raise SystemExit(f"missing v0.14.4 marker: {marker}")

print("PASS v0.14.4 stable relay discovery")
