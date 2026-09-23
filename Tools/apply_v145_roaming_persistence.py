#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BG = ROOT / "VexNative" / "VexBackgroundAgent.swift"

text = BG.read_text(encoding="utf-8")
if "V145_ROAMING_PERSISTENCE" in text:
    print("PASS v0.14.5 roaming persistence already applied")
    raise SystemExit(0)

text = text.replace(
    'private static let V144_GITHUB_ROAMING_BOOTSTRAP = "v0.14.4-github-roaming-bootstrap-v1"',
    'private static let V144_GITHUB_ROAMING_BOOTSTRAP = "v0.14.4-github-roaming-bootstrap-v1"\n    private static let V145_ROAMING_PERSISTENCE = "v0.14.5-roaming-persistence-v1"',
    1,
)

old = '''        await refreshRoamingBootstrap()
        let urls = relayURLs(path: "/phone/next")
        guard !urls.isEmpty else { return false }'''
new = '''        await refreshRoamingBootstrap()
        // v0.14.5: hold a long poll instead of hammering /phone/next every
        // couple seconds. The server waits up to 25 seconds and returns
        // immediately when a command arrives, which is both faster remotely
        // and kinder to cellular/battery usage.
        let urls = relayURLs(path: "/phone/wait")
        guard !urls.isEmpty else { return false }'''
if old not in text:
    raise SystemExit("v0.14.5 runOnce relay anchor missing")
text = text.replace(old, new, 1)

text = text.replace(
    'request.timeoutInterval = 12',
    'request.timeoutInterval = 35',
    1,
)

old_loop = '''                _ = await VexPhoneBackgroundWorker.runOnce()
                try? await Task.sleep(nanoseconds: 2_000_000_000)'''
new_loop = '''                _ = await VexPhoneBackgroundWorker.runOnce()
                // Long-poll returns immediately for queued work and after
                // roughly 25 seconds when idle. Keep the reconnect gap tiny.
                try? await Task.sleep(nanoseconds: 500_000_000)'''
if old_loop not in text:
    raise SystemExit("v0.14.5 foreground loop anchor missing")
text = text.replace(old_loop, new_loop, 1)

old_sched = '''        let refresh = BGAppRefreshTaskRequest(identifier: Self.refreshIdentifier)
        refresh.earliestBeginDate = Date(timeIntervalSinceNow: 15 * 60)
        try? BGTaskScheduler.shared.submit(refresh)

        let processing = BGProcessingTaskRequest(identifier: Self.processingIdentifier)
        processing.earliestBeginDate = Date(timeIntervalSinceNow: 20 * 60)
        processing.requiresNetworkConnectivity = true
        processing.requiresExternalPower = false
        try? BGTaskScheduler.shared.submit(processing)'''
new_sched = '''        BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: Self.refreshIdentifier)
        let refresh = BGAppRefreshTaskRequest(identifier: Self.refreshIdentifier)
        refresh.earliestBeginDate = Date(timeIntervalSinceNow: 15 * 60)
        try? BGTaskScheduler.shared.submit(refresh)

        BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: Self.processingIdentifier)
        let processing = BGProcessingTaskRequest(identifier: Self.processingIdentifier)
        processing.earliestBeginDate = Date(timeIntervalSinceNow: 20 * 60)
        processing.requiresNetworkConnectivity = true
        processing.requiresExternalPower = false
        try? BGTaskScheduler.shared.submit(processing)'''
if old_sched not in text:
    raise SystemExit("v0.14.5 scheduler anchor missing")
text = text.replace(old_sched, new_sched, 1)

old_init_tail = '''            if type == .ended {
                self.restartPersistentAudio()
            }
        }
    }'''
new_init_tail = '''            if type == .ended {
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
    }'''
if old_init_tail not in text:
    raise SystemExit("v0.14.5 audio observer anchor missing")
text = text.replace(old_init_tail, new_init_tail, 1)

old_foreground = '''    func applicationWillEnterForeground(_ application: UIApplication) {
        VexBackgroundAgent.shared.endBackgroundGrace(using: application)
    }'''
new_foreground = '''    func applicationWillEnterForeground(_ application: UIApplication) {
        VexBackgroundAgent.shared.endBackgroundGrace(using: application)
        VexBackgroundAgent.shared.startPersistentAgent()
        VexBackgroundAgent.shared.schedule()
    }'''
if old_foreground not in text:
    raise SystemExit("v0.14.5 foreground reentry anchor missing")
text = text.replace(old_foreground, new_foreground, 1)

BG.write_text(text, encoding="utf-8")

final = BG.read_text(encoding="utf-8")
for marker in [
    "V145_ROAMING_PERSISTENCE",
    'relayURLs(path: "/phone/wait")',
    "request.timeoutInterval = 35",
    "500_000_000",
    "cancel(taskRequestWithIdentifier:",
    "AVAudioSession.routeChangeNotification",
    "AVAudioSession.mediaServicesWereResetNotification",
]:
    if marker not in final:
        raise SystemExit(f"missing v0.14.5 marker: {marker}")

print("PASS v0.14.5 roaming persistence patch")
