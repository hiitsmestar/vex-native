#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BG = ROOT / "VexNative" / "VexBackgroundAgent.swift"

text = BG.read_text(encoding="utf-8")
if "V140_BACKGROUND_LONGPOLL_RELAY" in text:
    print("PASS v0.13.10 background long-poll already applied")
    raise SystemExit(0)

text = text.replace(
    'private let V139_AGENT_LIFECYCLE_KEEPALIVE = "v0.13.9-agent-lifecycle-keepalive-v1"',
    'private let V139_AGENT_LIFECYCLE_KEEPALIVE = "v0.13.9-agent-lifecycle-keepalive-v1"\n'
    'private let V140_BACKGROUND_LONGPOLL_RELAY = "v0.13.10-background-longpoll-relay-v1"',
    1,
)

old_launch = '''        VexBackgroundAgent.shared.register()
        VexBackgroundAgent.shared.schedule()
        return true'''
new_launch = '''        VexBackgroundAgent.shared.register()
        VexBackgroundAgent.shared.schedule()
        VexBackgroundCommandSession.shared.start()
        return true'''
if old_launch not in text:
    raise SystemExit("v0.13.10 launch anchor missing")
text = text.replace(old_launch, new_launch, 1)

old_active = '''    func applicationDidBecomeActive(_ application: UIApplication) {
        VexBackgroundAgent.shared.startForegroundLoop()
    }'''
new_active = '''    func applicationDidBecomeActive(_ application: UIApplication) {
        VexBackgroundAgent.shared.startForegroundLoop()
        VexBackgroundCommandSession.shared.start()
    }'''
if old_active not in text:
    raise SystemExit("v0.13.10 active anchor missing")
text = text.replace(old_active, new_active, 1)

delegate_anchor = '''    func applicationWillEnterForeground(_ application: UIApplication) {
        VexBackgroundAgent.shared.endBackgroundGrace(using: application)
    }
}'''
delegate_new = '''    func applicationWillEnterForeground(_ application: UIApplication) {
        VexBackgroundAgent.shared.endBackgroundGrace(using: application)
    }

    func application(
        _ application: UIApplication,
        handleEventsForBackgroundURLSession identifier: String,
        completionHandler: @escaping () -> Void
    ) {
        VexBackgroundCommandSession.shared.setSystemCompletionHandler(completionHandler)
    }
}'''
if delegate_anchor not in text:
    raise SystemExit("v0.13.10 background URLSession app delegate anchor missing")
text = text.replace(delegate_anchor, delegate_new, 1)

worker_anchor = '''enum VexHeadlessBrain {'''
session_code = r'''
final class VexBackgroundCommandSession: NSObject, URLSessionDownloadDelegate, URLSessionDelegate {
    static let shared = VexBackgroundCommandSession()
    static let identifier = "local.star.vexnative.background.commandwait"

    private var session: URLSession!
    private var armed = false
    private var systemCompletionHandler: (() -> Void)?

    private override init() {
        super.init()
        let config = URLSessionConfiguration.background(withIdentifier: Self.identifier)
        config.sessionSendsLaunchEvents = true
        config.isDiscretionary = false
        config.waitsForConnectivity = true
        config.timeoutIntervalForRequest = 35
        config.timeoutIntervalForResource = 45
        session = URLSession(configuration: config, delegate: self, delegateQueue: nil)
    }

    func setSystemCompletionHandler(_ handler: @escaping () -> Void) {
        systemCompletionHandler = handler
    }

    func start() {
        session.getAllTasks { tasks in
            if tasks.isEmpty {
                self.arm()
            }
        }
    }

    private func arm() {
        guard !armed, let url = waitURL() else { return }
        armed = true
        var request = URLRequest(url: url)
        request.timeoutInterval = 35
        request.cachePolicy = .reloadIgnoringLocalCacheData
        session.downloadTask(with: request).resume()
    }

    private func waitURL() -> URL? {
        for raw in VexHeadlessBrain.configuredEndpoints() {
            guard let root = URL(string: raw),
                  VexBridgeNetworking.isBridgeURL(root),
                  var parts = URLComponents(url: root, resolvingAgainstBaseURL: false)
            else { continue }
            parts.port = 8771
            parts.path = "/phone/wait"
            return parts.url
        }
        return nil
    }

    func urlSession(
        _ session: URLSession,
        didReceive challenge: URLAuthenticationChallenge,
        completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
    ) {
        guard challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust,
              challenge.protectionSpace.port == 8771,
              let trust = challenge.protectionSpace.serverTrust,
              VexBridgeNetworking.isPrivateLANHost(challenge.protectionSpace.host.lowercased())
        else {
            completionHandler(.performDefaultHandling, nil)
            return
        }
        completionHandler(.useCredential, URLCredential(trust: trust))
    }

    func urlSession(
        _ session: URLSession,
        downloadTask: URLSessionDownloadTask,
        didFinishDownloadingTo location: URL
    ) {
        let data = (try? Data(contentsOf: location)) ?? Data()
        Task {
            _ = await VexPhoneBackgroundWorker.handleEnvelopeData(data)
            self.armed = false
            self.arm()
        }
    }

    func urlSession(
        _ session: URLSession,
        task: URLSessionTask,
        didCompleteWithError error: Error?
    ) {
        if error != nil {
            armed = false
            DispatchQueue.global().asyncAfter(deadline: .now() + 2) {
                self.arm()
            }
        }
    }

    func urlSessionDidFinishEvents(forBackgroundURLSession session: URLSession) {
        let handler = systemCompletionHandler
        systemCompletionHandler = nil
        DispatchQueue.main.async {
            handler?()
        }
    }
}

'''
if worker_anchor not in text:
    raise SystemExit("v0.13.10 session insertion anchor missing")
text = text.replace(worker_anchor, session_code + worker_anchor, 1)

run_anchor = '''    static func runOnce() async -> Bool {
        guard !Task.isCancelled else { return false }'''
run_new = '''    static func handleEnvelopeData(_ data: Data) async -> Bool {
        guard let envelope = try? JSONDecoder().decode(NextEnvelope.self, from: data),
              envelope.ok
        else { return false }
        guard let remote = envelope.command else { return true }

        let outcome = await execute(remote.command)
        await postResult(id: remote.id, ok: outcome.ok, result: outcome.result)
        UserDefaults.standard.set(Date(), forKey: "vex.phone.background.lastRun")
        return outcome.ok
    }

    static func runOnce() async -> Bool {
        guard !Task.isCancelled else { return false }'''
if run_anchor not in text:
    raise SystemExit("v0.13.10 worker anchor missing")
text = text.replace(run_anchor, run_new, 1)

old_decode = '''            let envelope = try JSONDecoder().decode(NextEnvelope.self, from: data)
            guard envelope.ok else { return false }
            guard let remote = envelope.command else { return true }

            let outcome = await execute(remote.command)
            await postResult(id: remote.id, ok: outcome.ok, result: outcome.result)
            UserDefaults.standard.set(Date(), forKey: "vex.phone.background.lastRun")
            return outcome.ok'''
new_decode = '''            return await handleEnvelopeData(data)'''
if old_decode not in text:
    raise SystemExit("v0.13.10 runOnce decode anchor missing")
text = text.replace(old_decode, new_decode, 1)

BG.write_text(text, encoding="utf-8")

final = BG.read_text(encoding="utf-8")
for marker in [
    'V140_BACKGROUND_LONGPOLL_RELAY = "v0.13.10-background-longpoll-relay-v1"',
    "URLSessionConfiguration.background(withIdentifier: Self.identifier)",
    'parts.path = "/phone/wait"',
    "handleEventsForBackgroundURLSession",
    "VexPhoneBackgroundWorker.handleEnvelopeData",
    "sessionSendsLaunchEvents = true",
]:
    if marker not in final:
        raise SystemExit(f"v0.13.10 marker missing: {marker}")

print("PASS v0.13.10 background long-poll patch")
