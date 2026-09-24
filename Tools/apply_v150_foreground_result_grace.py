#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BG = ROOT / "VexNative" / "VexBackgroundAgent.swift"

bg = BG.read_text(encoding="utf-8")
if "V150_FOREGROUND_RESULT_GRACE" in bg:
    print("PASS v0.15.0 foreground result grace already applied")
    raise SystemExit(0)

old_prop = '''    private var foregroundWakeTask: Task<Void, Never>?
    private var backgroundGraceTask: Task<Void, Never>?'''
new_prop = '''    private var foregroundWakeTask: Task<Void, Never>?
    private var foregroundWakeBackgroundTaskIdentifier: UIBackgroundTaskIdentifier = .invalid
    private var backgroundGraceTask: Task<Void, Never>?'''
if old_prop not in bg:
    raise SystemExit("v0.15.0 property anchor missing")
bg = bg.replace(old_prop, new_prop, 1)

old = '''    @MainActor
    func handleForegroundWake() {
        let defaults = UserDefaults.standard
        guard defaults.bool(forKey: "vex.phone.foregroundWake.pending") else { return }
        defaults.set(false, forKey: "vex.phone.foregroundWake.pending")

        stopForegroundLoop()
        foregroundWakeTask?.cancel()
        foregroundWakeTask = Task { @MainActor [weak self] in
            try? await Task.sleep(nanoseconds: 750_000_000)
            guard !Task.isCancelled, let self else { return }
            _ = await VexPhoneBackgroundWorker.runOnce()
            self.foregroundWakeTask = nil
            self.startForegroundLoop()
        }
    }
'''
new = '''    // V150_FOREGROUND_RESULT_GRACE
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
'''
if old not in bg:
    raise SystemExit("v0.15.0 wake anchor missing")
bg = bg.replace(old, new, 1)
BG.write_text(bg, encoding="utf-8")

final = BG.read_text(encoding="utf-8")
for marker in [
    "V150_FOREGROUND_RESULT_GRACE",
    "foregroundWakeBackgroundTaskIdentifier",
    "beginForegroundWakeResultGrace()",
    "endForegroundWakeResultGrace()",
    "VexForegroundWakeResult",
]:
    if marker not in final:
        raise SystemExit(f"missing v0.15.0 marker: {marker}")
print("PASS v0.15.0 foreground result grace patch")
