#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BG = ROOT / "VexNative" / "VexBackgroundAgent.swift"

text = BG.read_text(encoding="utf-8")
if "V140_PERSISTENT_PHONE_AGENT" in text:
    print("PASS v0.14.0 persistent phone agent already applied")
    raise SystemExit(0)

if "import AVFoundation\n" not in text:
    text = text.replace("import BackgroundTasks\n", "import AVFoundation\nimport BackgroundTasks\n", 1)

text = text.replace(
    'private let V139_AGENT_LIFECYCLE_KEEPALIVE = "v0.13.9-agent-lifecycle-keepalive-v1"\n',
    'private let V139_AGENT_LIFECYCLE_KEEPALIVE = "v0.13.9-agent-lifecycle-keepalive-v1"\n'
    'private let V140_PERSISTENT_PHONE_AGENT = "v0.14.0-persistent-phone-agent-v1"\n',
    1,
)

text = text.replace(
'''        VexBackgroundAgent.shared.register()
        VexBackgroundAgent.shared.schedule()
        return true''',
'''        VexBackgroundAgent.shared.register()
        VexBackgroundAgent.shared.schedule()
        VexBackgroundAgent.shared.startPersistentAgent()
        return true''',
1)

text = text.replace(
'''    func applicationDidBecomeActive(_ application: UIApplication) {
        VexBackgroundAgent.shared.startForegroundLoop()
    }

    func applicationWillResignActive(_ application: UIApplication) {
        VexBackgroundAgent.shared.stopForegroundLoop()
    }''',
'''    func applicationDidBecomeActive(_ application: UIApplication) {
        VexBackgroundAgent.shared.startPersistentAgent()
        VexBackgroundAgent.shared.startForegroundLoop()
    }

    func applicationWillResignActive(_ application: UIApplication) {
        // v0.14.0: keep the command loop alive. The background audio session
        // is the execution anchor once the app leaves the foreground.
    }''',
1)

text = text.replace(
'''        VexBackgroundAgent.shared.schedule()
        VexBackgroundAgent.shared.startBackgroundGrace(using: application)''',
'''        VexBackgroundAgent.shared.schedule()
        VexBackgroundAgent.shared.startPersistentAgent()
        VexBackgroundAgent.shared.startForegroundLoop()
        VexBackgroundAgent.shared.startBackgroundGrace(using: application)''',
1)

text = text.replace(
'''    private var foregroundTask: Task<Void, Never>?
    private var backgroundGraceTask: Task<Void, Never>?
    private var backgroundTaskIdentifier: UIBackgroundTaskIdentifier = .invalid
    private init() {}''',
'''    private var foregroundTask: Task<Void, Never>?
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
    }''',
1)

anchor='''    func startForegroundLoop() {
        guard foregroundTask == nil else { return }'''
insert='''    func startPersistentAgent() {
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
        guard foregroundTask == nil else { return }'''
if anchor not in text:
    raise SystemExit("v0.14.0 foreground loop anchor missing")
text = text.replace(anchor, insert, 1)

BG.write_text(text, encoding="utf-8")

final = BG.read_text(encoding="utf-8")
for marker in [
    'V140_PERSISTENT_PHONE_AGENT = "v0.14.0-persistent-phone-agent-v1"',
    "import AVFoundation",
    "startPersistentAgent()",
    "AVAudioSession.sharedInstance()",
    "AVAudioPlayerNode()",
    "audioPlayer.scheduleBuffer",
    "options: [.loops]",
    "vex.phone.persistentAgent.active",
    "VexPhoneBackgroundWorker.runOnce()",
]:
    if marker not in final:
        raise SystemExit(f"v0.14.0 marker missing: {marker}")

print("PASS v0.14.0 persistent phone agent patch")
