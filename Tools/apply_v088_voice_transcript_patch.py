#!/usr/bin/env python3
from pathlib import Path

path = Path("VexNative/ContentView.swift")
text = path.read_text(encoding="utf-8")

def once(old: str, new: str, label: str):
    global text
    if old not in text:
        raise SystemExit(f"{label}: source block not found")
    text = text.replace(old, new, 1)

# Make the listening state observable enough to diagnose real microphone pickup.
once(
'''    @Published private(set) var partialTranscript = ""\n''',
'''    @Published private(set) var partialTranscript = ""\n    @Published private(set) var lastHeard = ""\n    @Published private(set) var voiceHint = "Say ‘Vex …’"\n''',
"published voice diagnostics",
)

once(
'''    private var waitingForReply = false\n    private var inputTapInstalled = false\n''',
'''    private var waitingForReply = false\n    private var inputTapInstalled = false\n    private var wakeArmedUntil: Date?\n''',
"wake armed state",
)

# Don't hard-require Apple's on-device recognizer asset. Some supported devices
# report support but don't have the language asset ready, which can look like a
# perfectly green microphone that never yields text. Let Speech choose the best
# available recognizer path instead.
once(
'''        if recognizer.supportsOnDeviceRecognition { request.requiresOnDeviceRecognition = true }\n''',
'''        // Prefer reliability here: Speech may use the on-device recognizer when available,\n        // but we do not hard-require the local language asset.\n''',
"remove forced on-device recognition",
)

# Show every partial transcription immediately.
once(
'''        if let transcript, !transcript.isEmpty {\n            partialTranscript = transcript\n            silenceTimer?.invalidate()\n''',
'''        if let transcript, !transcript.isEmpty {\n            partialTranscript = transcript\n            lastHeard = transcript\n            voiceHint = "Heard: " + transcript\n            silenceTimer?.invalidate()\n''',
"live transcript",
)

# Natural wake flow: either say "Vex, do X" in one utterance or say "Vex" and
# the next utterance becomes the command for eight seconds.
old_commit = '''        guard isHandsFree, !raw.isEmpty else { restartListeningSoon(); return }\n        guard let command = Self.commandAfterWakePhrase(raw), !command.isEmpty else { restartListeningSoon(); return }\n\n        waitingForReply = true\n        onCommand?(command)\n'''
new_commit = '''        guard isHandsFree, !raw.isEmpty else { restartListeningSoon(); return }\n\n        let now = Date()\n        let armed = wakeArmedUntil.map { $0 > now } ?? false\n        var command: String?\n        if armed {\n            wakeArmedUntil = nil\n            command = raw\n        } else {\n            let parsed = Self.commandAfterWakePhrase(raw)\n            if parsed == "__WAKE_ONLY__" {\n                wakeArmedUntil = now.addingTimeInterval(8)\n                voiceHint = "Yep? Listening for your command…"\n                restartListeningSoon()\n                return\n            }\n            command = parsed\n        }\n\n        guard let command, !command.isEmpty else {\n            voiceHint = "Heard you — say ‘Vex …’ first"\n            restartListeningSoon()\n            return\n        }\n\n        voiceHint = "Sending: " + command\n        waitingForReply = true\n        onCommand?(command)\n'''
once(old_commit, new_commit, "wake command flow")

# Expand wake phrase tolerance and distinguish wake-only from a command.
start = text.find('    private static func commandAfterWakePhrase(_ raw: String) -> String? {')
end = text.find('    private static func spokenText', start)
if start < 0 or end < 0:
    raise SystemExit("wake parser bounds missing")
new_parser = r'''    private static func commandAfterWakePhrase(_ raw: String) -> String? {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        let lower = trimmed.lowercased()
        let prefixes = ["hey vex", "okay vex", "ok vex", "vex", "hey vicks", "vicks"]

        guard let prefix = prefixes.first(where: {
            lower == $0 || lower.hasPrefix($0 + " ") || lower.hasPrefix($0 + ",") || lower.hasPrefix($0 + ":")
        }) else { return nil }

        if lower == prefix { return "__WAKE_ONLY__" }
        let index = trimmed.index(trimmed.startIndex, offsetBy: prefix.count)
        let command = String(trimmed[index...])
            .trimmingCharacters(in: CharacterSet.whitespacesAndNewlines.union(CharacterSet(charactersIn: ",:.-")))
        return command.isEmpty ? "__WAKE_ONLY__" : command
    }

'''
text = text[:start] + new_parser + text[end:]

# Reset diagnostics when hands-free starts/stops.
once(
'''        isHandsFree = true\n        waitingForReply = false\n        do {\n''',
'''        isHandsFree = true\n        waitingForReply = false\n        lastHeard = ""\n        voiceHint = "Say ‘Vex …’"\n        wakeArmedUntil = nil\n        do {\n''',
"start diagnostics",
)
once(
'''        isHandsFree = false\n        waitingForReply = false\n        synthesizer.stopSpeaking(at: .immediate)\n''',
'''        isHandsFree = false\n        waitingForReply = false\n        wakeArmedUntil = nil\n        voiceHint = "Voice off"\n        synthesizer.stopSpeaking(at: .immediate)\n''',
"stop diagnostics",
)

# Replace the terse status label with a real visible signal showing whether the
# recognizer is hearing words, waiting for the wake phrase, or sending a command.
old_status = '''            if voice.isHandsFree {\n                Text(voice.isListening ? "• 🎙️ listening" : "• 🔊 voice")\n                    .font(.caption)\n                    .foregroundStyle(voice.isListening ? Color.green : VexTheme.muted)\n            }\n\n'''
new_status = '''            if voice.isHandsFree {\n                VStack(alignment: .leading, spacing: 1) {\n                    Text(voice.isListening ? "• 🎙️ listening" : "• 🔊 voice")\n                        .font(.caption)\n                        .foregroundStyle(voice.isListening ? Color.green : VexTheme.muted)\n                    Text(voice.voiceHint)\n                        .font(.caption2)\n                        .foregroundStyle(VexTheme.muted)\n                        .lineLimit(1)\n                        .truncationMode(.tail)\n                }\n            }\n\n'''
once(old_status, new_status, "voice status diagnostics")

path.write_text(text, encoding="utf-8")
for marker in ["lastHeard", "voiceHint", "wakeArmedUntil", "__WAKE_ONLY__", "Heard: "]:
    if marker not in text:
        raise SystemExit(f"missing v0.8.8 marker: {marker}")
print("Applied v0.8.8 voice transcript/reliability patch")
