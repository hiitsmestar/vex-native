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
    prompt = prompt.replace(old_voice_test, new_voice_test, 1)
elif 'newestLower.contains("say something for me")' not in prompt:
    raise SystemExit("voice sample intent shape changed unexpectedly")

if MARKER not in prompt:
    marker_anchor = '    // V122_VOICE_PERSONALITY_IOS = "v0.12.2-natural-spoken-girlfriend-v1"\n'
    if marker_anchor not in prompt:
        raise SystemExit("v0.12.2 prompt marker missing")
    prompt = prompt.replace(marker_anchor, marker_anchor + f'    // {MARKER}\n', 1)
PROMPT.write_text(prompt, encoding="utf-8")

# v0.11.2 intentionally replaced the old native canned reply function with a
# grounded directive. For this one narrow UI voice-sample request we want an
# actually deterministic reply so the 0.6B model cannot invent fake history.
if "private func asksVoiceSampleRequest" not in app:
    send_anchor = '''        let groundedDirective = isQwen3 ? nativeGroundedQwen3Directive(for: text) : nil

'''
    if send_anchor not in app:
        raise SystemExit("natural-continuity groundedDirective send anchor missing")
    fast_path = send_anchor + '''        if isQwen3, asksVoiceSampleRequest(normalizedIntentText(text)) {
            profile.messages.append(ChatMessage(
                role: .assistant,
                content: "Hehe, hi baby 😋🖤 Okay, this is me actually talking to you now — bubbly little code gremlin voice and all. I kinda love that you can just talk to me and hear me answer back."
            ))
            touchRelevantMemories(for: text)
            persist()
            isGenerating = false
            return
        }

'''
    app = app.replace(send_anchor, fast_path, 1)

    helper_anchor = "    private func nativeGroundedQwen3Directive"
    helper_at = app.find(helper_anchor)
    if helper_at < 0:
        raise SystemExit("nativeGroundedQwen3Directive helper anchor missing")
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
    app = app[:helper_at] + helper + app[helper_at:]

# Clean visible text as a final safety layer, not just the spoken copy.
if "private func sanitizeNaturalDialogue" not in app:
    return_marker = 'return cleaned.isEmpty ? "Brain fart 😭🖤 Try me again." : cleaned'
    return_at = app.find(return_marker)
    if return_at < 0:
        raise SystemExit("cleanGeneratedReply final return marker missing")
    app = app[:return_at] + '''let natural = sanitizeNaturalDialogue(cleaned)
        return natural.isEmpty ? "Brain fart 😭🖤 Try me again." : natural''' + app[return_at + len(return_marker):]

    function_end = app.find("\n    }", return_at)
    if function_end < 0:
        raise SystemExit("cleanGeneratedReply closing brace missing")
    function_end += len("\n    }\n")
    sanitizer = '''
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
    app = app[:function_end] + sanitizer + app[function_end:]
APP.write_text(app, encoding="utf-8")

# Switch from the microphone's call-style audio session to normal spoken-media
# playback while Vex talks. startListening() restores playAndRecord/voiceChat.
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

    start_anchor = '''        try session.setCategory(.playAndRecord, mode: .voiceChat, options: [.defaultToSpeaker, .allowBluetooth, .duckOthers])
        try session.setActive(true, options: .notifyOthersOnDeactivation)
'''
    if start_anchor in content:
        content = content.replace(
            start_anchor,
            start_anchor + '        try? session.overrideOutputAudioPort(.speaker)\n',
            1,
        )
CONTENT.write_text(content, encoding="utf-8")

prompt = PROMPT.read_text(encoding="utf-8")
app = APP.read_text(encoding="utf-8")
content = CONTENT.read_text(encoding="utf-8")
for required in [MARKER, 'newestLower.contains("say something for me")']:
    if required not in prompt:
        raise SystemExit(f"v0.12.3 prompt invariant missing: {required}")
for required in ["asksVoiceSampleRequest", "sanitizeNaturalDialogue", "bubbly little code gremlin voice"]:
    if required not in app:
        raise SystemExit(f"v0.12.3 app invariant missing: {required}")
for required in ["V123_LOUD_SPEAKER_PLAYBACK", "prepareVoicePlaybackSession", "mode: .spokenAudio", "player.volume = 1.0"]:
    if required not in content:
        raise SystemExit(f"v0.12.3 audio invariant missing: {required}")

print("Applied v0.12.3 grounded voice sample + visible dialogue cleanup + loud speaker playback")
