#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

PATH = Path("VexNative/ContentView.swift")
text = PATH.read_text(encoding="utf-8")


def once(old: str, new: str, label: str) -> None:
    global text
    if old not in text:
        raise SystemExit(f"{label}: source block not found")
    text = text.replace(old, new, 1)


if "V121_VOICE_FOUNDATION_IOS" in text:
    print("v0.12.1 iOS voice foundation already applied")
    raise SystemExit(0)

for required in [
    "final class VoiceConversationController",
    "enum SpeechEngine: String, CaseIterable, Identifiable",
    'components.path = "/tts/speak"',
    '"audio_base64"',
    "VexVoiceSettingsView",
]:
    if required not in text:
        raise SystemExit(f"v0.12.1 iOS voice foundation requires historical voice chain marker: {required}")

# Preserve existing saved pcNeural/iphone choices while making a future-proof Auto
# mode the default for new installs. Auto can resolve to a local neural provider on
# the dedicated AI PC later without another iPhone UI/API rewrite.
old_engine = '''    enum SpeechEngine: String, CaseIterable, Identifiable {
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
'''
new_engine = '''    enum SpeechEngine: String, CaseIterable, Identifiable {
        case automatic
        case pcNeural
        case iphone

        var id: String { rawValue }
        var title: String {
            switch self {
            case .automatic: return "Auto"
            case .pcNeural: return "Bridge Voice"
            case .iphone: return "iPhone Local"
            }
        }
        var detail: String {
            switch self {
            case .automatic:
                return "Use the paired Vex Bridge voice provider when available, then fall back to the iPhone. This same route can become fully local on the dedicated AI PC."
            case .pcNeural:
                return "Use the paired Vex Bridge voice provider. The current lightweight Edge neural provider needs internet; a future custom local provider uses the same contract."
            case .iphone:
                return "Use only the best installed iPhone system voice. No PC voice provider is contacted."
            }
        }
        static var saved: SpeechEngine {
            guard let raw = UserDefaults.standard.string(forKey: "vex.voice.engine.v1"),
                  let value = SpeechEngine(rawValue: raw) else { return .automatic }
            return value
        }
    }
'''
once(old_engine, new_engine, "speech engine contract")

old_setter = '''    func setSpeechEngine(_ engine: SpeechEngine) {
        speechEngine = engine
        UserDefaults.standard.set(engine.rawValue, forKey: "vex.voice.engine.v1")
        voiceHint = engine == .pcNeural ? "Voice: PC neural" : "Voice: iPhone local"
    }
'''
new_setter = '''    func setSpeechEngine(_ engine: SpeechEngine) {
        speechEngine = engine
        UserDefaults.standard.set(engine.rawValue, forKey: "vex.voice.engine.v1")
        switch engine {
        case .automatic: voiceHint = "Voice: automatic Bridge → iPhone"
        case .pcNeural: voiceHint = "Voice: Bridge provider"
        case .iphone: voiceHint = "Voice: iPhone local"
        }
    }
'''
once(old_setter, new_setter, "speech engine setter")

once(
    '''    private func speakPrepared(_ text: String) async {
        if speechEngine == .pcNeural {
''',
    '''    private func speakPrepared(_ text: String) async {
        if speechEngine != .iphone {
''',
    "automatic bridge speech routing",
)

payload_anchor = '''                "text": String(text.prefix(1800)),
                "voice": neuralVoice.rawValue,
                "rate": Int(neuralRate.rounded()),
'''
payload_new = '''                "text": String(text.prefix(1800)),
                "provider": speechEngine == .automatic ? "auto" : "edge-neural",
                "voice": neuralVoice.rawValue,
                "rate": Int(neuralRate.rounded()),
'''
once(payload_anchor, payload_new, "provider-aware TTS request")

# A mic tap while Vex is speaking now means "stop talking and listen" instead of
# turning the whole hands-free session off. A mic tap while already listening still
# turns hands-free off, preserving the old quick toggle behavior.
old_toggle = '''    func toggleHandsFree() async throws {
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
'''
new_toggle = '''    func toggleHandsFree() async throws {
        if isHandsFree {
            if isSpeechOutputActive {
                interruptSpeechAndListen()
                return
            }
            stopHandsFree()
            return
        }
        guard await requestSpeechPermission() else { throw VoiceError.speechPermission }
        guard await requestMicPermission() else { throw VoiceError.microphonePermission }
        isHandsFree = true
        waitingForReply = false
        try startListening()
    }

    func interruptSpeechAndListen() {
        guard isHandsFree else { return }
        speechTask?.cancel()
        speechTask = nil
        neuralRequestInFlight = false
        neuralPlayer?.stop()
        neuralPlayer = nil
        synthesizer.stopSpeaking(at: .immediate)
        waitingForReply = false
        stopRecognition()
        voiceHint = "Interrupted — listening…"
        restartListeningSoon()
    }
'''
once(old_toggle, new_toggle, "voice interruption behavior")

old_detail = '''                    Text(voice.speechEngine == .pcNeural
                         ? "Natural neural speech through either paired Vex Bridge. Falls back to the iPhone voice if both PCs or the internet are unavailable."
                         : "Fully local iPhone speech with the best installed Vex-like system voice.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
'''
new_detail = '''                    Text(voice.speechEngine.detail)
                        .font(.caption)
                        .foregroundStyle(.secondary)
'''
once(old_detail, new_detail, "voice engine explanation")

once(
    "                if voice.speechEngine == .pcNeural {\n",
    "                if voice.speechEngine != .iphone {\n",
    "voice tuning visibility",
)

# Keep a plain source marker that CI can prove survived every later iOS patch.
web_marker = "// MARK: - Web Brain v0.6\n"
if web_marker not in text:
    raise SystemExit("Web Brain marker missing for voice foundation marker")
text = text.replace(
    web_marker,
    '// V121_VOICE_FOUNDATION_IOS = "v0.12.1-swap-ready-voice-v1"\n' + web_marker,
    1,
)

PATH.write_text(text, encoding="utf-8")

for marker in [
    'V121_VOICE_FOUNDATION_IOS = "v0.12.1-swap-ready-voice-v1"',
    "case automatic",
    'return "Bridge Voice"',
    '"provider": speechEngine == .automatic ? "auto" : "edge-neural"',
    "func interruptSpeechAndListen()",
    'voiceHint = "Interrupted — listening…"',
    "Text(voice.speechEngine.detail)",
]:
    if marker not in text:
        raise SystemExit(f"v0.12.1 iOS voice invariant missing: {marker}")

print("Applied v0.12.1 iOS automatic/swap-ready voice routing and tap-to-interrupt behavior")
