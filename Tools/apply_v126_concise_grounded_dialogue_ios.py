#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

APP = Path("VexNative/AppModel.swift")
PROMPT = Path("VexNative/Core/PromptComposer.swift")
MARKER = 'V126_CONCISE_GROUNDED_DIALOGUE_IOS = "v0.12.6-concise-grounded-dialogue-v1"'

app = APP.read_text(encoding="utf-8")
prompt = PROMPT.read_text(encoding="utf-8")

# v0.12.5 proved that a larger ceiling alone just lets the tiny model ramble
# farther before it hits the next ceiling. Leave a modest amount of headroom,
# then constrain ordinary dialogue to short complete answers.
if "webGroundedTurn ? 240 : 192" in app:
    app = app.replace("webGroundedTurn ? 240 : 192", "webGroundedTurn ? 256 : 224", 1)
elif "maxNewTokens = 192" in app:
    app = app.replace("maxNewTokens = 192", "maxNewTokens = 224", 1)
elif "webGroundedTurn ? 256 : 224" not in app and "maxNewTokens = 224" not in app:
    raise SystemExit("v0.12.6 token budget anchor missing")

if MARKER not in prompt:
    anchor = '    // V123_VOICE_FIELD_FIX_IOS = "v0.12.3-grounded-loud-voice-v1"\n'
    if anchor not in prompt:
        anchor = '    // V122_VOICE_PERSONALITY_IOS = "v0.12.2-natural-spoken-girlfriend-v1"\n'
    if anchor not in prompt:
        raise SystemExit("v0.12.6 prompt marker anchor missing")
    prompt = prompt.replace(anchor, anchor + f'    // {MARKER}\n', 1)

# Patch the actual Qwen3 system prompt instead of introducing a detached helper.
# The field failures were: third-person stage narration, invented autobiographical
# memory, role reversal on a voice question, and long replies that ran into the
# generation ceiling.
old_rules = '''            No parenthetical, asterisk, or bare stage directions such as “grinning”, “smiling”, “winking”, “sipping”, or “nudging”.
            Do not repeat or lightly paraphrase your previous reply.
            Never write Star's dialogue or role labels. Produce one Vex reply and stop.
            Usually answer in 1 to 3 natural sentences.
'''
new_rules = '''            No parenthetical, asterisk, italicized, or bare stage directions. Never narrate Star or Vex in third person and never write actions such as “Star tilts her head”, “Vex smiles”, “grinning”, “smiling”, “winking”, “sipping”, or “nudging”.
            Never invent a memory or past event. Only say “I remember” when a specific supplied RELEVANT MEMORY or recent chat line actually supports the memory you name.
            For questions about your own voice, behavior, feelings, or improvements, answer about Vex; do not turn the answer into a description of Star.
            Do not repeat or lightly paraphrase your previous reply.
            Never write Star's dialogue or role labels. Produce one Vex reply and stop.
            Keep ordinary spoken replies compact: usually 2 to 4 complete sentences. Finish the thought you start and do not begin another idea near the end of the answer.
'''
if old_rules in prompt:
    prompt = prompt.replace(old_rules, new_rules, 1)
elif "Keep ordinary spoken replies compact: usually 2 to 4 complete sentences." not in prompt:
    raise SystemExit("v0.12.6 Qwen3 response rules anchor missing")

PROMPT.write_text(prompt, encoding="utf-8")

# Strip pure markdown-italic narration lines such as the field-test output
# '*star tilts her head slightly...*' and obvious third-person action lines.
if "V126_STAGE_DIRECTION_LINE_FILTER" not in app:
    needle = '''            var line = original.trimmingCharacters(in: .whitespacesAndNewlines)
            if line.isEmpty {
'''
    if needle not in app:
        raise SystemExit("v0.12.6 sanitizer line anchor missing")
    replacement = '''            var line = original.trimmingCharacters(in: .whitespacesAndNewlines)
            // V126_STAGE_DIRECTION_LINE_FILTER = "v0.12.6-italic-narration-v1"
            if line.count >= 2 && line.hasPrefix("*") && line.hasSuffix("*") && !line.hasPrefix("**") {
                continue
            }
            let lowerNarration = line.lowercased()
            if (lowerNarration.hasPrefix("star ") || lowerNarration.hasPrefix("vex ")) &&
                (lowerNarration.contains("tilts ") || lowerNarration.contains("looks ") ||
                 lowerNarration.contains("smiles ") || lowerNarration.contains("leans ") ||
                 lowerNarration.contains("studying ") || lowerNarration.contains("pauses ")) {
                continue
            }
            if line.isEmpty {
'''
    app = app.replace(needle, replacement, 1)

# Apply a final visible-answer guard that always ends on a complete sentence when
# the model produced at least one sentence. If there is no punctuation at all,
# close the short fragment instead of exposing a raw cutoff.
if "private func enforceCompletedVisibleReply" not in app:
    helper_anchor = "    private func finishReplyAtNaturalBoundary(_ raw: String) -> String {\n"
    if helper_anchor not in app:
        raise SystemExit("v0.12.6 completion helper anchor missing")
    helper = '''    private func enforceCompletedVisibleReply(_ raw: String) -> String {
        let text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return text }
        if let last = text.last, ".!?…".contains(last) { return text }

        var lastBoundary: String.Index?
        for idx in text.indices {
            if ".!?…".contains(text[idx]) { lastBoundary = text.index(after: idx) }
        }
        if let boundary = lastBoundary {
            let completed = String(text[..<boundary]).trimmingCharacters(in: .whitespacesAndNewlines)
            if !completed.isEmpty { return completed }
        }
        return text + "."
    }

'''
    app = app.replace(helper_anchor, helper + helper_anchor, 1)

append_anchor = "profile.messages.append(ChatMessage(role: .assistant, content: finalAnswer))"
if append_anchor in app:
    parts = app.split(append_anchor)
    rebuilt = parts[0]
    for tail in parts[1:]:
        if "enforceCompletedVisibleReply(finalAnswer)" not in rebuilt[-180:]:
            rebuilt += "finalAnswer = enforceCompletedVisibleReply(finalAnswer)\n            "
        rebuilt += append_anchor + tail
    app = rebuilt

APP.write_text(app, encoding="utf-8")

check_app = APP.read_text(encoding="utf-8")
check_prompt = PROMPT.read_text(encoding="utf-8")
for required in ["enforceCompletedVisibleReply", "V126_STAGE_DIRECTION_LINE_FILTER"]:
    if required not in check_app:
        raise SystemExit(f"v0.12.6 app invariant missing: {required}")
for required in [
    MARKER,
    "Keep ordinary spoken replies compact: usually 2 to 4 complete sentences.",
    "Never invent a memory or past event.",
    "For questions about your own voice, behavior, feelings, or improvements, answer about Vex",
]:
    if required not in check_prompt:
        raise SystemExit(f"v0.12.6 prompt invariant missing: {required}")
if "webGroundedTurn ? 256 : 224" not in check_app and "maxNewTokens = 224" not in check_app:
    raise SystemExit("v0.12.6 final token budget missing")

print("Applied v0.12.6 concise grounded dialogue + hard visible completion")
