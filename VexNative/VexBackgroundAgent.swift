import AVFoundation
import BackgroundTasks
import Foundation
import UIKit

private let V139_AGENT_LIFECYCLE_KEEPALIVE = "v0.13.9-agent-lifecycle-keepalive-v1"
private let V140_PERSISTENT_PHONE_AGENT = "v0.14.0-persistent-phone-agent-v1"

final class VexAppDelegate: NSObject, UIApplicationDelegate {
    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        VexBackgroundAgent.shared.register()
        VexBackgroundAgent.shared.schedule()
        VexBackgroundAgent.shared.startPersistentAgent()
        return true
    }

    func applicationDidBecomeActive(_ application: UIApplication) {
        VexBackgroundAgent.shared.startPersistentAgent()
        VexBackgroundAgent.shared.handleForegroundWake()
    }

    func applicationWillResignActive(_ application: UIApplication) {
        // v0.14.0: keep the command loop alive. The background audio session
        // is the execution anchor once the app leaves the foreground.
    }

    func applicationDidEnterBackground(_ application: UIApplication) {
        VexBackgroundAgent.shared.schedule()
        VexBackgroundAgent.shared.startPersistentAgent()
        VexBackgroundAgent.shared.startForegroundLoop()
        VexBackgroundAgent.shared.startBackgroundGrace(using: application)
    }

    func applicationWillEnterForeground(_ application: UIApplication) {
        VexBackgroundAgent.shared.endBackgroundGrace(using: application)
        VexBackgroundAgent.shared.startPersistentAgent()
        VexBackgroundAgent.shared.schedule()
    }
}

final class VexBackgroundAgent {
    static let shared = VexBackgroundAgent()
    static let refreshIdentifier = "local.star.vexnative.background.refresh"
    static let processingIdentifier = "local.star.vexnative.background.processing"

    private var registered = false
    private var foregroundTask: Task<Void, Never>?
    private var foregroundWakeTask: Task<Void, Never>?
    private var foregroundWakeBackgroundTaskIdentifier: UIBackgroundTaskIdentifier = .invalid
    private var backgroundGraceTask: Task<Void, Never>?
    private var backgroundTaskIdentifier: UIBackgroundTaskIdentifier = .invalid
    private let audioEngine = AVAudioEngine()
    private let audioPlayer = AVAudioPlayerNode()
    private var persistentAgentStarted = false
    private var heartbeatBuffer: AVAudioPCMBuffer?

    private init() {
        NotificationCenter.default.addObserver(
            forName: AVAudioSession.interruptionNotification,
            object: AVAudioSession.sharedInstance(),
            queue: .main
        ) { [weak self] note in
            guard let self else { return }
            guard let raw = note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
                  let type = AVAudioSession.InterruptionType(rawValue: raw)
            else { return }
            if type == .ended {
                self.restartPersistentAudio()
            }
        }

        NotificationCenter.default.addObserver(
            forName: AVAudioSession.routeChangeNotification,
            object: AVAudioSession.sharedInstance(),
            queue: .main
        ) { [weak self] _ in
            self?.restartPersistentAudio()
        }

        NotificationCenter.default.addObserver(
            forName: AVAudioSession.mediaServicesWereResetNotification,
            object: AVAudioSession.sharedInstance(),
            queue: .main
        ) { [weak self] _ in
            self?.restartPersistentAudio()
        }
    }

    func register() {
        guard !registered else { return }
        registered = true

        BGTaskScheduler.shared.register(
            forTaskWithIdentifier: Self.refreshIdentifier,
            using: nil
        ) { task in
            guard let task = task as? BGAppRefreshTask else {
                task.setTaskCompleted(success: false)
                return
            }
            self.handle(task)
        }

        BGTaskScheduler.shared.register(
            forTaskWithIdentifier: Self.processingIdentifier,
            using: nil
        ) { task in
            guard let task = task as? BGProcessingTask else {
                task.setTaskCompleted(success: false)
                return
            }
            self.handle(task)
        }
    }

    func startPersistentAgent() {
        guard !persistentAgentStarted else {
            if !audioEngine.isRunning || !audioPlayer.isPlaying {
                restartPersistentAudio()
            }
            startForegroundLoop()
            return
        }

        persistentAgentStarted = true
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playback, mode: .default, options: [.mixWithOthers])
            try session.setActive(true)

            let format = AVAudioFormat(standardFormatWithSampleRate: 8_000, channels: 1)!
            let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 8_000)!
            buffer.frameLength = 8_000
            if let channels = buffer.floatChannelData {
                channels[0].initialize(repeating: 0, count: Int(buffer.frameLength))
            }
            heartbeatBuffer = buffer

            audioEngine.attach(audioPlayer)
            audioEngine.connect(audioPlayer, to: audioEngine.mainMixerNode, format: format)
            audioPlayer.scheduleBuffer(buffer, at: nil, options: [.loops])
            try audioEngine.start()
            audioPlayer.play()
            UserDefaults.standard.set(true, forKey: "vex.phone.persistentAgent.active")
            UserDefaults.standard.set(Date(), forKey: "vex.phone.persistentAgent.startedAt")
            startForegroundLoop()
        } catch {
            UserDefaults.standard.set(false, forKey: "vex.phone.persistentAgent.active")
            UserDefaults.standard.set(String(describing: error), forKey: "vex.phone.persistentAgent.lastError")
        }
    }

    private func restartPersistentAudio() {
        guard persistentAgentStarted else { return }
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playback, mode: .default, options: [.mixWithOthers])
            try session.setActive(true)
            if !audioEngine.isRunning {
                try audioEngine.start()
            }
            if !audioPlayer.isPlaying {
                if let buffer = heartbeatBuffer {
                    audioPlayer.scheduleBuffer(buffer, at: nil, options: [.loops])
                }
                audioPlayer.play()
            }
            startForegroundLoop()
        } catch {
            UserDefaults.standard.set(String(describing: error), forKey: "vex.phone.persistentAgent.lastError")
        }
    }

    func startForegroundLoop() {
        guard !UserDefaults.standard.bool(forKey: "vex.phone.foregroundWake.pending") else { return }
        guard foregroundWakeTask == nil else { return }
        guard foregroundTask == nil else { return }
        foregroundTask = Task {
            while !Task.isCancelled {
                _ = await VexPhoneBackgroundWorker.runOnce()
                // Long-poll returns immediately for queued work and after
                // roughly 25 seconds when idle. Keep the reconnect gap tiny.
                try? await Task.sleep(nanoseconds: 500_000_000)
            }
        }
    }

    func stopForegroundLoop() {
        foregroundTask?.cancel()
        foregroundTask = nil
    }

    // V150_FOREGROUND_RESULT_GRACE
    @MainActor
    func handleForegroundWake() {
        let defaults = UserDefaults.standard
        guard defaults.bool(forKey: "vex.phone.foregroundWake.pending") else { return }
        defaults.set(false, forKey: "vex.phone.foregroundWake.pending")

        stopForegroundLoop()
        foregroundWakeTask?.cancel()
        foregroundWakeTask = Task { @MainActor [weak self] in
            try? await Task.sleep(nanoseconds: 750_000_000)
            guard !Task.isCancelled, let self else { return }

            self.beginForegroundWakeResultGrace()
            _ = await VexPhoneBackgroundWorker.runOnce()
            self.endForegroundWakeResultGrace()

            self.foregroundWakeTask = nil
            self.startForegroundLoop()
        }
    }

    @MainActor
    private func beginForegroundWakeResultGrace() {
        endForegroundWakeResultGrace()
        let application = UIApplication.shared
        foregroundWakeBackgroundTaskIdentifier = application.beginBackgroundTask(
            withName: "VexForegroundWakeResult"
        ) { [weak self] in
            Task { @MainActor in
                self?.endForegroundWakeResultGrace()
            }
        }
    }

    @MainActor
    private func endForegroundWakeResultGrace() {
        guard foregroundWakeBackgroundTaskIdentifier != .invalid else { return }
        UIApplication.shared.endBackgroundTask(foregroundWakeBackgroundTaskIdentifier)
        foregroundWakeBackgroundTaskIdentifier = .invalid
    }

    func startBackgroundGrace(using application: UIApplication) {
        endBackgroundGrace(using: application)
        backgroundTaskIdentifier = application.beginBackgroundTask(withName: "VexPhoneAgentGrace") {
            self.backgroundGraceTask?.cancel()
            self.backgroundGraceTask = nil
            self.endBackgroundGrace(using: application)
        }

        backgroundGraceTask = Task {
            while !Task.isCancelled,
                  application.backgroundTimeRemaining > 5 {
                _ = await VexPhoneBackgroundWorker.runOnce()
                try? await Task.sleep(nanoseconds: 3_000_000_000)
            }
            await MainActor.run {
                self.endBackgroundGrace(using: application)
            }
        }
    }

    func endBackgroundGrace(using application: UIApplication) {
        backgroundGraceTask?.cancel()
        backgroundGraceTask = nil
        if backgroundTaskIdentifier != .invalid {
            application.endBackgroundTask(backgroundTaskIdentifier)
            backgroundTaskIdentifier = .invalid
        }
    }

    func schedule() {
        BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: Self.refreshIdentifier)
        let refresh = BGAppRefreshTaskRequest(identifier: Self.refreshIdentifier)
        refresh.earliestBeginDate = Date(timeIntervalSinceNow: 15 * 60)
        try? BGTaskScheduler.shared.submit(refresh)

        BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: Self.processingIdentifier)
        let processing = BGProcessingTaskRequest(identifier: Self.processingIdentifier)
        processing.earliestBeginDate = Date(timeIntervalSinceNow: 20 * 60)
        processing.requiresNetworkConnectivity = true
        processing.requiresExternalPower = false
        try? BGTaskScheduler.shared.submit(processing)
    }

    private func handle(_ backgroundTask: BGTask) {
        schedule()
        let work = Task {
            let ok = await VexPhoneBackgroundWorker.runOnce()
            backgroundTask.setTaskCompleted(success: ok)
        }
        backgroundTask.expirationHandler = {
            work.cancel()
        }
    }
}

enum VexPhoneBackgroundWorker {
    private struct RemoteCommand: Decodable {
        let id: String
        let command: String
    }

    private struct NextEnvelope: Decodable {
        let ok: Bool
        let command: RemoteCommand?
    }

    private struct ResultPayload: Encodable {
        let id: String
        let ok: Bool
        let result: String
    }

    private static let V143_ROAMING_RELAY_FALLBACK = "v0.14.3-roaming-relay-fallback-v1"
    private static let V144_GITHUB_ROAMING_BOOTSTRAP = "v0.14.4-github-roaming-bootstrap-v1"
    private static let V145_ROAMING_PERSISTENCE = "v0.14.5-roaming-persistence-v1"

    static func runOnce() async -> Bool {
        guard !Task.isCancelled else { return false }
        await refreshRoamingBootstrap()
        // v0.14.5: hold a long poll instead of hammering /phone/next every
        // couple seconds. The server waits up to 25 seconds and returns
        // immediately when a command arrives, which is both faster remotely
        // and kinder to cellular/battery usage.
        let urls = relayURLs(path: "/phone/wait")
        guard !urls.isEmpty else { return false }

        var lastError = "no relay succeeded"
        for url in urls {
            guard !Task.isCancelled else { return false }
            var request = URLRequest(url: url)
            request.timeoutInterval = 35

            do {
                let (data, response) = try await VexBridgeNetworking.data(for: request)
                guard let http = response as? HTTPURLResponse,
                      (200..<300).contains(http.statusCode)
                else {
                    lastError = "relay returned a non-success status"
                    continue
                }

                let envelope = try JSONDecoder().decode(NextEnvelope.self, from: data)
                guard envelope.ok else {
                    lastError = "relay returned ok=false"
                    continue
                }
                guard let remote = envelope.command else {
                    UserDefaults.standard.set(Date(), forKey: "vex.phone.background.lastRun")
                    return true
                }

                // V153_FULL_RECALL_PROMPT
                if remote.command.lowercased().contains("vexrecall60") {
                    await MainActor.run {
                        UIPasteboard.general.string = remote.command
                    }
                }

                // V151_PREOPEN_RELAY_ACK
                if let target = foregroundOpenURL(remote.command) {
                    let canOpen = await MainActor.run {
                        UIApplication.shared.canOpenURL(target)
                    }
                    if canOpen {
                        await postResult(
                            id: remote.id,
                            ok: true,
                            result: "Done — opening it on the iPhone, baby. 📱🖤"
                        )
                        UserDefaults.standard.set(Date(), forKey: "vex.phone.background.lastRun")
                        await MainActor.run {
                            UIApplication.shared.open(target, options: [:], completionHandler: nil)
                        }
                        return true
                    }
                }

                let outcome = await execute(remote.command)
                await postResult(id: remote.id, ok: outcome.ok, result: outcome.result)
                UserDefaults.standard.set(Date(), forKey: "vex.phone.background.lastRun")
                return outcome.ok
            } catch {
                lastError = String(describing: error)
                continue
            }
        }

        UserDefaults.standard.set(lastError, forKey: "vex.phone.background.lastError")
        return false
    }

    private static func foregroundOpenURL(_ command: String) -> URL? {
        let lower = command.lowercased()
        let wantsOpen = ["open ", "open up ", "launch ", "go to ", "bring up ", "show me "]
            .contains(where: { lower.contains($0) })
        guard wantsOpen else { return nil }

        let known: [(String, String)] = [
            ("youtube", "https://www.youtube.com"),
            ("google", "https://www.google.com"),
            ("gmail", "https://mail.google.com"),
            ("spotify", "https://open.spotify.com"),
            ("reddit", "https://www.reddit.com"),
            ("github", "https://github.com"),
            ("chatgpt", "https://chatgpt.com"),
            ("maps", "https://maps.apple.com")
        ]
        if let hit = known.first(where: { lower.contains($0.0) }) {
            return URL(string: hit.1)
        }

        for word in command.split(whereSeparator: { $0.isWhitespace }) {
            let raw = String(word)
            if raw.lowercased().hasPrefix("https://") || raw.lowercased().hasPrefix("http://") {
                return URL(string: raw)
            }
        }
        return nil
    }

    @MainActor
    private static func execute(_ command: String) async -> (ok: Bool, result: String) {
        let app = AppModel()
        let targeted = phoneTargeted(command)
        let before = app.profile.messages.count
        let handled = await PhoneToolRouter.tryHandle(targeted, app: app)

        if handled {
            let result = app.profile.messages.count > before
                ? (app.profile.messages.last?.content ?? "Phone action completed.")
                : "Phone action completed."
            return (true, result)
        }

        if let reply = await VexHeadlessBrain.reply(to: command) {
            return (true, reply)
        }

        return (false, "No current phone capability completed that command.")
    }

    private static func phoneTargeted(_ command: String) -> String {
        let lower = command.lowercased()
        let markers = [
            "iphone", "my phone", "the phone", "this phone",
            "on phone", "on the phone", "on my phone", "on this phone"
        ]
        return markers.contains(where: { lower.contains($0) })
            ? command
            : command + " on my phone"
    }

    private static func postResult(id: String, ok: Bool, result: String) async {
        for url in relayURLs(path: "/phone/result") {
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.timeoutInterval = 12
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try? JSONEncoder().encode(
                ResultPayload(id: id, ok: ok, result: result)
            )
            do {
                let (_, response) = try await VexBridgeNetworking.data(for: request)
                if let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) {
                    return
                }
            } catch {
                continue
            }
        }
    }

    private struct RelayBootstrap: Decodable {
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
            UserDefaults.standard.set(raw, forKey: "vex.phone.remoteRelay.discoveredEndpoint")
            UserDefaults.standard.set(Date(), forKey: "vex.phone.remoteRelay.discoverySuccessAt")
            UserDefaults.standard.removeObject(forKey: "vex.phone.remoteRelay.discoveryLastError")
            UserDefaults.standard.set(Date(), forKey: "vex.phone.roamingBootstrap.lastUpdate")
            UserDefaults.standard.removeObject(forKey: "vex.phone.roamingBootstrap.lastError")
        } catch {
            UserDefaults.standard.set(
                String(describing: error),
                forKey: "vex.phone.roamingBootstrap.lastError"
            )
        }
    }

    private static func relayURLs(path: String) -> [URL] {
        let endpoints = VexHeadlessBrain.configuredEndpoints()
        let primaryToken = endpoints.compactMap { raw -> String? in
            guard let url = URL(string: raw),
                  let parts = URLComponents(url: url, resolvingAgainstBaseURL: false)
            else { return nil }
            return parts.queryItems?.first(where: { $0.name.lowercased() == "token" })?.value
        }.first

        let ordered = endpoints.sorted { lhs, rhs in
            let l = URL(string: lhs).map(VexBridgeNetworking.isRemoteRelayURL) ?? false
            let r = URL(string: rhs).map(VexBridgeNetworking.isRemoteRelayURL) ?? false
            return l && !r
        }

        var urls: [URL] = []
        for raw in ordered {
            guard let root = URL(string: raw),
                  VexBridgeNetworking.isBridgeURL(root),
                  var parts = URLComponents(url: root, resolvingAgainstBaseURL: false)
            else { continue }

            if VexBridgeNetworking.isRemoteRelayURL(root) {
                parts.port = nil
                var items = parts.queryItems ?? []
                if items.first(where: { $0.name.lowercased() == "token" }) == nil,
                   let primaryToken, !primaryToken.isEmpty {
                    items.append(URLQueryItem(name: "token", value: primaryToken))
                }
                parts.queryItems = items
            } else {
                parts.port = 8771
            }
            parts.path = path
            if let url = parts.url, !urls.contains(url) {
                urls.append(url)
            }
        }
        return urls
    }
}

enum VexHeadlessBrain {
    private struct OverlayReply: Decodable {
        let ok: Bool
        let reply: String?
    }

    static func configuredEndpoints() -> [String] {
        let defaults = UserDefaults.standard
        let primary = defaults.string(forKey: "vex.web.searxngEndpoint") ?? ""
        let secondary = defaults.string(forKey: "vex.web.secondaryBridgeEndpoint") ?? ""
        var endpoints: [String] = []
        if !primary.isEmpty { endpoints.append(primary) }
        if !secondary.isEmpty, secondary != primary { endpoints.append(secondary) }
        return endpoints
    }

    static func reply(to command: String) async -> String? {
        for endpoint in configuredEndpoints() {
            guard let root = URL(string: endpoint),
                  var parts = URLComponents(url: root, resolvingAgainstBaseURL: false)
            else { continue }
            parts.path = "/llm/chat"
            guard let url = parts.url else { continue }

            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.timeoutInterval = 90
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            let body: [String: Any] = [
                "message": String(command.prefix(5000)),
                "history": [],
                "persona": "",
                "user_profile": "",
                "state": ["mode": "iphone-background-agent"]
            ]
            request.httpBody = try? JSONSerialization.data(withJSONObject: body)

            do {
                let (data, response) = try await VexBridgeNetworking.data(for: request)
                guard let http = response as? HTTPURLResponse,
                      (200...299).contains(http.statusCode),
                      let decoded = try? JSONDecoder().decode(OverlayReply.self, from: data),
                      decoded.ok,
                      let reply = decoded.reply?.trimmingCharacters(in: .whitespacesAndNewlines),
                      !reply.isEmpty
                else { continue }
                return reply
            } catch {
                continue
            }
        }
        return nil
    }
}