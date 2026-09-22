#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BG = ROOT / "VexNative" / "VexBackgroundAgent.swift"

text = BG.read_text(encoding="utf-8")
if "V144_GITHUB_ROAMING_BOOTSTRAP" in text:
    print("PASS v0.14.4 github roaming bootstrap already applied")
    raise SystemExit(0)

text = text.replace(
    'private static let V143_ROAMING_RELAY_FALLBACK = "v0.14.3-roaming-relay-fallback-v1"',
    'private static let V143_ROAMING_RELAY_FALLBACK = "v0.14.3-roaming-relay-fallback-v1"\n    private static let V144_GITHUB_ROAMING_BOOTSTRAP = "v0.14.4-github-roaming-bootstrap-v1"',
    1,
)

old_run = '''    static func runOnce() async -> Bool {
        guard !Task.isCancelled else { return false }
        let urls = relayURLs(path: "/phone/next")'''
new_run = '''    static func runOnce() async -> Bool {
        guard !Task.isCancelled else { return false }
        await refreshRoamingBootstrap()
        let urls = relayURLs(path: "/phone/next")'''
if old_run not in text:
    raise SystemExit("v0.14.4 runOnce anchor missing")
text = text.replace(old_run, new_run, 1)

anchor = '''    private static func relayURLs(path: String) -> [URL] {'''
insert = '''    private struct RelayBootstrap: Decodable {
        let version: Int?
        let endpoint: String
        let updated_at: String?
    }

    private static func refreshRoamingBootstrap() async {
        guard let url = URL(string: "https://raw.githubusercontent.com/hiitsmestar/vex-native/main/remote-relay.json") else {
            return
        }

        var request = URLRequest(url: url)
        request.timeoutInterval = 8
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.setValue("VexNative/0.14.4", forHTTPHeaderField: "User-Agent")

        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse,
                  (200..<300).contains(http.statusCode),
                  let decoded = try? JSONDecoder().decode(RelayBootstrap.self, from: data)
            else { return }

            let raw = decoded.endpoint.trimmingCharacters(in: .whitespacesAndNewlines)
            guard let endpoint = URL(string: raw),
                  VexBridgeNetworking.isRemoteRelayURL(endpoint)
            else { return }

            UserDefaults.standard.set(raw, forKey: "vex.web.secondaryBridgeEndpoint")
            UserDefaults.standard.set(Date(), forKey: "vex.phone.roamingBootstrap.lastUpdate")
            UserDefaults.standard.removeObject(forKey: "vex.phone.roamingBootstrap.lastError")
        } catch {
            UserDefaults.standard.set(
                String(describing: error),
                forKey: "vex.phone.roamingBootstrap.lastError"
            )
        }
    }

    private static func relayURLs(path: String) -> [URL] {'''
if anchor not in text:
    raise SystemExit("v0.14.4 relayURLs anchor missing")
text = text.replace(anchor, insert, 1)

BG.write_text(text, encoding="utf-8")

final = BG.read_text(encoding="utf-8")
for marker in [
    "V144_GITHUB_ROAMING_BOOTSTRAP",
    "refreshRoamingBootstrap()",
    "raw.githubusercontent.com/hiitsmestar/vex-native/main/remote-relay.json",
    "vex.phone.roamingBootstrap.lastUpdate",
    "isRemoteRelayURL(endpoint)",
]:
    if marker not in final:
        raise SystemExit(f"missing v0.14.4 marker: {marker}")

print("PASS v0.14.4 github roaming bootstrap patch")
