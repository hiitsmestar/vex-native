#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOICE = ROOT / "VexNative" / "VexVoiceIntents.swift"
BG = ROOT / "VexNative" / "VexBackgroundAgent.swift"

voice = VOICE.read_text(encoding="utf-8")
if "V149_SERIALIZED_FOREGROUND_WAKE" in voice:
    print("PASS v0.14.9 serialized foreground wake already applied")
    raise SystemExit(0)

old = '''        if wake == "wake and check remote relay" {
            // V148_FOREGROUND_READY_HANDOFF
            UserDefaults.standard.set(true, forKey: "vex.phone.foregroundWake.pending")
            return .result(dialog: "Ready.")
        }'''
new = '''        if wake == "wake and check remote relay" {
            // V149_SERIALIZED_FOREGROUND_WAKE
            UserDefaults.standard.set(true, forKey: "vex.phone.foregroundWake.pending")
            VexBackgroundAgent.shared.stopForegroundLoop()
            if UIApplication.shared.applicationState == .active {
                VexBackgroundAgent.shared.handleForegroundWake()
            }
            return .result(dialog: "Ready.")
        }'''
if old not in voice:
    raise SystemExit("v0.14.9 voice anchor missing")
VOICE.write_text(voice.replace(old, new, 1), encoding="utf-8")

bg = BG.read_text(encoding="utf-8")
old_active = '''    func applicationDidBecomeActive(_ application: UIApplication) {
        VexBackgroundAgent.shared.startPersistentAgent()
        VexBackgroundAgent.shared.startForegroundLoop()

        let defaults = UserDefaults.standard
        guard defaults.bool(forKey: "vex.phone.foregroundWake.pending") else { return }
        defaults.set(false, forKey: "vex.phone.foregroundWake.pending")

        Task { @MainActor in
            try? await Task.sleep(nanoseconds: 750_000_000)
            _ = await VexPhoneBackgroundWorker.runOnce()
        }
    }'''
new_active = '''    func applicationDidBecomeActive(_ application: UIApplication) {
        VexBackgroundAgent.shared.startPersistentAgent()
        VexBackgroundAgent.shared.handleForegroundWake()
    }'''
if old_active not in bg:
    raise SystemExit("v0.14.9 lifecycle anchor missing")
bg = bg.replace(old_active, new_active, 1)

old_prop = '''    private var foregroundTask: Task<Void, Never>?
    private var backgroundGraceTask: Task<Void, Never>?'''
new_prop = '''    private var foregroundTask: Task<Void, Never>?
    private var foregroundWakeTask: Task<Void, Never>?
    private var backgroundGraceTask: Task<Void, Never>?'''
if old_prop not in bg:
    raise SystemExit("v0.14.9 property anchor missing")
bg = bg.replace(old_prop, new_prop, 1)

old_loop = '''    func startForegroundLoop() {
        guard foregroundTask == nil else { return }
        foregroundTask = Task {'''
new_loop = '''    func startForegroundLoop() {
        guard !UserDefaults.standard.bool(forKey: "vex.phone.foregroundWake.pending") else { return }
        guard foregroundWakeTask == nil else { return }
        guard foregroundTask == nil else { return }
        foregroundTask = Task {'''
if old_loop not in bg:
    raise SystemExit("v0.14.9 loop anchor missing")
bg = bg.replace(old_loop, new_loop, 1)

anchor = '''    func stopForegroundLoop() {
        foregroundTask?.cancel()
        foregroundTask = nil
    }
'''
insert = '''    func stopForegroundLoop() {
        foregroundTask?.cancel()
        foregroundTask = nil
    }

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
            _ = await VexPhoneBackgroundWorker.runOnce()
            self.foregroundWakeTask = nil
            self.startForegroundLoop()
        }
    }
'''
if anchor not in bg:
    raise SystemExit("v0.14.9 stop-loop anchor missing")
bg = bg.replace(anchor, insert, 1)
BG.write_text(bg, encoding="utf-8")

final_voice = VOICE.read_text(encoding="utf-8")
final_bg = BG.read_text(encoding="utf-8")
for marker in ["V149_SERIALIZED_FOREGROUND_WAKE", "stopForegroundLoop()", "handleForegroundWake()"]:
    if marker not in final_voice:
        raise SystemExit(f"missing v0.14.9 voice marker: {marker}")
for marker in ["foregroundWakeTask", "handleForegroundWake()", "guard foregroundWakeTask == nil"]:
    if marker not in final_bg:
        raise SystemExit(f"missing v0.14.9 background marker: {marker}")
print("PASS v0.14.9 serialized foreground wake patch")
