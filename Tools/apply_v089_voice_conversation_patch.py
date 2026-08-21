#!/usr/bin/env python3
from pathlib import Path

path = Path("VexNative/ContentView.swift")
text = path.read_text(encoding="utf-8")


def once(old: str, new: str, label: str):
    global text
    if old not in text:
        raise SystemExit(f"{label}: source block not found")
    text = text.replace(old, new, 1)

# v0.8.8 proves Speech is hearing Star, but still requires an exact wake phrase
# before it will submit the utterance. The mic button itself is already an explicit
# hands-free opt-in, so v0.8.9 treats normal speech as a command while voice mode is
# on. A leading Vex/Hey Vex is still stripped naturally, and saying only "Vex"
# still arms a short follow-up window.
old_commit = '''        let now = Date()\n        let armed = wakeArmedUntil.map { $0 > now } ?? false\n        var command: String?\n        if armed {\n            wakeArmedUntil = nil\n            command = raw\n        } else {\n            let parsed = Self.commandAfterWakePhrase(raw)\n            if parsed == "__WAKE_ONLY__" {\n                wakeArmedUntil = now.addingTimeInterval(8)\n                voiceHint = "Yep? Listening for your command…"\n                restartListeningSoon()\n                return\n            }\n            command = parsed\n        }\n\n        guard let command, !command.isEmpty else {\n            voiceHint = "Heard you — say ‘Vex …’ first"\n            restartListeningSoon()\n            return\n        }\n\n        voiceHint = "Sending: " + command\n        waitingForReply = true\n        onCommand?(command)\n'''
new_commit = '''        let now = Date()\n        let armed = wakeArmedUntil.map { $0 > now } ?? false\n        var command: String?\n        if armed {\n            wakeArmedUntil = nil\n            command = raw\n        } else {\n            let parsed = Self.commandAfterWakePhrase(raw)\n            if parsed == "__WAKE_ONLY__" {\n                wakeArmedUntil = now.addingTimeInterval(8)\n                voiceHint = "Yep? Listening for your command…"\n                restartListeningSoon()\n                return\n            }\n            // The user already explicitly enabled the microphone. Do not make a\n            // tiny speech recognizer correctly hear the wake word on every turn.\n            // If a wake phrase is present, strip it; otherwise submit the speech.\n            command = parsed ?? raw\n        }\n\n        guard let command, !command.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {\n            voiceHint = "Listening…"\n            restartListeningSoon()\n            return\n        }\n\n        voiceHint = "Sending: " + command\n        waitingForReply = true\n        onCommand?(command)\n'''
once(old_commit, new_commit, "wake-free conversational submit")

# Give Vex an explicit reply mode, persisted on-device. Text is always retained in
# the conversation model; voice-only merely hides assistant bubbles while active,
# so switching back to Text/Both never destroys history.
once(
'''    @Published private(set) var voiceHint = "Say ‘Vex …’"\n''',
'''    @Published private(set) var voiceHint = "Just talk — I’m listening"\n    @Published private(set) var replyMode: ReplyMode = ReplyMode.saved\n''',
"reply mode published state",
)

# Prefer a recognizable feminine system voice when installed, then fall back to
# the best normal en-US voice available on that iPhone.
old_voice = '''        let utterance = AVSpeechUtterance(string: text)\n        utterance.voice = AVSpeechSynthesisVoice(language: "en-US")\n        utterance.rate = 0.49\n        utterance.pitchMultiplier = 1.06\n        utterance.volume = 1.0\n        synthesizer.speak(utterance)\n'''
new_voice = '''        let utterance = AVSpeechUtterance(string: text)\n        utterance.voice = Self.preferredVexVoice()\n        utterance.rate = 0.49\n        utterance.pitchMultiplier = 1.08\n        utterance.volume = 1.0\n        synthesizer.speak(utterance)\n'''
once(old_voice, new_voice, "preferred Vex voice")

# Only synthesize speech in Both/Voice modes.
once(
'''    func speak(_ rawText: String) {\n        guard isHandsFree else { return }\n''',
'''    func speak(_ rawText: String) {\n        guard isHandsFree, replyMode != .textOnly else { return }\n''',
"speech mode guard",
)

# Start hints should reflect the new no-wake-required conversation behavior.
text = text.replace('voiceHint = "Say ‘Vex …’"', 'voiceHint = "Just talk — I’m listening"')

# Add mode setter / enum / voice selection before VoiceError.
error_marker = '''    enum VoiceError: LocalizedError {\n'''
voice_modes = r'''    enum ReplyMode: String, CaseIterable, Identifiable {
        case both
        case textOnly
        case voiceOnly

        var id: String { rawValue }
        var title: String {
            switch self {
            case .both: return "Voice + Text"
            case .textOnly: return "Text Only"
            case .voiceOnly: return "Voice Only"
            }
        }
        var symbol: String {
            switch self {
            case .both: return "speaker.wave.2.fill"
            case .textOnly: return "text.bubble.fill"
            case .voiceOnly: return "waveform"
            }
        }
        static var saved: ReplyMode {
            guard let raw = UserDefaults.standard.string(forKey: "vex.voice.replyMode.v1"),
                  let mode = ReplyMode(rawValue: raw) else { return .both }
            return mode
        }
    }

    func setReplyMode(_ mode: ReplyMode) {
        replyMode = mode
        UserDefaults.standard.set(mode.rawValue, forKey: "vex.voice.replyMode.v1")
        switch mode {
        case .both: voiceHint = "Replies: voice + text"
        case .textOnly: voiceHint = "Replies: text only"
        case .voiceOnly: voiceHint = "Replies: voice only"
        }
    }

    private static func preferredVexVoice() -> AVSpeechSynthesisVoice? {
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
if error_marker not in text:
    raise SystemExit("VoiceError marker missing")
text = text.replace(error_marker, voice_modes + error_marker, 1)

# Add a compact response-mode menu beside the mic. It does not interfere with the
# mic toggle: tap mic to listen, tap speaker/text icon to choose output behavior.
textfield_marker = '''            TextField("Say something to Vex…", text: $app.draft)\n'''
mode_menu = '''            Menu {\n                ForEach(VoiceConversationController.ReplyMode.allCases) { mode in\n                    Button {\n                        voice.setReplyMode(mode)\n                    } label: {\n                        Label(mode.title, systemImage: mode.symbol)\n                    }\n                }\n            } label: {\n                Image(systemName: voice.replyMode.symbol)\n                    .font(.headline)\n                    .foregroundStyle(VexTheme.hotPink)\n                    .frame(width: 38, height: 44)\n                    .background(VexTheme.panel)\n                    .clipShape(RoundedRectangle(cornerRadius: 13))\n            }\n            .buttonStyle(.plain)\n            .accessibilityLabel("Vex reply mode: " + voice.replyMode.title)\n\n'''
if textfield_marker not in text:
    raise SystemExit("composer TextField marker missing")
text = text.replace(textfield_marker, mode_menu + textfield_marker, 1)

# Voice-only mode hides assistant bubbles while it is selected, but the response
# remains in app.messages so it can still drive speech, memory and later history.
old_loop = '''                            ForEach(app.messages) { message in\n                                ChatBubble(message: message)\n                                    .id(message.id)\n                            }\n'''
new_loop = '''                            ForEach(app.messages) { message in\n                                if voice.replyMode != .voiceOnly || message.role != .assistant {\n                                    ChatBubble(message: message)\n                                        .id(message.id)\n                                }\n                            }\n'''
once(old_loop, new_loop, "voice-only chat visibility")

# Make the visible status explain what the microphone now does.
text = text.replace('Text(voice.voiceHint)', 'Text(voice.voiceHint)')

path.write_text(text, encoding="utf-8")
for marker in [
    "command = parsed ?? raw",
    "ReplyMode",
    "Voice + Text",
    "preferredVexVoice",
    "voice.replyMode != .voiceOnly",
    "Just talk — I’m listening",
]:
    if marker not in text:
        raise SystemExit(f"missing v0.8.9 marker: {marker}")
print("Applied v0.8.9 conversational voice/reply-mode patch")
