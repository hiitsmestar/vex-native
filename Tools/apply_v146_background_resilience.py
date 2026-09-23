#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BG = ROOT / "VexNative" / "VexBackgroundAgent.swift"

text = BG.read_text(encoding="utf-8")
if "V146_BACKGROUND_RESILIENCE" in text:
    print("PASS v0.14.6 background resilience already applied")
    raise SystemExit(0)

marker = 'private let V140_PERSISTENT_PHONE_AGENT = "v0.14.0-persistent-phone-agent-v1"\n'
if marker not in text:
    raise SystemExit("v0.14.6 persistent-agent marker missing")
text = text.replace(
    marker,
    marker + 'private let V146_BACKGROUND_RESILIENCE = "v0.14.6-background-resilience-v1"\n',
    1,
)

if "private var heartbeatBuffer: AVAudioPCMBuffer?" not in text:
    raise SystemExit("v0.14.6 heartbeat buffer anchor missing")
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
    raise SystemExit("v0.14.6 persistent-agent guard anchor missing")
text = text.replace(old_guard, new_guard, 1)

old_success = '''            UserDefaults.standard.set(Date(), forKey: "vex.phone.persistentAgent.startedAt")
            startForegroundLoop()'''
new_success = '''            UserDefaults.standard.set(Date(), forKey: "vex.phone.persistentAgent.startedAt")
            startForegroundLoop()
            startResilienceWatchdog()'''
if old_success not in text:
    raise SystemExit("v0.14.6 persistent-agent success anchor missing")
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
    raise SystemExit("v0.14.6 foreground loop anchor missing")
text = text.replace(anchor, insert, 1)

bg_anchor = '''        VexBackgroundAgent.shared.startPersistentAgent()
        VexBackgroundAgent.shared.startForegroundLoop()
        VexBackgroundAgent.shared.startBackgroundGrace(using: application)'''
if bg_anchor in text:
    text = text.replace(
        bg_anchor,
        '''        VexBackgroundAgent.shared.startPersistentAgent()
        VexBackgroundAgent.shared.startForegroundLoop()
        VexBackgroundAgent.shared.startResilienceWatchdog()
        VexBackgroundAgent.shared.startBackgroundGrace(using: application)''',
        1,
    )

BG.write_text(text, encoding="utf-8")

final = BG.read_text(encoding="utf-8")
for required in [
    "V146_BACKGROUND_RESILIENCE",
    "resilienceWatchdogTask",
    "startResilienceWatchdog()",
    "vex.phone.background.watchdogHeartbeat",
    "restartPersistentAudio()",
    "VexPhoneBackgroundWorker.runOnce()",
    "V144_GITHUB_ROAMING_BOOTSTRAP",
    "refreshRoamingBootstrap()",
]:
    if required not in final:
        raise SystemExit(f"missing v0.14.6 marker: {required}")

print("PASS v0.14.6 background resilience patch")
