#!/usr/bin/env python3
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"{label}: expected source block not found")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# iPhone: hands-free voice loop + spoken replies.
# ---------------------------------------------------------------------------
content_path = Path("VexNative/ContentView.swift")
text = content_path.read_text(encoding="utf-8")

if "import Speech\n" not in text:
    text = text.replace("import SwiftUI\n", "import SwiftUI\nimport Speech\nimport AVFoundation\n", 1)

text = replace_once(
    text,
    "    @StateObject private var web = WebBrain.shared\n",
    "    @StateObject private var web = WebBrain.shared\n    @StateObject private var voice = VoiceConversationController()\n",
    "voice state object",
)

# Configure the voice command callback during the existing startup task.
startup = "            await app.loadSavedModelIfPresent()\n"
startup_new = """            await app.loadSavedModelIfPresent()\n            voice.onCommand = { command in\n                guard !app.isGenerating, !web.isWorking else { return }\n                app.draft = command\n                Task { await app.sendWithWeb() }\n            }\n"""
text = replace_once(text, startup, startup_new, "voice startup callback")

# Speak assistant replies while hands-free mode is active. Stop the mic when the
# view goes away so it never keeps listening after the chat UI is dismissed.
alert_marker = '''        .alert(\n            "Tiny brain error",\n'''
voice_lifecycle = '''        .onChange(of: app.messages.count) { oldCount, newCount in\n            guard newCount > oldCount, voice.isHandsFree,\n                  let last = app.messages.last, last.role == .assistant\n            else { return }\n            voice.speak(last.content)\n        }\n        .onDisappear {\n            voice.stopHandsFree()\n        }\n'''
if alert_marker not in text:
    raise SystemExit("ContentView.swift: alert marker missing")
text = text.replace(alert_marker, voice_lifecycle + alert_marker, 1)

# Add voice state to the status strip.
status_start = text.find("    private var statusStrip: some View {")
status_end = text.find("    private var composer: some View {", status_start)
if status_start < 0 or status_end < 0:
    raise SystemExit("ContentView.swift: status strip markers missing")
status_block = text[status_start:status_end]
spacer = "            Spacer()\n"
voice_status = '''            if voice.isHandsFree {\n                Text(voice.isListening ? "• 🎙️ listening" : "• 🔊 voice")\n                    .font(.caption)\n                    .foregroundStyle(voice.isListening ? Color.green : VexTheme.muted)\n            }\n\n'''
if spacer not in status_block:
    raise SystemExit("ContentView.swift: status spacer missing")
status_block = status_block.replace(spacer, voice_status + spacer, 1)
text = text[:status_start] + status_block + text[status_end:]

# Add a persistent hands-free microphone button beside the existing photo menu.
textfield_marker = '''            TextField("Say something to Vex…", text: $app.draft)\n'''
voice_button = '''            Button {\n                Task {\n                    do {\n                        try await voice.toggleHandsFree()\n                    } catch {\n                        app.lastError = error.localizedDescription\n                    }\n                }\n            } label: {\n                Image(systemName: voice.isHandsFree ? "waveform.circle.fill" : "mic.fill")\n                    .font(.headline)\n                    .foregroundStyle(voice.isHandsFree ? Color.green : VexTheme.hotPink)\n                    .frame(width: 40, height: 44)\n                    .background(VexTheme.panel)\n                    .clipShape(RoundedRectangle(cornerRadius: 13))\n            }\n            .buttonStyle(.plain)\n            .accessibilityLabel(voice.isHandsFree ? "Turn off hands-free voice" : "Turn on hands-free voice")\n\n'''
if textfield_marker not in text:
    raise SystemExit("ContentView.swift: composer TextField marker missing")
text = text.replace(textfield_marker, voice_button + textfield_marker, 1)

# Voice controller. Hands-free mode uses a wake phrase so music/TV audio does not
# get submitted as commands. Say "Vex ..." / "Hey Vex ..." after enabling once.
web_marker = "// MARK: - Web Brain v0.6\n"
voice_controller = r'''// MARK: - Hands-free voice v0.8.6

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

        let speechOK = await requestSpeechPermission()
        guard speechOK else { throw VoiceError.speechPermission }
        let micOK = await requestMicPermission()
        guard micOK else { throw VoiceError.microphonePermission }

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
        guard !text.isEmpty else {
            restartListeningSoon()
            return
        }
        synthesizer.stopSpeaking(at: .immediate)
        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = AVSpeechSynthesisVoice(language: "en-US")
        utterance.rate = 0.49
        utterance.pitchMultiplier = 1.06
        utterance.volume = 1.0
        synthesizer.speak(utterance)
    }

    private func requestSpeechPermission() async -> Bool {
        if SFSpeechRecognizer.authorizationStatus() == .authorized { return true }
        return await withCheckedContinuation { continuation in
            SFSpeechRecognizer.requestAuthorization { status in
                continuation.resume(returning: status == .authorized)
            }
        }
    }

    private func requestMicPermission() async -> Bool {
        let session = AVAudioSession.sharedInstance()
        switch session.recordPermission {
        case .granted:
            return true
        case .denied:
            return false
        case .undetermined:
            return await withCheckedContinuation { continuation in
                session.requestRecordPermission { granted in
                    continuation.resume(returning: granted)
                }
            }
        @unknown default:
            return false
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
        if recognizer.supportsOnDeviceRecognition {
            request.requiresOnDeviceRecognition = true
        }
        recognitionRequest = request

        let input = audioEngine.inputNode
        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0 else { throw VoiceError.microphoneUnavailable }
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak request] buffer, _ in
            request?.append(buffer)
        }

        audioEngine.prepare()
        try audioEngine.start()
        isListening = true
        partialTranscript = ""

        recognitionTask = recognizer.recognitionTask(with: request) { [weak self] result, error in
            let transcript = result?.bestTranscription.formattedString
            let isFinal = result?.isFinal ?? false
            let failed = error != nil
            DispatchQueue.main.async {
                self?.consume(transcript: transcript, isFinal: isFinal, failed: failed)
            }
        }
    }

    private func consume(transcript: String?, isFinal: Bool, failed: Bool) {
        guard isHandsFree else { return }
        if let transcript, !transcript.isEmpty {
            partialTranscript = transcript
            silenceTimer?.invalidate()
            silenceTimer = Timer.scheduledTimer(withTimeInterval: 1.25, repeats: false) { [weak self] _ in
                self?.commitTranscript()
            }
        }

        if isFinal {
            commitTranscript()
        } else if failed && partialTranscript.isEmpty {
            stopRecognition()
            restartListeningSoon()
        }
    }

    private func commitTranscript() {
        silenceTimer?.invalidate()
        silenceTimer = nil
        let raw = partialTranscript.trimmingCharacters(in: .whitespacesAndNewlines)
        partialTranscript = ""
        stopRecognition()

        guard isHandsFree, !raw.isEmpty else {
            restartListeningSoon()
            return
        }
        guard let command = Self.commandAfterWakePhrase(raw), !command.isEmpty else {
            restartListeningSoon()
            return
        }

        waitingForReply = true
        onCommand?(command)

        // If a tool/model turn fails to append a reply, don't leave the mic dead forever.
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
        guard let prefix = prefixes.first(where: { lower == $0 || lower.hasPrefix($0 + " ") || lower.hasPrefix($0 + ",") }) else {
            return nil
        }
        let index = trimmed.index(trimmed.startIndex, offsetBy: prefix.count)
        return String(trimmed[index...])
            .trimmingCharacters(in: CharacterSet.whitespacesAndNewlines.union(CharacterSet(charactersIn: ",:.-")))
    }

    private static func spokenText(_ raw: String) -> String {
        var text = raw
        if let range = text.range(of: "🌐 Sources:") { text = String(text[..<range.lowerBound]) }
        if let range = text.range(of: "Sources:") { text = String(text[..<range.lowerBound]) }
        text = text.replacingOccurrences(of: "🖤", with: "")
            .replacingOccurrences(of: "💕", with: "")
            .replacingOccurrences(of: "✨", with: "")
            .replacingOccurrences(of: "😭", with: "")
            .replacingOccurrences(of: "😂", with: "")
            .replacingOccurrences(of: "😈", with: "")
        return text.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        Task { @MainActor [weak self] in self?.restartListeningSoon() }
    }

    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance) {
        Task { @MainActor [weak self] in self?.restartListeningSoon() }
    }

    enum VoiceError: LocalizedError {
        case speechPermission
        case microphonePermission
        case recognizerUnavailable
        case microphoneUnavailable

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
if web_marker not in text:
    raise SystemExit("ContentView.swift: Web Brain marker missing")
text = text.replace(web_marker, voice_controller + web_marker, 1)


# ---------------------------------------------------------------------------
# iPhone PC router: direct media keys + recent-PC follow-up target.
# ---------------------------------------------------------------------------
# Expand requestedAction with media transport/volume commands before browser/open parsing.
action_sig = '    private static func requestedAction(_ lower: String, original: String) -> String? {\n'
if action_sig not in text:
    raise SystemExit("ContentView.swift: requestedAction v0.8.5 marker missing")
action_inject = r'''    private static func requestedAction(_ lower: String, original: String) -> String? {
        if lower.contains("play pause") || lower.contains("pause the music") || lower.contains("pause music") ||
            lower == "pause" || lower.hasPrefix("pause ") || lower.contains("pause it") {
            return "media_play_pause"
        }
        if lower.contains("next song") || lower.contains("next track") || lower.contains("skip song") ||
            lower.contains("skip track") || lower.contains("skip this") {
            return "media_next"
        }
        if lower.contains("previous song") || lower.contains("previous track") || lower.contains("last song") ||
            lower.contains("go back a song") || lower.contains("go back one track") {
            return "media_previous"
        }
        if lower.contains("mute") || lower.contains("unmute") {
            return "volume_mute"
        }
        if lower.contains("volume up") || lower.contains("turn it up") || lower.contains("turn the volume up") ||
            lower.contains("make it louder") || lower == "louder" {
            return "volume_up"
        }
        if lower.contains("volume down") || lower.contains("turn it down") || lower.contains("turn the volume down") ||
            lower.contains("make it quieter") || lower == "quieter" {
            return "volume_down"
        }
'''
text = text.replace(action_sig, action_inject, 1)

# v0.8.5 target parser stores explicit targets. Add a timestamp and allow a recent
# explicit machine to carry into natural follow-ups like "play the playlist" or
# "turn it down" for 20 minutes.
target_marker = '    private static let lastTargetKey = "vex.pc.lastTarget.v1"\n'
if target_marker not in text:
    raise SystemExit("ContentView.swift: lastTargetKey marker missing")
text = text.replace(target_marker, target_marker + '    private static let lastTargetAtKey = "vex.pc.lastTargetAt.v1"\n', 1)

# Stamp target time whenever v0.8.5 records an explicit target.
text = text.replace('UserDefaults.standard.set("both", forKey: lastTargetKey)\n            return .both',
                    'UserDefaults.standard.set("both", forKey: lastTargetKey)\n            UserDefaults.standard.set(Date().timeIntervalSince1970, forKey: lastTargetAtKey)\n            return .both')
text = text.replace('UserDefaults.standard.set("secondary", forKey: lastTargetKey)\n            return .secondary',
                    'UserDefaults.standard.set("secondary", forKey: lastTargetKey)\n            UserDefaults.standard.set(Date().timeIntervalSince1970, forKey: lastTargetAtKey)\n            return .secondary')
text = text.replace('UserDefaults.standard.set("primary", forKey: lastTargetKey)\n            return .primary',
                    'UserDefaults.standard.set("primary", forKey: lastTargetKey)\n            UserDefaults.standard.set(Date().timeIntervalSince1970, forKey: lastTargetAtKey)\n            return .primary')

# Before requestedTarget returns nil, reuse a recent explicit target. Find the
# exact v0.8.5 tail of the function and insert the TTL lookup.
target_func_start = text.find("    private static func requestedTarget(_ lower: String) -> NodeTarget? {")
target_func_end = text.find("    private static func requestedAction", target_func_start)
if target_func_start < 0 or target_func_end < 0:
    raise SystemExit("ContentView.swift: target function bounds missing")
target_block = text[target_func_start:target_func_end]
needle = "        return nil\n    }\n"
recent_target = r'''        let savedAt = UserDefaults.standard.double(forKey: lastTargetAtKey)
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
if needle not in target_block:
    raise SystemExit("ContentView.swift: target return marker missing")
target_block = target_block.replace(needle, recent_target, 1)
text = text[:target_func_start] + target_block + text[target_func_end:]

# Media action success messages.
success_default = '''        default:\n            return "Done on \\(whereText), baby. 🖤"\n'''
media_success = '''        case "media_play_pause":\n            return "Done — I toggled play/pause on \\(whereText), baby. 🎵🖤"\n        case "media_next":\n            return "Done — I skipped to the next track on \\(whereText), baby. ⏭️🖤"\n        case "media_previous":\n            return "Done — I went back a track on \\(whereText), baby. ⏮️🖤"\n        case "volume_mute":\n            return "Done — I toggled mute on \\(whereText), baby. 🔇🖤"\n        case "volume_up":\n            return "Done — I turned it up on \\(whereText), baby. 🔊🖤"\n        case "volume_down":\n            return "Done — I turned it down on \\(whereText), baby. 🔉🖤"\n        default:\n            return "Done on \\(whereText), baby. 🖤"\n'''
if success_default not in text:
    raise SystemExit("ContentView.swift: success default marker missing")
text = text.replace(success_default, media_success, 1)

content_path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Windows Bridge: real media transport/volume keys + named YouTube/media lookup.
# ---------------------------------------------------------------------------
bridge_path = Path("Bridge/vex_bridge.py")
bridge = bridge_path.read_text(encoding="utf-8")

if "import ctypes\n" not in bridge:
    bridge = bridge.replace("import argparse\n", "import argparse\nimport ctypes\n", 1)

# Extend PC_TOOL_ACTIONS without depending on the exact previous item ordering.
list_start = bridge.find("PC_TOOL_ACTIONS = [")
list_end = bridge.find("]\n", list_start)
if list_start < 0 or list_end < 0:
    raise SystemExit("vex_bridge.py: PC_TOOL_ACTIONS list missing")
list_block = bridge[list_start:list_end]
for action in ["media_play_pause", "media_next", "media_previous", "volume_mute", "volume_down", "volume_up"]:
    if f'"{action}"' not in list_block:
        list_block += f'    "{action}",\n'
bridge = bridge[:list_start] + list_block + bridge[list_end:]

# Media key helper before the action executor.
run_marker = "def run_pc_tool_action(action: str, payload: dict | None = None) -> dict:\n"
if run_marker not in bridge:
    raise SystemExit("vex_bridge.py: run_pc_tool_action payload signature missing")
media_helper = r'''def _press_windows_media_key(vk: int) -> None:
    KEYEVENTF_KEYUP = 0x0002
    user32 = ctypes.windll.user32
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


'''
bridge = bridge.replace(run_marker, media_helper + run_marker, 1)

# Add branches immediately before the action executor's unsupported-action else.
open_url_tail = '''            os.startfile(raw_url)\n            message = f"Opened {parsed_url.hostname}"\n        else:\n'''
media_branches = '''            os.startfile(raw_url)\n            message = f"Opened {parsed_url.hostname}"\n        elif action == "media_play_pause":\n            _press_windows_media_key(0xB3)\n            message = "Play/pause toggled"\n        elif action == "media_next":\n            _press_windows_media_key(0xB0)\n            message = "Next track"\n        elif action == "media_previous":\n            _press_windows_media_key(0xB1)\n            message = "Previous track"\n        elif action == "volume_mute":\n            _press_windows_media_key(0xAD)\n            message = "Mute toggled"\n        elif action == "volume_down":\n            _press_windows_media_key(0xAE)\n            message = "Volume down"\n        elif action == "volume_up":\n            _press_windows_media_key(0xAF)\n            message = "Volume up"\n        else:\n'''
if open_url_tail not in bridge:
    raise SystemExit("vex_bridge.py: open_url action tail missing")
bridge = bridge.replace(open_url_tail, media_branches, 1)

# Teach the v0.8.5 compiler how to turn "play <name> playlist/song" into a real
# YouTube watch/playlist URL using web evidence. This remains a safe URL primitive.
infer_marker = "def _infer_primitive(step_text: str) -> dict | None:\n"
if infer_marker not in bridge:
    raise SystemExit("vex_bridge.py: v0.8.5 infer primitive missing")
media_discovery = r'''def _discover_media_url(step_text: str) -> dict | None:
    low = re.sub(r"\s+", " ", step_text.lower()).strip()
    if not (low.startswith("play ") or " playlist" in low or " song" in low or " track" in low or " album" in low):
        return None

    query = re.sub(r"^(please\s+)?(can you\s+)?(play|put on|start)\s+", "", step_text, flags=re.I).strip()
    query = re.sub(r"\s+(on|in)\s+(the\s+)?(kitchen|downstairs|upstairs|hp|monte)(\s+(pc|computer))?.*$", "", query, flags=re.I).strip()
    query = re.sub(r"\s+for me$", "", query, flags=re.I).strip()
    if not query:
        return None

    search_query = f'{query} YouTube'
    if "playlist" in query.lower():
        search_query = f'{query} site:youtube.com playlist'
    try:
        results = web_search(search_query, limit=10)
    except Exception:
        results = []

    wanted = {t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) > 1 and t not in {"the", "a", "an", "playlist", "song", "track", "album"}}
    scored = []
    for result in results:
        raw_url = str(result.get("url") or "").strip()
        title = str(result.get("title") or "").strip()
        parsed = urlsplit(raw_url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not ("youtube.com" in host or "youtu.be" in host):
            continue
        hay = f"{title.lower()} {raw_url.lower()}"
        overlap = sum(1 for token in wanted if token in hay)
        if wanted and overlap == 0:
            continue
        score = overlap * 3
        if "playlist" in query.lower() and ("playlist" in hay or "list=" in raw_url):
            score += 5
        if "/watch" in raw_url or "youtu.be/" in raw_url:
            score += 3
        scored.append((score, raw_url, title))

    if not scored:
        return None
    scored.sort(key=lambda row: row[0], reverse=True)
    _, url, title = scored[0]
    return {"url": url, "title": title or query}


'''
bridge = bridge.replace(infer_marker, media_discovery + infer_marker, 1)

# Insert media resolution at the top of _infer_primitive after the lowercase line.
infer_lower = '''def _infer_primitive(step_text: str) -> dict | None:\n    low = step_text.lower()\n'''
infer_new = '''def _infer_primitive(step_text: str) -> dict | None:\n    low = step_text.lower()\n\n    if low.startswith("play ") || false:\n        pass\n'''
# Avoid writing invalid Python with Swift-like syntax; use direct Python replacement below.
if infer_lower not in bridge:
    raise SystemExit("vex_bridge.py: infer lower marker missing")
bridge = bridge.replace(
    infer_lower,
    '''def _infer_primitive(step_text: str) -> dict | None:\n    low = step_text.lower()\n\n    if low.startswith("play ") or " playlist" in low or " song" in low or " track" in low or " album" in low:\n        media = _discover_media_url(step_text)\n        if media:\n            return {"kind": "url", "value": media["url"], "label": media.get("title") or "YouTube media"}\n''',
    1,
)

# Advertise the extra safe controls in status, if the v0.8.5 status list exists.
bridge = bridge.replace(
    '"skill_primitives": ["open_url", "launch_installed_app", "open_existing_folder", "compile_multi_step_workflow"],',
    '"skill_primitives": ["open_url", "launch_installed_app", "open_existing_folder", "compile_multi_step_workflow", "windows_media_keys"],',
)

bridge_path.write_text(bridge, encoding="utf-8")

full_path = Path("Bridge/vex_bridge_full.py")
full = full_path.read_text(encoding="utf-8")
full = full.replace('VERSION = "0.8.5"', 'VERSION = "0.8.6"', 1)
full_path.write_text(full, encoding="utf-8")

# Final sanity markers.
for path, markers in [
    (content_path, ["VoiceConversationController", "toggleHandsFree", "media_play_pause", "lastTargetAtKey"]),
    (bridge_path, ["_press_windows_media_key", '"media_play_pause"', "_discover_media_url", "windows_media_keys"]),
    (full_path, ['VERSION = "0.8.6"']),
]:
    data = path.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in data:
            raise SystemExit(f"{path}: missing v0.8.6 marker {marker}")

print("Applied v0.8.6 hands-free voice + PC media control patch")
