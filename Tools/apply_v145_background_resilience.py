#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BG = ROOT / "VexNative" / "VexBackgroundAgent.swift"

text = BG.read_text(encoding="utf-8")
if "V145_BACKGROUND_RESILIENCE" in text:
    print("PASS v0.14.5 background resilience already applied")
    raise SystemExit(0)

if 'private let V140_PERSISTENT_PHONE_AGENT = "v0.14.0-persistent-phone-agent-v1"' not in text:
    raise SystemExit("v0.14.5 persistent-agent marker missing")

text = text.replace(
    'private let V140_PERSISTENT_PHONE_AGENT = "v0.14.0-persistent-phone-agent-v1"\n',
    'private let V140_PERSISTENT_PHONE_AGENT = "v0.14.0-persistent-phone-agent-v1"\n'
    'private let V145_BACKGROUND_RESILIENCE = "v0.14.5-background-resilience-v4"\n',
    1,
)

if "private var heartbeatBuffer: AVAudioPCMBuffer?" not in text:
    raise SystemExit("v0.14.5 heartbeat buffer anchor missing")
text = text.replace(
    "private var heartbeatBuffer: AVAudioPCMBuffer?",
    "private var heartbeatBuffer: AVAudioPCMBuffer?\n    private var resilienceWatchdogTask: Task<Void, Never>?",
    1,
)

old_guard = '''        guard !persistentAgentStarted else {
            if !audioEngine.isRunning || !audioPlayer.isPlaying {
                restartPersistentAudio()
            }
            startForegroundLoop()
            return
        }'''
new_guard = '''        guard !persistentAgentStarted else {
            if !audioEngine.isRunning || !audioPlayer.isPlaying {
                restartPersistentAudio()
            }
            startForegroundLoop()
            startResilienceWatchdog()
            return
        }'''
if old_guard not in text:
    raise SystemExit("v0.14.5 persistent-agent guard anchor missing")
text = text.replace(old_guard, new_guard, 1)

old_success = '''            UserDefaults.standard.set(Date(), forKey: "vex.phone.persistentAgent.startedAt")
            startForegroundLoop()'''
new_success = '''            UserDefaults.standard.set(Date(), forKey: "vex.phone.persistentAgent.startedAt")
            startForegroundLoop()
            startResilienceWatchdog()'''
if old_success not in text:
    raise SystemExit("v0.14.5 persistent-agent success anchor missing")
text = text.replace(old_success, new_success, 1)

anchor = '''    func startForegroundLoop() {
        guard foregroundTask == nil else { return }'''
insert = '''    func startResilienceWatchdog() {
        guard resilienceWatchdogTask == nil else { return }

        resilienceWatchdogTask = Task { [weak self] in
            while !Task.isCancelled {
                guard let self else { return }

                await MainActor.run {
                    if !self.audioEngine.isRunning || !self.audioPlayer.isPlaying {
                        self.restartPersistentAudio()
                    }
                    UserDefaults.standard.set(
                        Date(),
                        forKey: "vex.phone.background.watchdogHeartbeat"
                    )
                }

                _ = await VexPhoneBackgroundWorker.runOnce()
                try? await Task.sleep(nanoseconds: 10_000_000_000)
            }
        }
    }

    func startForegroundLoop() {
        guard foregroundTask == nil else { return }'''
if anchor not in text:
    raise SystemExit("v0.14.5 foreground loop anchor missing")
text = text.replace(anchor, insert, 1)

# Make the background transition explicitly kick the watchdog too.
bg_anchor = '''        VexBackgroundAgent.shared.startPersistentAgent()
        VexBackgroundAgent.shared.startForegroundLoop()
        VexBackgroundAgent.shared.startBackgroundGrace(using: application)'''
bg_new = '''        VexBackgroundAgent.shared.startPersistentAgent()
        VexBackgroundAgent.shared.startForegroundLoop()
        VexBackgroundAgent.shared.startResilienceWatchdog()
        VexBackgroundAgent.shared.startBackgroundGrace(using: application)'''
if bg_anchor in text:
    text = text.replace(bg_anchor, bg_new, 1)

BG.write_text(text, encoding="utf-8")

final = BG.read_text(encoding="utf-8")
for marker in [
    'V145_BACKGROUND_RESILIENCE = "v0.14.5-background-resilience-v4"',
    "resilienceWatchdogTask",
    "startResilienceWatchdog()",
    "vex.phone.background.watchdogHeartbeat",
    "restartPersistentAudio()",
    "VexPhoneBackgroundWorker.runOnce()",
    "refreshRoamingBootstrap()",
]:
    if marker not in final:
        raise SystemExit(f"missing v0.14.5 marker: {marker}")

print("PASS v0.14.5 background resilience patch")
