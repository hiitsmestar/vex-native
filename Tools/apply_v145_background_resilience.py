#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BG = ROOT / "VexNative" / "VexBackgroundAgent.swift"

text = BG.read_text(encoding="utf-8")
if "V145_BACKGROUND_RESILIENCE" in text:
    print("PASS v0.14.5 background resilience already applied")
    raise SystemExit(0)

text = text.replace(
    'private let V140_PERSISTENT_PHONE_AGENT = "v0.14.0-persistent-phone-agent-v1"\n',
    'private let V140_PERSISTENT_PHONE_AGENT = "v0.14.0-persistent-phone-agent-v1"\n'
    'private let V145_BACKGROUND_RESILIENCE = "v0.14.5-background-resilience-v3"\n',
    1,
)

text = text.replace(
    '''    private var persistentAgentStarted = false
    private var heartbeatBuffer: AVAudioPCMBuffer?''',
    '''    private var persistentAgentStarted = false
    private var heartbeatBuffer: AVAudioPCMBuffer?
    private var resilienceWatchdogTask: Task<Void, Never>?''',
    1,
)

old_init_tail = '''            if type == .ended {
                self.restartPersistentAudio()
            }
        }
    }

    func startPersistentAgent() {'''

new_init_tail = '''            if type == .ended {
                self.restartPersistentAudio()
                self.startResilienceWatchdog()
            }
        }

        NotificationCenter.default.addObserver(
            forName: AVAudioSession.routeChangeNotification,
            object: AVAudioSession.sharedInstance(),
            queue: .main
        ) { [weak self] _ in
            guard let self else { return }
            self.restartPersistentAudio()
            self.startResilienceWatchdog()
        }
    }

    func startPersistentAgent() {'''

if old_init_tail not in text:
    raise SystemExit("v0.14.5 init/notification anchor missing")
text = text.replace(old_init_tail, new_init_tail, 1)

text = text.replace(
    '''        guard !persistentAgentStarted else {
            if !audioEngine.isRunning || !audioPlayer.isPlaying {
                restartPersistentAudio()
            }
            startForegroundLoop()
            return
        }''',
    '''        guard !persistentAgentStarted else {
            if !audioEngine.isRunning || !audioPlayer.isPlaying {
                restartPersistentAudio()
            }
            startForegroundLoop()
            startResilienceWatchdog()
            return
        }''',
    1,
)

text = text.replace(
    '''            UserDefaults.standard.set(Date(), forKey: "vex.phone.persistentAgent.startedAt")
            startForegroundLoop()''',
    '''            UserDefaults.standard.set(Date(), forKey: "vex.phone.persistentAgent.startedAt")
            startForegroundLoop()
            startResilienceWatchdog()''',
    1,
)

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

text = text.replace(
    '''        VexBackgroundAgent.shared.startPersistentAgent()
        VexBackgroundAgent.shared.startForegroundLoop()''',
    '''        VexBackgroundAgent.shared.startPersistentAgent()
        VexBackgroundAgent.shared.startForegroundLoop()
        VexBackgroundAgent.shared.startResilienceWatchdog()''',
    1,
)

BG.write_text(text, encoding="utf-8")

final = BG.read_text(encoding="utf-8")
for marker in [
    'V145_BACKGROUND_RESILIENCE = "v0.14.5-background-resilience-v3"',
    "resilienceWatchdogTask",
    "startResilienceWatchdog()",
    "AVAudioSession.routeChangeNotification",
    "vex.phone.background.watchdogHeartbeat",
    "restartPersistentAudio()",
    "VexPhoneBackgroundWorker.runOnce()",
    "refreshRoamingBootstrap()",
]:
    if marker not in final:
        raise SystemExit(f"missing v0.14.5 marker: {marker}")

print("PASS v0.14.5 background resilience patch")
