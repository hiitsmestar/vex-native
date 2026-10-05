import CryptoKit
import AppIntents
import Foundation
import Security
import SwiftUI

/// Dedicated LAN transport for Vex Bridge.
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
              (challenge.protectionSpace.port == 8765 || challenge.protectionSpace.port == 8771),
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
    private static let V142_REMOTE_ROAMING_RELAY = "v0.14.2-remote-roaming-relay-v1"

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
        }
        guard let fingerprint = decodeFingerprint(rawPin) else {
            throw VexBridgeNetworkingError.invalidCertificatePin
        }

        var bridgeRequest = request
        bridgeRequest.url = strippingPin(from: url)

        let configuration = URLSessionConfiguration.ephemeral
        // v0.9.4.4: cognition and local rendering are intentionally long-running
        // on CPU-only PCs. The old transport-level 18/24 second limits silently
        // overrode the 90 second URLRequest timeout used by PCCognitionOverlay,
        // causing VexNative to abandon a healthy PC before Ollama returned.
        let path = bridgeRequest.url?.path.lowercased() ?? ""
        if path == "/llm/chat" || path == "/vexnative/send" {
            configuration.timeoutIntervalForRequest = 180
            configuration.timeoutIntervalForResource = 240
        } else if path.hasPrefix("/art/") {
            configuration.timeoutIntervalForRequest = 180
            configuration.timeoutIntervalForResource = 240
        } else {
            configuration.timeoutIntervalForRequest = 18
            configuration.timeoutIntervalForResource = 24
        }
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

    @MainActor
    static func streamLines(
        for request: URLRequest,
        onLine: (String) -> Void
    ) async throws -> URLResponse {
        guard let url = request.url else {
            let (bytes, response) = try await URLSession.shared.bytes(for: request)
            for try await line in bytes.lines { onLine(line) }
            return response
        }

        if isRemoteRelayURL(url) || !isPrivateBridgeURL(url) {
            let (bytes, response) = try await URLSession.shared.bytes(for: request)
            for try await line in bytes.lines { onLine(line) }
            return response
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
        // Deep/tool streams emit progress heartbeats and may legitimately outlive
        // a few minutes while a cold local model starts or durable work continues.
        // Keep the connection alive long enough for the existing 30-minute deep-job
        // budget instead of declaring a healthy Vex core offline at four minutes.
        configuration.timeoutIntervalForRequest = 300
        configuration.timeoutIntervalForResource = 1900
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        configuration.protocolClasses = []

        let delegate = VexBridgeTrustDelegate(expectedFingerprint: fingerprint)
        let session = URLSession(configuration: configuration, delegate: delegate, delegateQueue: nil)
        defer { session.finishTasksAndInvalidate() }

        do {
            let (bytes, response) = try await session.bytes(for: bridgeRequest)
            for try await line in bytes.lines { onLine(line) }
            return response
        } catch {
            if delegate.sawPinMismatch {
                throw VexBridgeNetworkingError.certificateMismatch
            }
            throw error
        }
    }

    static func isBridgeURL(_ url: URL) -> Bool {
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

@main
struct VexNativeApp: App {
    @UIApplicationDelegateAdaptor(VexAppDelegate.self) private var appDelegate
    @StateObject private var appModel = AppModel()

    init() {
        VexAppShortcuts.updateAppShortcutParameters()
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(appModel)
                .preferredColorScheme(.dark)
        }
    }
}