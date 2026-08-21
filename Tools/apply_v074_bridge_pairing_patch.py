#!/usr/bin/env python3
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"{label}: expected source block not found")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# iPhone: certificate-pinned private-LAN Vex Bridge transport
# ---------------------------------------------------------------------------
app_path = Path("VexNative/VexNativeApp.swift")
app = app_path.read_text(encoding="utf-8")

app = app.replace(
    "import Foundation\nimport SwiftUI\n",
    "import CryptoKit\nimport Foundation\nimport Security\nimport SwiftUI\n",
    1,
)

start_marker = "/// Dedicated LAN transport for Vex Bridge."
end_marker = "@main\nstruct VexNativeApp: App {"
start = app.find(start_marker)
end = app.find(end_marker)
if start < 0 or end < 0 or end <= start:
    raise SystemExit("VexNativeApp.swift: bridge transport markers not found")

secure_transport = r'''/// Dedicated LAN transport for Vex Bridge.
///
/// The bridge uses a per-install self-signed certificate, so normal iOS trust
/// correctly rejects it. Pairing therefore pins the exact leaf certificate
/// SHA-256 fingerprint printed by VexBridge.exe. Only HTTPS requests to a
/// private-LAN host on the dedicated bridge port can use this path. Public HTTPS
/// stays on URLSession.shared and normal system certificate validation.
enum VexBridgeNetworkingError: LocalizedError {
    case missingCertificatePin
    case invalidCertificatePin
    case certificateMismatch

    var errorDescription: String? {
        switch self {
        case .missingCertificatePin:
            return "Vex Bridge pairing is missing its certificate pin. Run the latest VexBridge.exe and paste the entire endpoint it prints."
        case .invalidCertificatePin:
            return "The Vex Bridge certificate pin is malformed. Paste the entire pairing endpoint from the PC again."
        case .certificateMismatch:
            return "The Vex Bridge certificate does not match this pairing. Paste the latest full endpoint from the PC before trying again."
        }
    }
}

final class VexBridgeTrustDelegate: NSObject, URLSessionDelegate {
    private let expectedFingerprint: Data
    private(set) var sawPinMismatch = false

    init(expectedFingerprint: Data) {
        self.expectedFingerprint = expectedFingerprint
    }

    func urlSession(
        _ session: URLSession,
        didReceive challenge: URLAuthenticationChallenge,
        completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
    ) {
        guard challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust,
              challenge.protectionSpace.port == 8765,
              let trust = challenge.protectionSpace.serverTrust,
              VexBridgeNetworking.isPrivateLANHost(challenge.protectionSpace.host.lowercased()),
              let certificate = SecTrustGetCertificateAtIndex(trust, 0)
        else {
            completionHandler(.performDefaultHandling, nil)
            return
        }

        let certificateData = SecCertificateCopyData(certificate) as Data
        let actualFingerprint = Data(SHA256.hash(data: certificateData))
        guard actualFingerprint == expectedFingerprint else {
            sawPinMismatch = true
            completionHandler(.cancelAuthenticationChallenge, nil)
            return
        }

        // We deliberately accept this otherwise-untrusted self-signed certificate
        // only after its exact leaf fingerprint matches the out-of-band pairing pin.
        completionHandler(.useCredential, URLCredential(trust: trust))
    }
}

enum VexBridgeNetworking {
    static func data(for request: URLRequest) async throws -> (Data, URLResponse) {
        guard let url = request.url, isBridgeURL(url) else {
            return try await URLSession.shared.data(for: request)
        }

        guard let rawPin = certificatePin(in: url) else {
            throw VexBridgeNetworkingError.missingCertificatePin
        }
        guard let fingerprint = decodeFingerprint(rawPin) else {
            throw VexBridgeNetworkingError.invalidCertificatePin
        }

        var bridgeRequest = request
        bridgeRequest.url = strippingPin(from: url)

        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 18
        configuration.timeoutIntervalForResource = 24
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        configuration.protocolClasses = []

        let delegate = VexBridgeTrustDelegate(expectedFingerprint: fingerprint)
        let session = URLSession(configuration: configuration, delegate: delegate, delegateQueue: nil)
        defer { session.finishTasksAndInvalidate() }

        do {
            return try await session.data(for: bridgeRequest)
        } catch {
            if delegate.sawPinMismatch {
                throw VexBridgeNetworkingError.certificateMismatch
            }
            throw error
        }
    }

    static func isBridgeURL(_ url: URL) -> Bool {
        guard url.scheme?.lowercased() == "https",
              url.port == 8765,
              let host = url.host?.lowercased()
        else { return false }
        return isPrivateLANHost(host)
    }

    static func isPrivateLANHost(_ host: String) -> Bool {
        if host.hasSuffix(".local") { return true }
        if host.hasPrefix("10.") || host.hasPrefix("192.168.") || host.hasPrefix("169.254.") {
            return true
        }
        let parts = host.split(separator: ".").compactMap { Int($0) }
        return parts.count == 4 && parts[0] == 172 && (16...31).contains(parts[1])
    }

    private static func certificatePin(in url: URL) -> String? {
        guard let components = URLComponents(url: url, resolvingAgainstBaseURL: false) else { return nil }
        return components.queryItems?
            .first(where: { $0.name.lowercased() == "pin" })?
            .value
    }

    private static func strippingPin(from url: URL) -> URL? {
        guard var components = URLComponents(url: url, resolvingAgainstBaseURL: false) else { return url }
        components.queryItems = components.queryItems?.filter { $0.name.lowercased() != "pin" }
        return components.url
    }

    private static func decodeFingerprint(_ raw: String) -> Data? {
        let normalized = raw
            .lowercased()
            .replacingOccurrences(of: ":", with: "")
            .replacingOccurrences(of: "-", with: "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard normalized.count == 64 else { return nil }

        var bytes = Data(capacity: 32)
        var index = normalized.startIndex
        for _ in 0..<32 {
            let next = normalized.index(index, offsetBy: 2)
            guard let byte = UInt8(normalized[index..<next], radix: 16) else { return nil }
            bytes.append(byte)
            index = next
        }
        return bytes
    }
}

'''
app = app[:start] + secure_transport + app[end:]
app_path.write_text(app, encoding="utf-8")


# ---------------------------------------------------------------------------
# iPhone: Web Brain routing, retries, troubleshooting discipline
# ---------------------------------------------------------------------------
content_path = Path("VexNative/ContentView.swift")
text = content_path.read_text(encoding="utf-8")

needle = "let (data, response) = try await URLSession.shared.data(for: request)"
count = text.count(needle)
if count < 3:
    raise SystemExit(f"ContentView.swift: expected at least 3 URLSession.shared data calls, found {count}")
text = text.replace(needle, "let (data, response) = try await VexBridgeNetworking.data(for: request)")

old_should = '''        if firstPublicURL(in: text) != nil { return true }\n        if isExplicitWebRequest(lower) { return true }\n        guard autoFreshEnabled else { return false }\n\n        let questionish = lower.contains("?") || [\n            "what ", "who ", "when ", "where ", "how ", "is ", "are ", "did ", "does ", "can "\n        ].contains(where: { lower.hasPrefix($0) })\n\n        let freshness = containsWholePhrase(lower, "latest") ||\n'''
new_should = '''        if firstPublicURL(in: text) != nil { return true }\n        if isBridgeRetryRequest(lower) { return true }\n        if isExplicitWebRequest(lower) { return true }\n        guard autoFreshEnabled else { return false }\n\n        let questionish = lower.contains("?") || [\n            "what ", "who ", "when ", "where ", "how ", "is ", "are ", "did ", "does ", "can ", "why "\n        ].contains(where: { lower.hasPrefix($0) })\n\n        if questionish && needsGeneralSearch(text) { return true }\n\n        let freshness = containsWholePhrase(lower, "latest") ||\n'''
text = replace_once(text, old_should, new_should, "shouldUseWeb")

old_triggers = '''            "research ", "learn about ", "study ", "read this url", "read this page"\n'''
new_triggers = '''            "research ", "learn about ", "study ", "read this url", "read this page",\n            "use my computer", "use the computer", "through my computer", "through the computer",\n            "try through my computer", "try through the computer", "try the bridge", "use the bridge",\n            "check my computer", "search my computer", "look on my computer", "look through my computer",\n            "i granted you access", "granted you access"\n'''
text = replace_once(text, old_triggers, new_triggers, "explicit web triggers")

old_query = '''        let query = cleanedQuery(from: text)\n        let cacheKey = query.lowercased()\n'''
new_query = '''        let normalizedRequest = normalize(text)\n        let query: String\n        if isBridgeRetryRequest(normalizedRequest), !lastQuery.isEmpty {\n            query = lastQuery\n        } else {\n            query = cleanedQuery(from: text)\n        }\n        let cacheKey = query.lowercased()\n'''
text = replace_once(text, old_query, new_query, "research retry query")

old_endpoint_fallback = '''                let searxResults = try await searchSearXNG(query: query, endpoint: endpoint)\n                if !searxResults.isEmpty {\n                    sources = searxResults\n                } else if wikipediaEnabled {\n                    status = "Trying Wikipedia…"\n                    sources = try await searchWikipedia(query: query)\n                } else {\n                    throw WebBrainError.noResults\n                }\n            } else if wikipediaEnabled {\n                if needsLiveGeneralSearch(text) {\n                    throw WebBrainError.generalSearchNeedsSearXNG\n                }\n'''
new_endpoint_fallback = '''                let searxResults = try await searchSearXNG(query: query, endpoint: endpoint)\n                if !searxResults.isEmpty {\n                    sources = searxResults\n                } else if wikipediaEnabled && !needsGeneralSearch(text) {\n                    status = "Trying Wikipedia…"\n                    sources = try await searchWikipedia(query: query)\n                } else {\n                    throw WebBrainError.noResults\n                }\n            } else if wikipediaEnabled {\n                if needsGeneralSearch(text) {\n                    throw WebBrainError.generalSearchNeedsSearXNG\n                }\n'''
text = replace_once(text, old_endpoint_fallback, new_endpoint_fallback, "Wikipedia troubleshooting fallback")

old_error = '            return "Live/current web search needs a SearXNG endpoint. Wikipedia is still available for encyclopedia-style research."\n'
new_error = '            return "General web/Bridge search is unavailable. Configure a Vex Bridge or SearXNG endpoint; Wikipedia is not used as a troubleshooting fallback."\n'
text = replace_once(text, old_error, new_error, "general search error text")

insert_before_learning = '''    func shouldLearnPermanently(from text: String) -> Bool {\n'''
retry_helper = '''    private func isBridgeRetryRequest(_ lower: String) -> Bool {\n        guard !lastQuery.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return false }\n        return lower.contains("try again") || lower.contains("retry") ||\n            lower.contains("try the bridge") || lower.contains("use the bridge") ||\n            lower.contains("through my computer") || lower.contains("through the computer") ||\n            lower.contains("use my computer") || lower.contains("use the computer") ||\n            lower.contains("check my computer") || lower.contains("search my computer") ||\n            lower.contains("look on my computer") || lower.contains("look through my computer") ||\n            lower.contains("granted you access")\n    }\n\n'''
if insert_before_learning not in text:
    raise SystemExit("ContentView.swift: learning function marker not found")
text = text.replace(insert_before_learning, retry_helper + insert_before_learning, 1)

old_removable = '''            "research", "learn about", "study"\n'''
new_removable = '''            "research", "learn about", "study", "use my computer", "use the computer",\n            "through my computer", "through the computer", "search my computer", "check my computer",\n            "look on my computer", "look through my computer", "try through my computer",\n            "try through the computer", "try the bridge", "use the bridge", "i granted you access"\n'''
text = replace_once(text, old_removable, new_removable, "cleaned query bridge controls")

insert_before_live = '''    private func needsLiveGeneralSearch(_ text: String) -> Bool {\n'''
general_helper = '''    private func needsGeneralSearch(_ text: String) -> Bool {\n        if needsLiveGeneralSearch(text) { return true }\n        let lower = normalize(text)\n        let troubleshooting = [\n            "troubleshoot", "repair", "broken", "not working", "stopped working",\n            "won't start", "wont start", "won't heat", "wont heat", "doesn't work",\n            "doesnt work", "error code", "fault code", "problem with", "diagnose",\n            "how do i fix", "how can i fix", "why isn't", "why isnt"\n        ]\n        return troubleshooting.contains(where: { lower.contains($0) })\n    }\n\n'''
if insert_before_live not in text:
    raise SystemExit("ContentView.swift: live-search helper marker not found")
text = text.replace(insert_before_live, general_helper + insert_before_live, 1)

content_path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# iPhone Brain UI: pairing endpoint wording
# ---------------------------------------------------------------------------
brain_path = Path("VexNative/Views/BrainView.swift")
brain = brain_path.read_text(encoding="utf-8")
brain = brain.replace('Text("SearXNG endpoint")', 'Text("Vex Bridge / SearXNG endpoint")', 1)
brain = brain.replace(
    'Text("Optional. Add an HTTPS SearXNG server with JSON search enabled for full live web search. Without one, Vex can still read public HTTPS links and use Wikipedia for encyclopedia-style research.")',
    'Text("Paste the full Vex Bridge pairing endpoint here, including its token and certificate pin, or use an HTTPS SearXNG server with JSON search enabled. Without either one, Vex can still read public HTTPS links and use Wikipedia for encyclopedia-style research.")',
    1,
)
brain_path.write_text(brain, encoding="utf-8")


# ---------------------------------------------------------------------------
# Windows bridge: persist existing cert, print its SHA-256 pin in pairing URL
# ---------------------------------------------------------------------------
bridge_path = Path("Bridge/vex_bridge.py")
bridge = bridge_path.read_text(encoding="utf-8")
bridge = bridge.replace('"""Vex Bridge v0.7', '"""Vex Bridge v0.7.4', 1)
bridge = bridge.replace('server_version = "VexBridge/0.7"', 'server_version = "VexBridge/0.7.4"', 1)
bridge = bridge.replace('"version": "0.7",', '"version": "0.7.4",', 1)
bridge = bridge.replace('"Mozilla/5.0 VexBridge/0.7"', '"Mozilla/5.0 VexBridge/0.7.4"', 1)

fingerprint_helper = '''\n\ndef certificate_fingerprint_sha256() -> str:\n    from cryptography import x509\n    from cryptography.hazmat.primitives import hashes\n\n    certificate = x509.load_pem_x509_certificate(CERT_PATH.read_bytes())\n    return certificate.fingerprint(hashes.SHA256()).hex()\n'''
marker = "\n\ndef lan_ip() -> str:\n"
if marker not in bridge:
    raise SystemExit("Bridge/vex_bridge.py: lan_ip marker not found")
bridge = bridge.replace(marker, fingerprint_helper + marker, 1)

bridge = replace_once(
    bridge,
    '''    token = config["token"]\n    endpoint = f"https://{address}:{port}?token={urllib.parse.quote(token)}"\n''',
    '''    token = config["token"]\n    fingerprint = certificate_fingerprint_sha256()\n    endpoint = f"https://{address}:{port}?token={urllib.parse.quote(token)}&pin={fingerprint}"\n''',
    "core bridge pairing endpoint",
)
bridge = replace_once(
    bridge,
    '''    print(endpoint)\n    print("\\nKeep this window open while Vex is using the bridge.")\n''',
    '''    print(endpoint)\n    print(f"Certificate pin (SHA-256): {fingerprint}")\n    print("\\nKeep this window open while Vex is using the bridge.")\n''',
    "core bridge fingerprint output",
)
bridge_path.write_text(bridge, encoding="utf-8")

full_path = Path("Bridge/vex_bridge_full.py")
full = full_path.read_text(encoding="utf-8")
full = replace_once(full, 'VERSION = "0.7.1"', 'VERSION = "0.7.4"', "full bridge version")
full = replace_once(
    full,
    '''    token = config["token"]\n    endpoint = f"https://{address}:{port}?token={urllib.parse.quote(token)}"\n''',
    '''    token = config["token"]\n    fingerprint = core.certificate_fingerprint_sha256()\n    endpoint = f"https://{address}:{port}?token={urllib.parse.quote(token)}&pin={fingerprint}"\n''',
    "full bridge pairing endpoint",
)
full = replace_once(
    full,
    '''    print(endpoint, flush=True)\n    print("\\nKeep this window open while Vex is using the bridge.", flush=True)\n''',
    '''    print(endpoint, flush=True)\n    print(f"Certificate pin (SHA-256): {fingerprint}", flush=True)\n    print("\\nKeep this window open while Vex is using the bridge.", flush=True)\n''',
    "full bridge fingerprint output",
)
full_path.write_text(full, encoding="utf-8")

print("Applied v0.7.4 certificate-pinned bridge pairing + retry/search routing patch")
print(f"Routed {count} Web Brain request call(s) through VexBridgeNetworking")
