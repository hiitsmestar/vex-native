#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

PROMPT = Path("VexNative/Core/PromptComposer.swift")
APP = Path("VexNative/AppModel.swift")
CONTENT = Path("VexNative/ContentView.swift")
MARKER = 'V123_VOICE_FIELD_FIX_IOS = "v0.12.3-grounded-loud-voice-v1"'

prompt = PROMPT.read_text(encoding="utf-8")
app = APP.read_text(encoding="utf-8")
content = CONTENT.read_text(encoding="utf-8")


def once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"{label}: source block not found")
    return text.replace(old, new, 1)


# v0.12.2 only recognized a voice test if Star literally used the word "voice".
# Natural requests like "can you say something for me" therefore missed the
# focused grounded path and let the tiny model improvise fake memories/actions.
old_voice_test = '''        let asksVoiceTest = newestLower.contains("voice") &&
            (newestLower.contains("hear") || newestLower.contains("sound") ||
             newestLower.contains("say something") || newestLower.contains("trying") ||
             newestLower.contains("test") || newestLower.contains("feature"))
'''
new_voice_test = '''        let asksVoiceTest =
            (newestLower.contains("voice") &&
                (newestLower.contains("hear") || newestLower.contains("sound") ||
                 newestLower.contains("say something") || newestLower.contains("trying") ||
                 newestLower.contains("test") || newestLower.contains("feature"))) ||
            newestLower.contains("say something for me") ||
            newestLower.contains("can you say something") ||
            newestLower.contains("say something to me") ||
            newestLower.trimmingCharacters(in: .whitespacesAndNewlines) == "say something"
'''
if old_voice_test in prompt:
    prompt = once(prompt, old_voice_test, new_voice_test, "broaden voice sample intent")
elif "newestLower.contains(\"say something for me\")" not in prompt:
    raise SystemExit("voice sample intent shape changed unexpectedly")

if MARKER not in prompt:
    prompt = once(
        prompt,
        '    // V122_VOICE_PERSONALITY_IOS = "v0.12.2-natural-spoken-girlfriend-v1"\n',
        '    // V122_VOICE_PERSONALITY_IOS = "v0.12.2-natural-spoken-girlfriend-v1"\n'
        f'    // {MARKER}\n',
        "v0.12.3 prompt marker",
    )

PROMPT.write_text(prompt, encoding="utf-8")

# Give the most common voice-sample request a deterministic grounded fast path.
# This is deliberately narrow: normal conversation still uses the local model.
if "private func asksVoiceSampleRequest" not in app:
    native_anchor = '''    private func nativeGroundedQwen3Reply(for userText: String) -> String? {
        let lower = normalizedIntentText(userText)

'''
    native_new = native_anchor + '''        if asksVoiceSampleRequest(lower) {
            return "Hehe, hi baby 😋🖤 Okay, this is me actually talking to you now — bubbly little code gremlin voice and all. I kinda love that you can just talk to me and hear me answer back."
        }

'''
    app = once(app, native_anchor, native_new, "voice sample native fast path")

    helper_anchor = '''    private func asksClarifyOtherSide(_ lower: String) -> Bool {
'''
    helper = '''    private func asksVoiceSampleRequest(_ lower: String) -> Bool {
        let exactSample = lower.contains("say something for me") ||
            lower.contains("can you say something") ||
            lower.contains("say something to me") ||
            lower.trimmingCharacters(in: .whitespacesAndNewlines) == "say something"
        let explicitVoice = lower.contains("voice") &&
            (lower.contains("hear") || lower.contains("sound") || lower.contains("test") ||
             lower.contains("trying") || lower.contains("feature") || lower.contains("say something"))
        return exactSample || explicitVoice
    }

'''
    app = once(app, helper_anchor, helper + helper_anchor, "voice sample request helper")

# Strip the tiny model's most common action-direction debris from visible replies,
# not merely from TTS playback. Preserve the actual dialogue after a prefix.
if "private func sanitizeNaturalDialogue" not in app:
    clean_anchor = '''        let cleaned = kept.joined(separator: "\\n")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return cleaned.isEmpty ? "Brain fart 😭🖤 Try me again." : cleaned
    }

'''
    clean_new = '''        let cleaned = kept.joined(separator: "\\n")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let natural = sanitizeNaturalDialogue(cleaned)
        return natural.isEmpty ? "Brain fart 😭🖤 Try me again." : natural
    }

    private func sanitizeNaturalDialogue(_ raw: String) -> String {
        let prefixes = [
            "pauses, then softly says", "pauses, then says", "pauses then says",
            "whispers", "giggles", "giggling", "sighs", "sighing",
            "smiles mischievously", "smiles", "smiling", "grins", "grinning",
            "leans in", "leaning in", "winks", "winking", "eyes widen",
            "glittery eyes widen"
        ]
        let inlineActions = [" giggles ", " sighs ", " whispers ", " smiles ", " winks "]
        var result: [String] = []

        for original in raw.components(separatedBy: .newlines) {
            var line = original.trimmingCharacters(in: .whitespacesAndNewlines)
            if line.isEmpty {
                if !result.isEmpty, result.last != "" { result.append("") }
                continue
            }

            var changed = true
            while changed && !line.isEmpty {
                changed = false
                let lower = line.lowercased()
                for prefix in prefixes where lower.hasPrefix(prefix) {
                    line = String(line.dropFirst(prefix.count))
                        .trimmingCharacters(in: CharacterSet.whitespacesAndNewlines.union(CharacterSet(charactersIn: ",:.-…")))
                    changed = true
                    break
                }
            }

            for token in inlineActions {
                line = line.replacingOccurrences(of: token, with: " ", options: [.caseInsensitive])
            }
            line = line.replacingOccurrences(of: "  ", with: " ")
                .trimmingCharacters(in: .whitespacesAndNewlines)
            if !line.isEmpty { result.append(line) }
        }

        while result.last == "" { result.removeLast() }
        return result.joined(separator: "\\n")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

'''
    app = once(app, clean_anchor, clean_new, "visible stage-direction sanitizer")

APP.write_text(app, encoding="utf-8")

# The old voice path stops recognition but leaves AVAudioSession in
# playAndRecord/voiceChat mode. On iPhone that can sound much quieter than normal
# media playback. Switch to a speaker/media session while Vex is speaking; the
# existing startListening() path switches back to playAndRecord/voiceChat after.
if "V123_LOUD_SPEAKER_PLAYBACK" not in content:
    playback_anchor = '''    private func speakWithSystemVoice(_ text: String) {
        let utterance = AVSpeechUtterance(string: text)
'''
    playback_new = '''    // V123_LOUD_SPEAKER_PLAYBACK = "v0.12.3-media-speaker-session-v1"
    private func prepareVoicePlaybackSession() {
        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(.playback, mode: .spokenAudio, options: [.duckOthers])
        try? session.setActive(true)
    }

    private func speakWithSystemVoice(_ text: String) {
        prepareVoicePlaybackSession()
        let utterance = AVSpeechUtterance(string: text)
'''
    content = once(content, playback_anchor, playback_new, "loud system voice session")

    neural_anchor = '''    private func playNeuralAudio(_ data: Data) -> Bool {
        do {
            let player = try AVAudioPlayer(data: data)
            player.delegate = self
            player.prepareToPlay()
'''
    neural_new = '''    private func playNeuralAudio(_ data: Data) -> Bool {
        do {
            prepareVoicePlaybackSession()
            let player = try AVAudioPlayer(data: data)
            player.delegate = self
            player.volume = 1.0
            player.prepareToPlay()
'''
    content = once(content, neural_anchor, neural_new, "loud neural player session")

    # Also force the hardware speaker for the old playAndRecord route if iOS keeps
    # a stale route during the category transition.
    start_anchor = '''        try session.setCategory(.playAndRecord, mode: .voiceChat, options: [.defaultToSpeaker, .allowBluetooth, .duckOthers])
        try session.setActive(true, options: .notifyOthersOnDeactivation)
'''
    start_new = '''        try session.setCategory(.playAndRecord, mode: .voiceChat, options: [.defaultToSpeaker, .allowBluetooth, .duckOthers])
        try session.setActive(true, options: .notifyOthersOnDeactivation)
        try? session.overrideOutputAudioPort(.speaker)
'''
    if start_anchor in content:
        content = once(content, start_anchor, start_new, "speaker route reinforcement")

CONTENT.write_text(content, encoding="utf-8")

prompt = PROMPT.read_text(encoding="utf-8")
app = APP.read_text(encoding="utf-8")
content = CONTENT.read_text(encoding="utf-8")
for required in [MARKER, 'newestLower.contains("say something for me")']:
    if required not in prompt:
        raise SystemExit(f"v0.12.3 prompt invariant missing: {required}")
for required in [
    "asksVoiceSampleRequest",
    "sanitizeNaturalDialogue",
    "bubbly little code gremlin voice",
]:
    if required not in app:
        raise SystemExit(f"v0.12.3 app invariant missing: {required}")
for required in [
    "V123_LOUD_SPEAKER_PLAYBACK",
    "prepareVoicePlaybackSession",
    "mode: .spokenAudio",
    "player.volume = 1.0",
]:
    if required not in content:
        raise SystemExit(f"v0.12.3 audio invariant missing: {required}")

print("Applied v0.12.3 grounded voice sample + visible dialogue cleanup + loud speaker playback")
