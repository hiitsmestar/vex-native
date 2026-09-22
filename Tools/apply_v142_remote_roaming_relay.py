#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "VexNative" / "VexNativeApp.swift"
CONTENT = ROOT / "VexNative" / "ContentView.swift"

app = APP.read_text(encoding="utf-8")
content = CONTENT.read_text(encoding="utf-8")

if "V142_REMOTE_ROAMING_RELAY" in app and "V142_REMOTE_ROAMING_RELAY" in content:
    print("PASS v0.14.2 roaming relay already applied")
    raise SystemExit(0)

old_data = '''    static func data(for request: URLRequest) async throws -> (Data, URLResponse) {
        guard let url = request.url, isBridgeURL(url) else {
            return try await URLSession.shared.data(for: request)
        }

        guard let rawPin = certificatePin(in: url) else {
            throw VexBridgeNetworkingError.missingCertificatePin
        }'''
new_data = '''    private static let V142_REMOTE_ROAMING_RELAY = "v0.14.2-remote-roaming-relay-v1"

    static func data(for request: URLRequest) async throws -> (Data, URLResponse) {
        guard let url = request.url else {
            return try await URLSession.shared.data(for: request)
        }

        // Public roaming relay uses normal CA-backed HTTPS. Only the private
        // LAN bridge uses our out-of-band self-signed certificate pin.
        if isRemoteRelayURL(url) {
            return try await URLSession.shared.data(for: request)
        }

        guard isPrivateBridgeURL(url) else {
            return try await URLSession.shared.data(for: request)
        }

        guard let rawPin = certificatePin(in: url) else {
            throw VexBridgeNetworkingError.missingCertificatePin
        }'''
if old_data not in app:
    raise SystemExit("v0.14.2 networking data anchor missing")
app = app.replace(old_data, new_data, 1)

old_bridge = '''    static func isBridgeURL(_ url: URL) -> Bool {
        guard url.scheme?.lowercased() == "https",
              let port = url.port,
              [8765, 8771].contains(port),
              let host = url.host?.lowercased()
        else { return false }
        return isPrivateLANHost(host)
    }

    static func isPrivateLANHost(_ host: String) -> Bool {'''
new_bridge = '''    static func isBridgeURL(_ url: URL) -> Bool {
        isPrivateBridgeURL(url) || isRemoteRelayURL(url)
    }

    static func isPrivateBridgeURL(_ url: URL) -> Bool {
        guard url.scheme?.lowercased() == "https",
              let port = url.port,
              [8765, 8771].contains(port),
              let host = url.host?.lowercased()
        else { return false }
        return isPrivateLANHost(host)
    }

    static func isRemoteRelayURL(_ url: URL) -> Bool {
        guard url.scheme?.lowercased() == "https",
              let host = url.host?.lowercased(),
              host.hasSuffix(".trycloudflare.com")
        else { return false }
        return url.port == nil || url.port == 443
    }

    static func isPrivateLANHost(_ host: String) -> Bool {'''
if old_bridge not in app:
    raise SystemExit("v0.14.2 bridge validator anchor missing")
app = app.replace(old_bridge, new_bridge, 1)

old_relay = '''            parts.port = 8771
            parts.path = path
            return parts.url'''
new_relay = '''            if VexBridgeNetworking.isRemoteRelayURL(root) {
                parts.port = nil
            } else {
                parts.port = 8771
            }
            parts.path = path
            return parts.url'''
if old_relay not in content:
    raise SystemExit("v0.14.2 relay URL anchor missing")
content = content.replace(old_relay, new_relay, 1)

# Marker in ContentView too, so assembly verification catches stale output.
marker_anchor = '// MARK: - Local PC image generation v0.9.4'
if marker_anchor not in content:
    raise SystemExit("v0.14.2 marker anchor missing")
content = content.replace(
    marker_anchor,
    'private let V142_REMOTE_ROAMING_RELAY = "v0.14.2-remote-roaming-relay-v1"\n\n' + marker_anchor,
    1,
)

APP.write_text(app, encoding="utf-8")
CONTENT.write_text(content, encoding="utf-8")

for path, markers in [
    (APP, ["V142_REMOTE_ROAMING_RELAY", "isRemoteRelayURL", "isPrivateBridgeURL", ".trycloudflare.com"]),
    (CONTENT, ["V142_REMOTE_ROAMING_RELAY", "isRemoteRelayURL(root)", "parts.port = nil", "parts.port = 8771"]),
]:
    final = path.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in final:
            raise SystemExit(f"v0.14.2 marker missing in {path.name}: {marker}")

print("PASS v0.14.2 remote roaming relay patch")
