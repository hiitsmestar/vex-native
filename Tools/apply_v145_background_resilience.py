#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "VexNative" / "VexNativeApp.swift"

text = APP.read_text(encoding="utf-8")
if "V145_BACKGROUND_RESILIENCE" in text:
    print("PASS v0.14.5 background resilience already applied")
    raise SystemExit(0)

if "import SwiftUI" not in text:
    raise SystemExit("SwiftUI import anchor missing")
text = text.replace(
    "import SwiftUI",
    "import SwiftUI\nimport UIKit\nimport BackgroundTasks",
    1,
)

anchor = "@main\nstruct VexNativeApp: App {"
if anchor not in text:
    raise SystemExit("VexNativeApp anchor missing")

coordinator = r'''
@MainActor
private enum VexBackgroundCoordinator {
    static let V145_BACKGROUND_RESILIENCE = "v0.14.5-background-resilience-v2"
    static let refreshIdentifier = "local.star.vexnative.background.refresh"
    static let processingIdentifier = "local.star.vexnative.background.processing"

    private static var registered = false
    private static var graceTask: UIBackgroundTaskIdentifier = .invalid

    static func register() {
        guard !registered else { return }
        registered = true

        BGTaskScheduler.shared.register(
            forTaskWithIdentifier: refreshIdentifier,
            using: nil
        ) { task in
            guard let refresh = task as? BGAppRefreshTask else {
                task.setTaskCompleted(success: false)
                return
            }
            Task { @MainActor in
                handleRefresh(refresh)
            }
        }

        BGTaskScheduler.shared.register(
            forTaskWithIdentifier: processingIdentifier,
            using: nil
        ) { task in
            guard let processing = task as? BGProcessingTask else {
                task.setTaskCompleted(success: false)
                return
            }
            Task { @MainActor in
                handleProcessing(processing)
            }
        }

        NotificationCenter.default.addObserver(
            forName: UIApplication.didBecomeActiveNotification,
            object: nil,
            queue: .main
        ) { _ in
            Task { @MainActor in
                appBecameActive()
            }
        }

        NotificationCenter.default.addObserver(
            forName: UIApplication.didEnterBackgroundNotification,
            object: nil,
            queue: .main
        ) { _ in
            Task { @MainActor in
                appEnteredBackground()
            }
        }

        scheduleAll()
    }

    static func appBecameActive() {
        scheduleAll()
        Task {
            _ = await VexBackgroundAgent.runOnce()
        }
    }

    static func appEnteredBackground() {
        scheduleAll()
        beginGraceWindow()
    }

    private static func handleRefresh(_ task: BGAppRefreshTask) {
        scheduleRefresh()
        let work = Task {
            let ok = await VexBackgroundAgent.runOnce()
            task.setTaskCompleted(success: ok)
        }
        task.expirationHandler = {
            work.cancel()
        }
    }

    private static func handleProcessing(_ task: BGProcessingTask) {
        scheduleProcessing()
        let work = Task {
            let ok = await VexBackgroundAgent.runOnce()
            task.setTaskCompleted(success: ok)
        }
        task.expirationHandler = {
            work.cancel()
        }
    }

    private static func scheduleAll() {
        scheduleRefresh()
        scheduleProcessing()
    }

    private static func scheduleRefresh() {
        BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: refreshIdentifier)
        let request = BGAppRefreshTaskRequest(identifier: refreshIdentifier)
        request.earliestBeginDate = Date(timeIntervalSinceNow: 15 * 60)
        try? BGTaskScheduler.shared.submit(request)
    }

    private static func scheduleProcessing() {
        BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: processingIdentifier)
        let request = BGProcessingTaskRequest(identifier: processingIdentifier)
        request.requiresNetworkConnectivity = true
        request.requiresExternalPower = false
        request.earliestBeginDate = Date(timeIntervalSinceNow: 20 * 60)
        try? BGTaskScheduler.shared.submit(request)
    }

    private static func beginGraceWindow() {
        if graceTask != .invalid {
            UIApplication.shared.endBackgroundTask(graceTask)
            graceTask = .invalid
        }

        graceTask = UIApplication.shared.beginBackgroundTask(
            withName: "VexRemoteRelayGrace"
        ) {
            if graceTask != .invalid {
                UIApplication.shared.endBackgroundTask(graceTask)
                graceTask = .invalid
            }
        }

        Task {
            defer {
                if graceTask != .invalid {
                    UIApplication.shared.endBackgroundTask(graceTask)
                    graceTask = .invalid
                }
            }

            for _ in 0..<3 {
                guard !Task.isCancelled else { break }
                _ = await VexBackgroundAgent.runOnce()
                try? await Task.sleep(nanoseconds: 6_000_000_000)
            }
        }
    }
}

'''

text = text.replace(anchor, coordinator + anchor, 1)

struct_anchor = "struct VexNativeApp: App {"
init_injection = '''struct VexNativeApp: App {
    init() {
        VexBackgroundCoordinator.register()
    }'''
if text.count(struct_anchor) != 1:
    raise SystemExit("unexpected VexNativeApp declaration count")
text = text.replace(struct_anchor, init_injection, 1)

APP.write_text(text, encoding="utf-8")

final = APP.read_text(encoding="utf-8")
for marker in [
    "V145_BACKGROUND_RESILIENCE",
    "BGTaskScheduler.shared.register",
    "BGAppRefreshTaskRequest",
    "BGProcessingTaskRequest",
    "beginBackgroundTask",
    "UIApplication.didEnterBackgroundNotification",
    "UIApplication.didBecomeActiveNotification",
    "VexBackgroundAgent.runOnce()",
]:
    if marker not in final:
        raise SystemExit(f"missing v0.14.5 marker: {marker}")

print("PASS v0.14.5 background resilience patch")
