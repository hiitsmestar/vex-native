#!/usr/bin/env python3
from pathlib import Path

path = Path("VexNative/ContentView.swift")
text = path.read_text(encoding="utf-8")


def once(old: str, new: str, label: str):
    global text
    if old not in text:
        raise SystemExit(f"{label}: source block not found")
    text = text.replace(old, new, 1)


once(
    '    @StateObject private var voice = VoiceConversationController()\n',
    '    @StateObject private var voice = VoiceConversationController()\n    @State private var showVoiceSettings = false\n',
    "voice settings state",
)
once(
    'final class VoiceConversationController: NSObject, ObservableObject, AVSpeechSynthesizerDelegate {',
    'final class VoiceConversationController: NSObject, ObservableObject, AVSpeechSynthesizerDelegate, AVAudioPlayerDelegate {',
    "audio player delegate",
)
once(
    '    @Published private(set) var replyMode: ReplyMode = ReplyMode.saved\n',
    '''    @Published private(set) var replyMode: ReplyMode = ReplyMode.saved
    @Published private(set) var speechEngine: SpeechEngine = SpeechEngine.saved
    @Published private(set) var neuralVoice: NeuralVoice = NeuralVoice.saved
    @Published private(set) var neuralRate: Double = UserDefaults.standard.object(forKey: "vex.voice.neuralRate.v1") as? Double ?? 0
    @Published private(set) var neuralPitch: Double = UserDefaults.standard.object(forKey: "vex.voice.neuralPitch.v1") as? Double ?? 0
''',
    "neural voice state",
)
once(
    '    private let synthesizer = AVSpeechSynthesizer()\n',
    '''    private let synthesizer = AVSpeechSynthesizer()
    private var neuralPlayer: AVAudioPlayer?
    private var neuralRequestInFlight = false
    private var speechTask: Task<Void, Never>?
''',
    "neural player state",
)

old_speak = '''    func speak(_ rawText: String) {
        guard isHandsFree, replyMode != .textOnly else { return }
        waitingForReply = false
        stopRecognition()
        let text = Self.spokenText(rawText)
        guard !text.isEmpty else { restartListeningSoon(); return }
        synthesizer.stopSpeaking(at: .immediate)
        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = Self.preferredVexVoice()
        utterance.rate = 0.49
        utterance.pitchMultiplier = 1.08
        utterance.volume = 1.0
        synthesizer.speak(utterance)
    }
'''
new_speak = '''    func speak(_ rawText: String) {
        guard isHandsFree, replyMode != .textOnly else { return }
        waitingForReply = false
        stopRecognition()
        let text = Self.spokenText(rawText)
        guard !text.isEmpty else { restartListeningSoon(); return }
        beginSpeech(text)
    }

    func previewVoice() {
        waitingForReply = false
        stopRecognition()
        beginSpeech("Hey Star. Much better. I refuse to sound like a haunted GPS.")
    }

    private func beginSpeech(_ text: String) {
        speechTask?.cancel()
        synthesizer.stopSpeaking(at: .immediate)
        neuralPlayer?.stop()
        neuralPlayer = nil
        speechTask = Task { [weak self] in
            guard let self else { return }
            await self.speakPrepared(text)
        }
    }

    private func speakPrepared(_ text: String) async {
        if speechEngine == .pcNeural {
            neuralRequestInFlight = true
            let audio = await fetchNeuralAudio(text)
            neuralRequestInFlight = false
            if Task.isCancelled { return }
            if let audio, playNeuralAudio(audio) { return }
        }
        speakWithSystemVoice(text)
    }

    private func speakWithSystemVoice(_ text: String) {
        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = Self.preferredVexVoice()
        utterance.rate = 0.50
        utterance.pitchMultiplier = 1.03
        utterance.volume = 1.0
        synthesizer.speak(utterance)
    }

    private func playNeuralAudio(_ data: Data) -> Bool {
        do {
            let player = try AVAudioPlayer(data: data)
            player.delegate = self
            player.prepareToPlay()
            neuralPlayer = player
            return player.play()
        } catch {
            neuralPlayer = nil
            return false
        }
    }

    private func fetchNeuralAudio(_ text: String) async -> Data? {
        for endpoint in Self.configuredBridgeEndpoints() {
            guard let root = URL(string: endpoint),
                  VexBridgeNetworking.isBridgeURL(root),
                  var components = URLComponents(url: root, resolvingAgainstBaseURL: false)
            else { continue }
            components.path = "/tts/speak"
            guard let url = components.url else { continue }

            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.timeoutInterval = 18
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try? JSONSerialization.data(withJSONObject: [
                "text": String(text.prefix(1800)),
                "voice": neuralVoice.rawValue,
                "rate": Int(neuralRate.rounded()),
                "pitch": Int(neuralPitch.rounded())
            ])

            do {
                let (data, response) = try await VexBridgeNetworking.data(for: request)
                guard let http = response as? HTTPURLResponse,
                      (200...299).contains(http.statusCode),
                      let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                      (json["ok"] as? Bool) == true,
                      let encoded = json["audio_base64"] as? String,
                      let audio = Data(base64Encoded: encoded), !audio.isEmpty
                else { continue }
                return audio
            } catch {
                continue
            }
        }
        return nil
    }

    private static func configuredBridgeEndpoints() -> [String] {
        let defaults = UserDefaults.standard
        let primary = defaults.string(forKey: WebBrain.searxEndpointKey)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let secondary = defaults.string(forKey: WebBrain.secondaryBridgeEndpointKey)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        var endpoints: [String] = []
        if !primary.isEmpty { endpoints.append(primary) }
        if !secondary.isEmpty, secondary != primary { endpoints.append(secondary) }
        return endpoints
    }

    private var isSpeechOutputActive: Bool {
        synthesizer.isSpeaking || neuralRequestInFlight || (neuralPlayer?.isPlaying ?? false)
    }
'''
once(old_speak, new_speak, "neural speech pipeline")

once(
    '''        wakeArmedUntil = nil
        voiceHint = "Voice off"
        synthesizer.stopSpeaking(at: .immediate)
        stopRecognition()
''',
    '''        wakeArmedUntil = nil
        voiceHint = "Voice off"
        speechTask?.cancel()
        speechTask = nil
        neuralRequestInFlight = false
        neuralPlayer?.stop()
        neuralPlayer = nil
        synthesizer.stopSpeaking(at: .immediate)
        stopRecognition()
''',
    "stop all voice output",
)
text = text.replace('!synthesizer.isSpeaking, !waitingForReply', '!isSpeechOutputActive, !waitingForReply')
text = text.replace('!self.synthesizer.isSpeaking, !self.waitingForReply', '!self.isSpeechOutputActive, !self.waitingForReply')

old_preferred = '''    private static func preferredVexVoice() -> AVSpeechSynthesisVoice? {
        let english = AVSpeechSynthesisVoice.speechVoices().filter { $0.language.lowercased().hasPrefix("en-us") }
        let preferredNames = ["Ava", "Samantha", "Zoe", "Nicky"]
        for wanted in preferredNames {
            if let voice = english.first(where: { $0.name.localizedCaseInsensitiveContains(wanted) }) {
                return voice
            }
        }
        return AVSpeechSynthesisVoice(language: "en-US")
    }
'''
new_preferred = '''    private static func preferredVexVoice() -> AVSpeechSynthesisVoice? {
        let english = AVSpeechSynthesisVoice.speechVoices().filter { $0.language.lowercased().hasPrefix("en-us") }
        let preferredNames = ["Ava", "Samantha", "Zoe", "Nicky"]
        let named = english.filter { voice in
            preferredNames.contains(where: { voice.name.localizedCaseInsensitiveContains($0) })
        }
        func qualityScore(_ voice: AVSpeechSynthesisVoice) -> Int {
            if voice.quality == .premium { return 3 }
            if voice.quality == .enhanced { return 2 }
            return 1
        }
        if let best = named.max(by: { qualityScore($0) < qualityScore($1) }) { return best }
        return AVSpeechSynthesisVoice(language: "en-US")
    }
'''
once(old_preferred, new_preferred, "better system fallback voice")

reply_mode_marker = '    enum ReplyMode: String, CaseIterable, Identifiable {\n'
if reply_mode_marker not in text:
    raise SystemExit("ReplyMode marker missing")
voice_options = r'''    enum SpeechEngine: String, CaseIterable, Identifiable {
        case pcNeural
        case iphone
        var id: String { rawValue }
        var title: String { self == .pcNeural ? "PC Neural (online)" : "iPhone Local" }
        static var saved: SpeechEngine {
            guard let raw = UserDefaults.standard.string(forKey: "vex.voice.engine.v1"),
                  let value = SpeechEngine(rawValue: raw) else { return .pcNeural }
            return value
        }
    }

    enum NeuralVoice: String, CaseIterable, Identifiable {
        case ava = "en-US-AvaMultilingualNeural"
        case emma = "en-US-EmmaMultilingualNeural"
        case jenny = "en-US-JennyNeural"
        case aria = "en-US-AriaNeural"
        case michelle = "en-US-MichelleNeural"
        var id: String { rawValue }
        var title: String {
            switch self {
            case .ava: return "Ava"
            case .emma: return "Emma"
            case .jenny: return "Jenny"
            case .aria: return "Aria"
            case .michelle: return "Michelle"
            }
        }
        static var saved: NeuralVoice {
            guard let raw = UserDefaults.standard.string(forKey: "vex.voice.neuralVoice.v1"),
                  let value = NeuralVoice(rawValue: raw) else { return .ava }
            return value
        }
    }

    func setSpeechEngine(_ engine: SpeechEngine) {
        speechEngine = engine
        UserDefaults.standard.set(engine.rawValue, forKey: "vex.voice.engine.v1")
        voiceHint = engine == .pcNeural ? "Voice: PC neural" : "Voice: iPhone local"
    }

    func setNeuralVoice(_ value: NeuralVoice) {
        neuralVoice = value
        UserDefaults.standard.set(value.rawValue, forKey: "vex.voice.neuralVoice.v1")
    }

    func setNeuralRate(_ value: Double) {
        neuralRate = min(30, max(-30, value))
        UserDefaults.standard.set(neuralRate, forKey: "vex.voice.neuralRate.v1")
    }

    func setNeuralPitch(_ value: Double) {
        neuralPitch = min(35, max(-35, value))
        UserDefaults.standard.set(neuralPitch, forKey: "vex.voice.neuralPitch.v1")
    }

'''
text = text.replace(reply_mode_marker, voice_options + reply_mode_marker, 1)

callback_marker = '''    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance) {
        Task { @MainActor [weak self] in self?.restartListeningSoon() }
    }

'''
callbacks = callback_marker + '''    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor [weak self] in
            self?.neuralPlayer = nil
            self?.restartListeningSoon()
        }
    }

    nonisolated func audioPlayerDecodeErrorDidOccur(_ player: AVAudioPlayer, error: Error?) {
        Task { @MainActor [weak self] in
            self?.neuralPlayer = nil
            self?.restartListeningSoon()
        }
    }

'''
once(callback_marker, callbacks, "neural playback callbacks")

menu_tail = '''                ForEach(VoiceConversationController.ReplyMode.allCases) { mode in
                    Button {
                        voice.setReplyMode(mode)
                    } label: {
                        Label(mode.title, systemImage: mode.symbol)
                    }
                }
'''
menu_new = menu_tail + '''                Divider()
                Button {
                    showVoiceSettings = true
                } label: {
                    Label("Tune Vex voice…", systemImage: "slider.horizontal.3")
                }
'''
once(menu_tail, menu_new, "voice settings menu entry")
once(
    '        .onDisappear { voice.stopHandsFree() }\n',
    '''        .onDisappear { voice.stopHandsFree() }
        .sheet(isPresented: $showVoiceSettings) {
            VexVoiceSettingsView(voice: voice)
        }
''',
    "voice settings sheet",
)

web_marker = '// MARK: - Web Brain v0.6\n'
if web_marker not in text:
    raise SystemExit("Web Brain marker missing")
settings_view = r'''private struct VexVoiceSettingsView: View {
    @ObservedObject var voice: VoiceConversationController
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section("Voice engine") {
                    Picker("Engine", selection: Binding(
                        get: { voice.speechEngine },
                        set: { voice.setSpeechEngine($0) }
                    )) {
                        ForEach(VoiceConversationController.SpeechEngine.allCases) { engine in
                            Text(engine.title).tag(engine)
                        }
                    }
                    .pickerStyle(.segmented)
                    Text(voice.speechEngine == .pcNeural
                         ? "Natural neural speech through either paired Vex Bridge. Falls back to the iPhone voice if both PCs or the internet are unavailable."
                         : "Fully local iPhone speech with the best installed Vex-like system voice.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                if voice.speechEngine == .pcNeural {
                    Section("Vex voice") {
                        Picker("Voice", selection: Binding(
                            get: { voice.neuralVoice },
                            set: { voice.setNeuralVoice($0) }
                        )) {
                            ForEach(VoiceConversationController.NeuralVoice.allCases) { item in
                                Text(item.title).tag(item)
                            }
                        }
                        VStack(alignment: .leading) {
                            Text("Speed  \(Int(voice.neuralRate))%")
                            Slider(value: Binding(
                                get: { voice.neuralRate },
                                set: { voice.setNeuralRate($0) }
                            ), in: -30...30, step: 5)
                        }
                        VStack(alignment: .leading) {
                            Text("Pitch  \(Int(voice.neuralPitch)) Hz")
                            Slider(value: Binding(
                                get: { voice.neuralPitch },
                                set: { voice.setNeuralPitch($0) }
                            ), in: -35...35, step: 5)
                        }
                    }
                }

                Section {
                    Button("Preview Vex") { voice.previewVoice() }
                }
            }
            .navigationTitle("Vex Voice")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}

'''
text = text.replace(web_marker, settings_view + web_marker, 1)

path.write_text(text, encoding="utf-8")
for marker in ["PC Neural (online)", "audio_base64", "VexVoiceSettingsView", "Preview Vex"]:
    if marker not in text:
        raise SystemExit(f"missing v0.9.0 neural voice marker: {marker}")
print("Applied v0.9.0 configurable Bridge neural voice patch")
