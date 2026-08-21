#!/usr/bin/env python3
from pathlib import Path


path = Path("VexNative/ContentView.swift")
text = path.read_text(encoding="utf-8")


def once(old: str, new: str, label: str) -> None:
    global text
    if old not in text:
        raise SystemExit(f"{label}: source block not found")
    text = text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# Voice: v0.8.9 proved the conversational speech loop works, but the built-in
# AVSpeechSynthesizer voice can sound extremely robotic on devices that do not
# have a good enhanced/premium voice installed. Prefer authenticated Bridge TTS
# audio and keep the best available iOS voice only as a resilient fallback.
# ---------------------------------------------------------------------------
once(
    "final class VoiceConversationController: NSObject, ObservableObject, AVSpeechSynthesizerDelegate {",
    "final class VoiceConversationController: NSObject, ObservableObject, AVSpeechSynthesizerDelegate, AVAudioPlayerDelegate {",
    "voice audio player delegate",
)

once(
    '''    private let synthesizer = AVSpeechSynthesizer()\n    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?\n''',
    '''    private let synthesizer = AVSpeechSynthesizer()\n    private var remotePlayer: AVAudioPlayer?\n    private var isFetchingRemoteVoice = false\n    private var speechGeneration = 0\n    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?\n''',
    "remote voice state",
)

once(
    '''        isHandsFree = false\n        waitingForReply = false\n        wakeArmedUntil = nil\n        voiceHint = "Voice off"\n        synthesizer.stopSpeaking(at: .immediate)\n''',
    '''        isHandsFree = false\n        waitingForReply = false\n        wakeArmedUntil = nil\n        voiceHint = "Voice off"\n        speechGeneration += 1\n        isFetchingRemoteVoice = false\n        remotePlayer?.stop()\n        remotePlayer = nil\n        synthesizer.stopSpeaking(at: .immediate)\n''',
    "stop remote voice",
)

start = text.find('    func speak(_ rawText: String) {')
end = text.find('    private func requestSpeechPermission()', start)
if start < 0 or end < 0:
    raise SystemExit("voice speak bounds missing")

new_speak = r'''    func speak(_ rawText: String) {
        guard isHandsFree else { return }

        // A completed assistant turn always releases the command wait. Text-only
        // mode must also resume listening instead of leaving voice mode stuck.
        waitingForReply = false
        stopRecognition()
        let text = Self.spokenText(rawText)
        guard replyMode != .textOnly, !text.isEmpty else {
            voiceHint = replyMode == .textOnly ? "Replies: text only" : "Listening…"
            restartListeningSoon()
            return
        }

        speechGeneration += 1
        let generation = speechGeneration
        synthesizer.stopSpeaking(at: .immediate)
        remotePlayer?.stop()
        remotePlayer = nil
        isFetchingRemoteVoice = true
        voiceHint = "Vex is speaking…"

        Task { [weak self] in
            guard let self else { return }
            let audio = await self.fetchBridgeVoice(text)
            guard self.isHandsFree, generation == self.speechGeneration else { return }
            self.isFetchingRemoteVoice = false

            if let audio, self.playRemoteVoice(audio, generation: generation) {
                return
            }
            self.speakLocalFallback(text, generation: generation)
        }
    }

    private func fetchBridgeVoice(_ text: String) async -> Data? {
        for endpoint in configuredBridgeEndpointsForVoice() {
            guard let url = Self.bridgeURL(endpoint: endpoint, path: "/tts") else { continue }
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.timeoutInterval = 8.0
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try? JSONSerialization.data(withJSONObject: ["text": text])
            do {
                let (data, response) = try await VexBridgeNetworking.data(for: request)
                guard let http = response as? HTTPURLResponse,
                      (200...299).contains(http.statusCode),
                      !data.isEmpty
                else { continue }
                return data
            } catch {
                continue
            }
        }
        return nil
    }

    private func configuredBridgeEndpointsForVoice() -> [String] {
        let defaults = UserDefaults.standard
        let primary = defaults.string(forKey: WebBrain.searxEndpointKey)?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let secondary = defaults.string(forKey: WebBrain.secondaryBridgeEndpointKey)?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""

        var endpoints = [primary, secondary].filter { endpoint in
            guard let url = URL(string: endpoint) else { return false }
            return VexBridgeNetworking.isBridgeURL(url)
        }
        var seen = Set<String>()
        endpoints = endpoints.filter { seen.insert($0).inserted }

        // Prefer the PC Star most recently addressed so voice follows the same
        // failover locality as media/PC commands, then try the other node.
        if defaults.string(forKey: "vex.pc.lastTarget.v1") == "secondary", endpoints.count > 1 {
            endpoints.swapAt(0, 1)
        }
        return endpoints
    }

    private static func bridgeURL(endpoint: String, path: String) -> URL? {
        guard let root = URL(string: endpoint),
              VexBridgeNetworking.isBridgeURL(root),
              var components = URLComponents(url: root, resolvingAgainstBaseURL: false)
        else { return nil }
        components.path = path
        return components.url
    }

    private func playRemoteVoice(_ data: Data, generation: Int) -> Bool {
        guard isHandsFree, generation == speechGeneration else { return false }
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playAndRecord, mode: .voiceChat, options: [.defaultToSpeaker, .allowBluetooth, .duckOthers])
            try session.setActive(true, options: .notifyOthersOnDeactivation)

            let player = try AVAudioPlayer(data: data)
            player.delegate = self
            player.prepareToPlay()
            remotePlayer = player
            if player.play() {
                voiceHint = "Vex is speaking…"
                return true
            }
            remotePlayer = nil
        } catch {
            remotePlayer = nil
        }
        return false
    }

    private func speakLocalFallback(_ text: String, generation: Int) {
        guard isHandsFree, generation == speechGeneration else { return }
        isFetchingRemoteVoice = false
        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = Self.preferredVexVoice()
        utterance.rate = 0.50
        utterance.pitchMultiplier = 1.00
        utterance.volume = 1.0
        voiceHint = "Vex is speaking…"
        synthesizer.speak(utterance)
    }

'''
text = text[:start] + new_speak + text[end:]

# Do not reopen the microphone underneath downloaded/playing neural speech.
text = text.replace(
    'guard isHandsFree, !synthesizer.isSpeaking, !waitingForReply else { return }',
    'guard isHandsFree, !synthesizer.isSpeaking, remotePlayer?.isPlaying != true, !isFetchingRemoteVoice, !waitingForReply else { return }',
)
text = text.replace(
    'guard let self, self.isHandsFree, !self.synthesizer.isSpeaking, !self.waitingForReply else { return }',
    'guard let self, self.isHandsFree, !self.synthesizer.isSpeaking, self.remotePlayer?.isPlaying != true, !self.isFetchingRemoteVoice, !self.waitingForReply else { return }',
)

# Replace the v0.8.9 name-only local voice picker. If Bridge TTS is unavailable,
# prefer iOS premium/enhanced feminine voices when Star has one installed.
voice_picker_start = text.find('    private static func preferredVexVoice() -> AVSpeechSynthesisVoice? {')
voice_picker_end = text.find('    enum VoiceError: LocalizedError {', voice_picker_start)
if voice_picker_start < 0 or voice_picker_end < 0:
    raise SystemExit("preferredVexVoice bounds missing")

voice_picker = r'''    private static func preferredVexVoice() -> AVSpeechSynthesisVoice? {
        let english = AVSpeechSynthesisVoice.speechVoices().filter {
            $0.language.lowercased().hasPrefix("en-us")
        }
        guard !english.isEmpty else { return AVSpeechSynthesisVoice(language: "en-US") }

        let preferredNames = ["Ava", "Samantha", "Zoe", "Nicky", "Allison", "Susan"]
        func score(_ voice: AVSpeechSynthesisVoice) -> Int {
            var value = voice.quality.rawValue * 100
            if voice.gender == .female { value += 40 }
            if let index = preferredNames.firstIndex(where: {
                voice.name.localizedCaseInsensitiveContains($0)
            }) {
                value += max(1, 30 - index * 4)
            }
            return value
        }
        return english.max(by: { score($0) < score($1) })
    }

    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor [weak self] in
            guard let self else { return }
            if self.remotePlayer === player { self.remotePlayer = nil }
            self.voiceHint = "Listening…"
            self.restartListeningSoon()
        }
    }

    nonisolated func audioPlayerDecodeErrorDidOccur(_ player: AVAudioPlayer, error: Error?) {
        Task { @MainActor [weak self] in
            guard let self else { return }
            if self.remotePlayer === player { self.remotePlayer = nil }
            self.restartListeningSoon()
        }
    }

'''
text = text[:voice_picker_start] + voice_picker + text[voice_picker_end:]


# ---------------------------------------------------------------------------
# Named media: keep natural follow-ups such as "playlist called stars vibes" in
# the PC tool layer. They must never fall through to random indexed files/Qwen.
# The Bridge returns resolution + verification evidence; the iPhone reports only
# what actually happened instead of claiming playback because an HTTP call ran.
# ---------------------------------------------------------------------------
once(
    '''    private struct ToolReply: Decodable {\n        let ok: Bool\n        let action: String?\n        let node_name: String?\n        let message: String?\n    }\n\n    private struct EndpointNode {\n''',
    '''    private struct ToolReply: Decodable {\n        let ok: Bool\n        let action: String?\n        let node_name: String?\n        let message: String?\n    }\n\n    private struct MediaReply: Decodable {\n        let ok: Bool\n        let verified: Bool?\n        let node_name: String?\n        let title: String?\n        let url: String?\n        let kind: String?\n        let resolution: String?\n        let message: String?\n    }\n\n    private struct EndpointNode {\n''',
    "media reply DTO",
)

once(
    '''        let parsedAction = requestedAction(lower, original: original)\n        guard let target = requestedTarget(lower) else { return false }\n\n        if parsedAction == nil, looksLikePCCommand(lower) {\n''',
    '''        let parsedAction = requestedAction(lower, original: original)\n        guard let target = requestedTarget(lower) else { return false }\n\n        if isNamedMediaRequest(lower) {\n            return await tryNamedMedia(original, target: target, app: app)\n        }\n\n        if parsedAction == nil, looksLikePCCommand(lower) {\n''',
    "named media interception",
)

media_helper_marker = '    private static func looksLikePCCommand(_ lower: String) -> Bool {\n'
if media_helper_marker not in text:
    raise SystemExit("looksLikePCCommand marker missing")

media_helpers = r'''    private static func isNamedMediaRequest(_ lower: String) -> Bool {
        let transportOnly = lower.contains("play pause") || lower.contains("pause the music") ||
            lower.contains("next song") || lower.contains("next track") ||
            lower.contains("previous song") || lower.contains("previous track") ||
            lower.contains("skip song") || lower.contains("skip track") ||
            lower.contains("volume up") || lower.contains("volume down") ||
            lower == "pause" || lower == "louder" || lower == "quieter"
        if transportOnly { return false }

        if lower.hasPrefix("play ") || lower.hasPrefix("put on ") || lower.hasPrefix("start playing ") {
            return true
        }
        let mediaWords = ["playlist", " song", "song ", " track", "track ", " album", "album "]
        return mediaWords.contains(where: { lower.contains($0) })
    }

    private static func tryNamedMedia(_ original: String, target: NodeTarget, app: AppModel) async -> Bool {
        let nodes = configuredNodes()
        let selected: [EndpointNode]
        switch target {
        case .primary:
            selected = nodes.filter { $0.label == "upstairs/primary PC" }
        case .secondary:
            selected = nodes.filter { $0.label == "kitchen/downstairs PC" }
        case .both:
            selected = nodes
        }
        guard !selected.isEmpty else { return false }

        app.draft = ""
        app.isGenerating = true
        defer { app.isGenerating = false }

        let normalizedRequest: String
        let lower = normalize(original)
        if lower.hasPrefix("play ") || lower.hasPrefix("put on ") || lower.hasPrefix("start playing ") {
            normalizedRequest = original
        } else {
            normalizedRequest = "play " + original
        }

        var replies: [(EndpointNode, MediaReply)] = []
        var failures: [EndpointNode] = []
        for node in selected {
            if let reply = await performMedia(requestText: normalizedRequest, endpoint: node.endpoint), reply.ok {
                replies.append((node, reply))
            } else {
                failures.append(node)
            }
        }

        guard !replies.isEmpty else {
            appendExchange(
                user: original,
                assistant: "I couldn't resolve that media request on the selected Bridge, baby. I didn't claim it opened because I don't have evidence that it did. 🖤",
                app: app
            )
            return true
        }

        let descriptions = replies.map { node, reply -> String in
            let reported = reply.node_name?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            let name = reported.isEmpty ? node.label : reported
            let title = reply.title?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            let resolution = reply.resolution ?? ""
            let verified = reply.verified ?? false

            if resolution == "search_results" {
                return "I opened YouTube search results for \(title.isEmpty ? "that media" : title) on \(name)"
            }
            if verified {
                return "I opened the matched \(reply.kind ?? "media") \(title.isEmpty ? "" : "‘\(title)’ ")on \(name) and verified the browser page"
            }
            return "I opened the matched \(reply.kind ?? "media") URL \(title.isEmpty ? "" : "for ‘\(title)’ ")on \(name), but I couldn't verify the page finished loading"
        }

        var reply = descriptions.joined(separator: replies.count > 1 ? ". " : "") + "."
        if !failures.isEmpty {
            reply += " The other selected Bridge didn't complete it."
        }
        reply += " 🖤"
        appendExchange(user: original, assistant: reply, app: app)
        return true
    }

    private static func performMedia(requestText: String, endpoint: String) async -> MediaReply? {
        guard let url = toolURL(endpoint: endpoint, path: "/media/play") else { return nil }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 15.0
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: ["request": requestText])
        do {
            let (data, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...499).contains(http.statusCode) else { return nil }
            return try JSONDecoder().decode(MediaReply.self, from: data)
        } catch {
            return nil
        }
    }

'''
text = text.replace(media_helper_marker, media_helpers + media_helper_marker, 1)

path.write_text(text, encoding="utf-8")

for marker in [
    "AVAudioPlayerDelegate",
    'path: "/tts"',
    "fetchBridgeVoice",
    "audioPlayerDidFinishPlaying",
    "quality.rawValue",
    "isNamedMediaRequest",
    'path: "/media/play"',
    "search_results",
    "I didn't claim it opened",
]:
    if marker not in text:
        raise SystemExit(f"missing v0.9.0 client marker: {marker}")

print("Applied v0.9.0 neural Bridge voice + grounded named-media client routing")
