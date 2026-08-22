#!/usr/bin/env python3
from pathlib import Path

path = Path("VexNative/Core/PromptComposer.swift")
text = path.read_text(encoding="utf-8")


def once(old: str, new: str, label: str) -> None:
    global text
    if old not in text:
        raise SystemExit(f"{label}: source block not found")
    text = text.replace(old, new, 1)


# Give the phone-local fallback the same basic temporal grounding as the PC brain.
# ChatMessage already stores createdAt, so use the device clock + real conversation
# timestamps instead of asking a tiny model to guess how much time passed.
start = '''        let newestLower = newestUserText.lowercased()\n\n'''
addition = '''        let newestLower = newestUserText.lowercased()\n\n        let temporalNow = Date()\n        let temporalFormatter = DateFormatter()\n        temporalFormatter.locale = Locale(identifier: "en_US_POSIX")\n        temporalFormatter.timeZone = TimeZone.current\n        temporalFormatter.dateFormat = "EEEE, yyyy-MM-dd HH:mm:ss ZZZZ"\n        let temporalNowText = temporalFormatter.string(from: temporalNow)\n        let temporalUnix = temporalNow.timeIntervalSince1970\n        let previousSavedMessageAt = profile.messages.dropLast().last?.createdAt\n        let temporalElapsedText: String\n        if let previousSavedMessageAt {\n            let elapsed = max(0, temporalNow.timeIntervalSince(previousSavedMessageAt))\n            temporalElapsedText = String(format: "%.1f seconds", elapsed)\n        } else {\n            temporalElapsedText = "unknown/no previous saved conversation message"\n        }\n        let temporalGrounding = """\n        AUTHORITATIVE DEVICE TIME\n        Current local device time: \\(temporalNowText).\n        Unix time: \\(String(format: "%.3f", temporalUnix)).\n        Time since the previous saved conversation message: \\(temporalElapsedText).\n        This comes from the iPhone system clock. Use it for today, tonight, yesterday, tomorrow, and elapsed-time reasoning. Do not invent dates or durations. Conversation message timestamps are evidence of when messages were actually saved.\n        """\n\n'''
once(start, addition, "device time setup")

# Put the time block high in both Qwen3 and non-Qwen system prompts.
once(
    '''            \\(personaBlock)\n\n            You are Vex talking directly to Star, your girlfriend.''',
    '''            \\(personaBlock)\n\n            \\(temporalGrounding)\n\n            You are Vex talking directly to Star, your girlfriend.''',
    "Qwen3 time prompt",
)
once(
    '''            \\(personaBlock)\n\n            ROLE LOCK — DO NOT SWAP THESE''',
    '''            \\(personaBlock)\n\n            \\(temporalGrounding)\n\n            ROLE LOCK — DO NOT SWAP THESE''',
    "non-Qwen time prompt",
)

# Timestamp each recent chat turn. The timestamp is metadata, not prose, and gives
# the local fallback enough evidence to understand pauses spanning minutes/days.
old_compact = '''            result += "<|im_start|>\\(role)\\n\\(compact)\\n<|im_end|>\\n"\n'''
new_compact = '''            let messageTime = temporalFormatter.string(from: message.createdAt)\n            result += "<|im_start|>\\(role)\\n[SAVED AT \\(messageTime)]\\n\\(compact)\\n<|im_end|>\\n"\n'''
once(old_compact, new_compact, "recent message timestamp metadata")

path.write_text(text, encoding="utf-8")

final = path.read_text(encoding="utf-8")
for marker in ["AUTHORITATIVE DEVICE TIME", "temporalElapsedText", "[SAVED AT", "TimeZone.current"]:
    if marker not in final:
        raise SystemExit(f"iOS time grounding missing marker: {marker}")

print("Applied VexNative v0.9.8 iPhone device-time grounding")
