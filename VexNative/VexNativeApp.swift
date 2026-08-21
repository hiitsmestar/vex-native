import Foundation
import SwiftUI

/// v0.7: allow the paired desktop Vex Bridge to expose a local HTTPS endpoint
/// with a per-install self-signed certificate. Trust is relaxed only for private
/// LAN hosts on the dedicated bridge port; ordinary public HTTPS keeps normal
/// system certificate validation.
final class VexBridgeURLProtocol: URLProtocol, URLSessionDataDelegate {
    private var task: URLSessionDataTask?
    private var session: URLSession?

    override class func canInit(with request: URLRequest) -> Bool {
        guard request.value(forHTTPHeaderField: "X-Vex-Bridge-Forwarded") == nil,
              let url = request.url,
              url.scheme?.lowercased() == "https",
              url.port == 8765,
              let host = url.host?.lowercased(),
              isPrivateLANHost(host)
        else { return false }
        return true
    }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        var forwarded = request
        forwarded.setValue("1", forHTTPHeaderField: "X-Vex-Bridge-Forwarded")

        // The Web Brain normally sends only the newest sentence as the search query.
        // For bridge requests, add the immediately preceding Star turn as context so
        // follow-ups such as "look up why this is happening" retain the dryer/error/
        // device details that were just described instead of becoming a vague search.
        if let url = forwarded.url,
           var components = URLComponents(url: url, resolvingAgainstBaseURL: false),
           var items = components.queryItems,
           let qIndex = items.firstIndex(where: { $0.name == "q" }),
           let current = items[qIndex].value,
           !current.isEmpty {
            let profile = LocalStore.shared.load()
            let previousUser = profile.messages
                .reversed()
                .first(where: { $0.role == .user })?
                .content
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            if !previousUser.isEmpty && !current.localizedCaseInsensitiveContains(previousUser) {
                let context = String(previousUser.prefix(700))
                items[qIndex] = URLQueryItem(name: "q", value: "\(current) | previous context: \(context)")
                components.queryItems = items
                forwarded.url = components.url
            }
        }

        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 18
        configuration.timeoutIntervalForResource = 24
        configuration.protocolClasses = []
        let session = URLSession(configuration: configuration, delegate: self, delegateQueue: nil)
        self.session = session

        task = session.dataTask(with: forwarded) { [weak self] data, response, error in
            guard let self else { return }
            if let error {
                self.client?.urlProtocol(self, didFailWithError: error)
                return
            }
            if let response {
                self.client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            }
            if let data, !data.isEmpty {
                self.client?.urlProtocol(self, didLoad: data)
            }
            self.client?.urlProtocolDidFinishLoading(self)
        }
        task?.resume()
    }

    override func stopLoading() {
        task?.cancel()
        session?.invalidateAndCancel()
        task = nil
        session = nil
    }

    func urlSession(
        _ session: URLSession,
        didReceive challenge: URLAuthenticationChallenge,
        completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
    ) {
        guard challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust,
              challenge.protectionSpace.port == 8765,
              let trust = challenge.protectionSpace.serverTrust,
              Self.isPrivateLANHost(challenge.protectionSpace.host.lowercased())
        else {
            completionHandler(.performDefaultHandling, nil)
            return
        }
        completionHandler(.useCredential, URLCredential(trust: trust))
    }

    private static func isPrivateLANHost(_ host: String) -> Bool {
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

    init() {
        URLProtocol.registerClass(VexBridgeURLProtocol.self)
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(appModel)
                .preferredColorScheme(.dark)
        }
    }
}
