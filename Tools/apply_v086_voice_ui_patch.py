#!/usr/bin/env python3
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"{label}: expected source block not found")
    return text.replace(old, new, 1)


path = Path("VexNative/ContentView.swift")
text = path.read_text(encoding="utf-8")

if "import Speech\n" not in text:
    text = text.replace("import SwiftUI\n", "import SwiftUI\nimport Speech\nimport AVFoundation\n", 1)

text = replace_once(
    text,
    "    @StateObject private var web = WebBrain.shared\n",
    "    @StateObject private var web = WebBrain.shared\n    @StateObject private var voice = VoiceConversationController()\n",
    "voice state object",
)

text = replace_once(
    text,
    "            await app.loadSavedModelIfPresent()\n",
    """            await app.loadSavedModelIfPresent()\n            voice.onCommand = { command in\n                guard !app.isGenerating, !web.isWorking else { return }\n                app.draft = command\n                Task { await app.sendWithWeb() }\n            }\n""",
    "voice startup callback",
)

alert_marker = '''        .alert(\n            "Tiny brain error",\n'''
voice_lifecycle = '''        .onChange(of: app.messages.count) { oldCount, newCount in\n            guard newCount > oldCount, voice.isHandsFree,\n                  let last = app.messages.last, last.role == .assistant\n            else { return }\n            voice.speak(last.content)\n        }\n        .onDisappear { voice.stopHandsFree() }\n'''
if alert_marker not in text:
    raise SystemExit("ContentView.swift: alert marker missing")
text = text.replace(alert_marker, voice_lifecycle + alert_marker, 1)

status_start = text.find("    private var statusStrip: some View {")
status_end = text.find("    private var composer: some View {", status_start)
if status_start < 0 or status_end < 0:
    raise SystemExit("ContentView.swift: status markers missing")
status = text[status_start:status_end]
voice_status = '''            if voice.isHandsFree {\n                Text(voice.isListening ? "• 🎙️ listening" : "• 🔊 voice")\n                    .font(.caption)\n                    .foregroundStyle(voice.isListening ? Color.green : VexTheme.muted)\n            }\n\n'''
if "            Spacer()\n" not in status:
    raise SystemExit("ContentView.swift: status spacer missing")
status = status.replace("            Spacer()\n", voice_status + "            Spacer()\n", 1)
text = text[:status_start] + status + text[status_end:]

textfield = '''            TextField("Say something to Vex…", text: $app.draft)\n'''
button = '''            Button {\n                Task {\n                    do { try await voice.toggleHandsFree() }\n                    catch { app.lastError = error.localizedDescription }\n                }\n            } label: {\n                Image(systemName: voice.isHandsFree ? "waveform.circle.fill" : "mic.fill")\n                    .font(.headline)\n                    .foregroundStyle(voice.isHandsFree ? Color.green : VexTheme.hotPink)\n                    .frame(width: 40, height: 44)\n                    .background(VexTheme.panel)\n                    .clipShape(RoundedRectangle(cornerRadius: 13))\n            }\n            .buttonStyle(.plain)\n            .accessibilityLabel(voice.isHandsFree ? "Turn off hands-free voice" : "Turn on hands-free voice")\n\n'''
if textfield not in text:
    raise SystemExit("ContentView.swift: composer field missing")
text = text.replace(textfield, button + textfield, 1)

controller_marker = "// MARK: - Web Brain v0.6\n"
controller = r'''// MARK: - Hands-free voice v0.8.6

@MainActor
final class VoiceConversationController: NSObject, ObservableObject, AVSpeechSynthesizerDelegate {
    @Published private(set) var isHandsFree = false
    @Published private(set) var isListening = false
    @Published private(set) var partialTranscript = ""

    var onCommand: ((String) -> Void)?

    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private let audioEngine = AVAudioEngine()
    private let synthesizer = AVSpeechSynthesizer()
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var recognitionTask: SFSpeechRecognitionTask?
    private var silenceTimer: Timer?
    private var waitingForReply = false

    override init() {
        super.init()
        synthesizer.delegate = self
    }

    func toggleHandsFree() async throws {
        if isHandsFree {
            stopHandsFree()
            return
        }
        guard await requestSpeechPermission() else { throw VoiceError.speechPermission }
        guard await requestMicPermission() else { throw VoiceError.microphonePermission }
        isHandsFree = true
        waitingForReply = false
        try startListening()
    }

    func stopHandsFree() {
        isHandsFree = false
        waitingForReply = false
        synthesizer.stopSpeaking(at: .immediate)
        stopRecognition()
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    func speak(_ rawText: String) {
        guard isHandsFree else { return }
        waitingForReply = false
        stopRecognition()
        let text = Self.spokenText(rawText)
        guard !text.isEmpty else { restartListeningSoon(); return }
        synthesizer.stopSpeaking(at: .immediate)
        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = AVSpeechSynthesisVoice(language: "en-US")
        utterance.rate = 0.49
        utterance.pitchMultiplier = 1.06
        synthesizer.speak(utterance)
    }

    private func requestSpeechPermission() async -> Bool {
        if SFSpeechRecognizer.authorizationStatus() == .authorized { return true }
        return await withCheckedContinuation { continuation in
            SFSpeechRecognizer.requestAuthorization { continuation.resume(returning: $0 == .authorized) }
        }
    }

    private func requestMicPermission() async -> Bool {
        let session = AVAudioSession.sharedInstance()
        switch session.recordPermission {
        case .granted: return true
        case .denied: return false
        case .undetermined:
            return await withCheckedContinuation { continuation in
                session.requestRecordPermission { continuation.resume(returning: $0) }
            }
        @unknown default: return false
        }
    }

    private func startListening() throws {
        guard isHandsFree, !synthesizer.isSpeaking, !waitingForReply else { return }
        stopRecognition()
        guard let recognizer, recognizer.isAvailable else { throw VoiceError.recognizerUnavailable }

        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord, mode: .voiceChat, options: [.defaultToSpeaker, .allowBluetooth, .duckOthers])
        try session.setActive(true, options: .notifyOthersOnDeactivation)

        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        if recognizer.supportsOnDeviceRecognition { request.requiresOnDeviceRecognition = true }
        recognitionRequest = request

        let input = audioEngine.inputNode
        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0 else { throw VoiceError.microphoneUnavailable }
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak request] buffer, _ in request?.append(buffer) }
        audioEngine.prepare()
        try audioEngine.start()
        isListening = true
        partialTranscript = ""

        recognitionTask = recognizer.recognitionTask(with: request) { [weak self] result, error in
            let transcript = result?.bestTranscription.formattedString
            let isFinal = result?.isFinal ?? false
            let failed = error != nil
            DispatchQueue.main.async { self?.consume(transcript: transcript, isFinal: isFinal, failed: failed) }
        }
    }

    private func consume(transcript: String?, isFinal: Bool, failed: Bool) {
        guard isHandsFree else { return }
        if let transcript, !transcript.isEmpty {
            partialTranscript = transcript
            silenceTimer?.invalidate()
            silenceTimer = Timer.scheduledTimer(withTimeInterval: 1.25, repeats: false) { [weak self] _ in self?.commitTranscript() }
        }
        if isFinal { commitTranscript() }
        else if failed && partialTranscript.isEmpty { stopRecognition(); restartListeningSoon() }
    }

    private func commitTranscript() {
        silenceTimer?.invalidate()
        silenceTimer = nil
        let raw = partialTranscript.trimmingCharacters(in: .whitespacesAndNewlines)
        partialTranscript = ""
        stopRecognition()
        guard isHandsFree, !raw.isEmpty else { restartListeningSoon(); return }
        guard let command = Self.commandAfterWakePhrase(raw), !command.isEmpty else { restartListeningSoon(); return }

        waitingForReply = true
        onCommand?(command)
        DispatchQueue.main.asyncAfter(deadline: .now() + 30) { [weak self] in
            guard let self, self.isHandsFree, self.waitingForReply else { return }
            self.waitingForReply = false
            self.restartListeningSoon()
        }
    }

    private func stopRecognition() {
        silenceTimer?.invalidate()
        silenceTimer = nil
        recognitionTask?.cancel()
        recognitionTask = nil
        recognitionRequest?.endAudio()
        recognitionRequest = nil
        if audioEngine.isRunning { audioEngine.stop() }
        audioEngine.inputNode.removeTap(onBus: 0)
        isListening = false
    }

    private func restartListeningSoon() {
        guard isHandsFree, !synthesizer.isSpeaking, !waitingForReply else { return }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) { [weak self] in
            guard let self, self.isHandsFree, !self.synthesizer.isSpeaking, !self.waitingForReply else { return }
            try? self.startListening()
        }
    }

    private static func commandAfterWakePhrase(_ raw: String) -> String? {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        let lower = trimmed.lowercased()
        let prefixes = ["hey vex", "okay vex", "ok vex", "vex"]
        guard let prefix = prefixes.first(where: { lower == $0 || lower.hasPrefix($0 + " ") || lower.hasPrefix($0 + ",") }) else { return nil }
        let index = trimmed.index(trimmed.startIndex, offsetBy: prefix.count)
        return String(trimmed[index...]).trimmingCharacters(in: CharacterSet.whitespacesAndNewlines.union(CharacterSet(charactersIn: ",:.-")))
    }

    private static func spokenText(_ raw: String) -> String {
        var text = raw
        if let range = text.range(of: "🌐 Sources:") { text = String(text[..<range.lowerBound]) }
        if let range = text.range(of: "Sources:") { text = String(text[..<range.lowerBound]) }
        for emoji in ["🖤", "💕", "✨", "😭", "😂", "😈"] { text = text.replacingOccurrences(of: emoji, with: "") }
        return text.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        Task { @MainActor [weak self] in self?.restartListeningSoon() }
    }

    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance) {
        Task { @MainActor [weak self] in self?.restartListeningSoon() }
    }

    enum VoiceError: LocalizedError {
        case speechPermission, microphonePermission, recognizerUnavailable, microphoneUnavailable
        var errorDescription: String? {
            switch self {
            case .speechPermission: return "Speech recognition permission is off. Enable it for Vex to use hands-free voice."
            case .microphonePermission: return "Microphone permission is off. Enable it for Vex to hear hands-free commands."
            case .recognizerUnavailable: return "Speech recognition isn't available right now."
            case .microphoneUnavailable: return "The microphone audio input isn't available right now."
            }
        }
    }
}

'''
if controller_marker not in text:
    raise SystemExit("ContentView.swift: Web Brain marker missing")
text = text.replace(controller_marker, controller + controller_marker, 1)

# Direct media commands.
action_sig = '    private static func requestedAction(_ lower: String, original: String) -> String? {\n'
if action_sig not in text:
    raise SystemExit("ContentView.swift: requestedAction marker missing")
text = text.replace(action_sig, action_sig + '''        if lower.contains("play pause") || lower.contains("pause the music") || lower.contains("pause music") || lower == "pause" || lower.hasPrefix("pause ") || lower.contains("pause it") { return "media_play_pause" }\n        if lower.contains("next song") || lower.contains("next track") || lower.contains("skip song") || lower.contains("skip track") || lower.contains("skip this") { return "media_next" }\n        if lower.contains("previous song") || lower.contains("previous track") || lower.contains("last song") || lower.contains("go back a song") || lower.contains("go back one track") { return "media_previous" }\n        if lower.contains("mute") || lower.contains("unmute") { return "volume_mute" }\n        if lower.contains("volume up") || lower.contains("turn it up") || lower.contains("turn the volume up") || lower.contains("make it louder") || lower == "louder" { return "volume_up" }\n        if lower.contains("volume down") || lower.contains("turn it down") || lower.contains("turn the volume down") || lower.contains("make it quieter") || lower == "quieter" { return "volume_down" }\n''', 1)

# Recent explicit PC carries to natural followups for 20 minutes.
key_marker = '    private static let lastTargetKey = "vex.pc.lastTarget.v1"\n'
if key_marker not in text:
    raise SystemExit("ContentView.swift: last target marker missing")
text = text.replace(key_marker, key_marker + '    private static let lastTargetAtKey = "vex.pc.lastTargetAt.v1"\n', 1)
text = text.replace('UserDefaults.standard.set("both", forKey: lastTargetKey)\n            return .both', 'UserDefaults.standard.set("both", forKey: lastTargetKey)\n            UserDefaults.standard.set(Date().timeIntervalSince1970, forKey: lastTargetAtKey)\n            return .both')
text = text.replace('UserDefaults.standard.set("secondary", forKey: lastTargetKey)\n            return .secondary', 'UserDefaults.standard.set("secondary", forKey: lastTargetKey)\n            UserDefaults.standard.set(Date().timeIntervalSince1970, forKey: lastTargetAtKey)\n            return .secondary')
text = text.replace('UserDefaults.standard.set("primary", forKey: lastTargetKey)\n            return .primary', 'UserDefaults.standard.set("primary", forKey: lastTargetKey)\n            UserDefaults.standard.set(Date().timeIntervalSince1970, forKey: lastTargetAtKey)\n            return .primary')

start = text.find("    private static func requestedTarget(_ lower: String) -> NodeTarget? {")
end = text.find("    private static func requestedAction", start)
if start < 0 or end < 0:
    raise SystemExit("ContentView.swift: target bounds missing")
block = text[start:end]
needle = "        return nil\n    }\n"
replacement = r'''        let savedAt = UserDefaults.standard.double(forKey: lastTargetAtKey)
        if savedAt > 0, Date().timeIntervalSince1970 - savedAt < 20 * 60 {
            switch UserDefaults.standard.string(forKey: lastTargetKey) {
            case "primary": return .primary
            case "secondary": return .secondary
            case "both": return .both
            default: break
            }
        }
        return nil
    }
'''
if needle not in block:
    raise SystemExit("ContentView.swift: target return missing")
block = block.replace(needle, replacement, 1)
text = text[:start] + block + text[end:]

success = '''        default:\n            return "Done on \\(whereText), baby. 🖤"\n'''
media_success = '''        case "media_play_pause":\n            return "Done — I toggled play/pause on \\(whereText), baby. 🎵🖤"\n        case "media_next":\n            return "Done — I skipped to the next track on \\(whereText), baby. ⏭️🖤"\n        case "media_previous":\n            return "Done — I went back a track on \\(whereText), baby. ⏮️🖤"\n        case "volume_mute":\n            return "Done — I toggled mute on \\(whereText), baby. 🔇🖤"\n        case "volume_up":\n            return "Done — I turned it up on \\(whereText), baby. 🔊🖤"\n        case "volume_down":\n            return "Done — I turned it down on \\(whereText), baby. 🔉🖤"\n        default:\n            return "Done on \\(whereText), baby. 🖤"\n'''
if success not in text:
    raise SystemExit("ContentView.swift: success switch marker missing")
text = text.replace(success, media_success, 1)

path.write_text(text, encoding="utf-8")
for marker in ["VoiceConversationController", "toggleHandsFree", "media_play_pause", "lastTargetAtKey"]:
    if marker not in text:
        raise SystemExit(f"missing UI marker: {marker}")
print("Applied v0.8.6 hands-free voice UI + media routing")
