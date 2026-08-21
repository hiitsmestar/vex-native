import Foundation
import SwiftUI

/// Dedicated LAN transport for Vex Bridge.
///
/// URLSession.shared follows normal iOS trust rules and correctly rejects the
/// bridge's per-install self-signed certificate. For the paired bridge only,
/// create an ephemeral session whose delegate accepts server trust exclusively
/// for private-LAN hosts on the dedicated Vex Bridge port. Public HTTPS never
/// uses this relaxed path.
final class VexBridgeTrustDelegate: NSObject, URLSessionDelegate {
    func urlSession(
        _ session: URLSession,
        didReceive challenge: URLAuthenticationChallenge,
        completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
    ) {
        guard challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust,
              challenge.protectionSpace.port == 8765,
              let trust = challenge.protectionSpace.serverTrust,
              VexBridgeNetworking.isPrivateLANHost(challenge.protectionSpace.host.lowercased())
        else {
            completionHandler(.performDefaultHandling, nil)
            return
        }

        completionHandler(.useCredential, URLCredential(trust: trust))
    }
}

enum VexBridgeNetworking {
    static func data(for request: URLRequest) async throws -> (Data, URLResponse) {
        guard let url = request.url, isBridgeURL(url) else {
            return try await URLSession.shared.data(for: request)
        }

        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 18
        configuration.timeoutIntervalForResource = 24
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        // Avoid custom/global URLProtocol recursion. This session speaks directly
        // to the paired bridge and handles its TLS challenge with the delegate.
        configuration.protocolClasses = []

        let delegate = VexBridgeTrustDelegate()
        let session = URLSession(configuration: configuration, delegate: delegate, delegateQueue: nil)
        defer { session.finishTasksAndInvalidate() }
        return try await session.data(for: request)
    }

    static func isBridgeURL(_ url: URL) -> Bool {
        guard url.scheme?.lowercased() == "https",
              url.port == 8765,
              let host = url.host?.lowercased()
        else { return false }
        return isPrivateLANHost(host)
    }

    static func isPrivateLANHost(_ host: String) -> Bool {
        if host == "localhost" || host.hasSuffix(".local") { return true }
        if host.hasPrefix("127.") || host.hasPrefix("10.") || host.hasPrefix("192.168.") || host.hasPrefix("169.254.") {
            return true
        }
        let parts = host.split(separator: ".").compactMap { Int($0) }
        return parts.count == 4 && parts[0] == 172 && (16...31).contains(parts[1])
    }
}

@main
struct VexNativeApp: App {
    @StateObject private var appModel = AppModel()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(appModel)
                .preferredColorScheme(.dark)
        }
    }
}
