#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BG = ROOT / "VexNative" / "VexBackgroundAgent.swift"

text = BG.read_text(encoding="utf-8")
if "V139_AGENT_LIFECYCLE_KEEPALIVE" in text:
    print("PASS v0.13.9 lifecycle keepalive already applied")
    raise SystemExit(0)

text = text.replace(
'''final class VexAppDelegate: NSObject, UIApplicationDelegate {
    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        VexBackgroundAgent.shared.register()
        VexBackgroundAgent.shared.schedule()
        return true
    }

    func applicationDidEnterBackground(_ application: UIApplication) {
        VexBackgroundAgent.shared.schedule()
    }
}''',
'''private let V139_AGENT_LIFECYCLE_KEEPALIVE = "v0.13.9-agent-lifecycle-keepalive-v1"

final class VexAppDelegate: NSObject, UIApplicationDelegate {
    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        VexBackgroundAgent.shared.register()
        VexBackgroundAgent.shared.schedule()
        return true
    }

    func applicationDidBecomeActive(_ application: UIApplication) {
        VexBackgroundAgent.shared.startForegroundLoop()
    }

    func applicationWillResignActive(_ application: UIApplication) {
        VexBackgroundAgent.shared.stopForegroundLoop()
    }

    func applicationDidEnterBackground(_ application: UIApplication) {
        VexBackgroundAgent.shared.schedule()
        VexBackgroundAgent.shared.startBackgroundGrace(using: application)
    }

    func applicationWillEnterForeground(_ application: UIApplication) {
        VexBackgroundAgent.shared.endBackgroundGrace(using: application)
    }
}''',
1)

text = text.replace(
'''    private var registered = false
    private init() {}''',
'''    private var registered = false
    private var foregroundTask: Task<Void, Never>?
    private var backgroundGraceTask: Task<Void, Never>?
    private var backgroundTaskIdentifier: UIBackgroundTaskIdentifier = .invalid
    private init() {}''',
1)

anchor = '''    func schedule() {
        let refresh = BGAppRefreshTaskRequest(identifier: Self.refreshIdentifier)'''
insert = '''    func startForegroundLoop() {
        guard foregroundTask == nil else { return }
        foregroundTask = Task {
            while !Task.isCancelled {
                _ = await VexPhoneBackgroundWorker.runOnce()
                try? await Task.sleep(nanoseconds: 2_000_000_000)
            }
        }
    }

    func stopForegroundLoop() {
        foregroundTask?.cancel()
        foregroundTask = nil
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
        let refresh = BGAppRefreshTaskRequest(identifier: Self.refreshIdentifier)'''
if anchor not in text:
    raise SystemExit("v0.13.9 schedule anchor missing")
text = text.replace(anchor, insert, 1)

BG.write_text(text, encoding="utf-8")

final = BG.read_text(encoding="utf-8")
for marker in [
    'V139_AGENT_LIFECYCLE_KEEPALIVE = "v0.13.9-agent-lifecycle-keepalive-v1"',
    "applicationDidBecomeActive",
    "startForegroundLoop()",
    "beginBackgroundTask(withName: \"VexPhoneAgentGrace\")",
    "application.backgroundTimeRemaining > 5",
    "endBackgroundTask(backgroundTaskIdentifier)",
]:
    if marker not in final:
        raise SystemExit(f"v0.13.9 marker missing: {marker}")

print("PASS v0.13.9 agent lifecycle keepalive patch")
