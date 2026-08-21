import Foundation
import SwiftUI

/// v0.7: allow the paired desktop Vex Bridge to expose a local HTTPS endpoint
/// with a per-install self-signed certificate. We only relax trust for private-
/// network hosts on the dedicated bridge port; public HTTPS traffic keeps normal
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
        guard var request = request as URLRequest? else { return }
        request.setValue("1", forHTTPHeaderField: "X-Vex-Bridge-Forwarded")

        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 18
        configuration.timeoutIntervalForResource = 24
        configuration.protocolClasses = []
        let session = URLSession(configuration: configuration, delegate: self, delegateQueue: nil)
        self.session = session

        task = session.dataTask(with: request) { [weak self] data, response, error in
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
