#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

APP = Path("VexNative/AppModel.swift")
PROMPT = Path("VexNative/Core/PromptComposer.swift")
MARKER = 'V126_CONCISE_GROUNDED_DIALOGUE_IOS = "v0.12.6-concise-grounded-dialogue-v1"'

app = APP.read_text(encoding="utf-8")
prompt = PROMPT.read_text(encoding="utf-8")

# Field test on v0.12.5 showed that simply raising the token ceiling encouraged
# the tiny model to ramble until it found the new ceiling. Give it a little more
# room, but more importantly teach it to finish in a compact number of sentences.
if "webGroundedTurn ? 240 : 192" in app:
    app = app.replace("webGroundedTurn ? 240 : 192", "webGroundedTurn ? 256 : 224", 1)
elif "maxNewTokens = 192" in app:
    app = app.replace("maxNewTokens = 192", "maxNewTokens = 224", 1)
elif "webGroundedTurn ? 256 : 224" not in app and "maxNewTokens = 224" not in app:
    raise SystemExit("v0.12.6 token budget anchor missing")

# Strengthen the prompt at the existing v0.12.2/v0.12.3 personality marker.
if MARKER not in prompt:
    anchor = '    // V123_VOICE_FIELD_FIX_IOS = "v0.12.3-grounded-loud-voice-v1"\n'
    if anchor not in prompt:
        anchor = '    // V122_VOICE_PERSONALITY_IOS = "v0.12.2-natural-spoken-girlfriend-v1"\n'
    if anchor not in prompt:
        raise SystemExit("v0.12.6 prompt marker anchor missing")
    prompt = prompt.replace(anchor, anchor + f'    // {MARKER}\n', 1)

# Insert durable dialogue rules near the voice-test/personality logic. These
# rules address the exact v0.12.5 field failures: third-person stage directions,
# invented memories, role reversal, and runaway unfinished replies.
rules = '''\n        // v0.12.6 field-grounding rules for the tiny local model.\n        let conciseGroundedDialogueRules = """\n        Speak only as Vex, directly to Star. Never narrate Star or Vex in third person and never write stage directions, actions, screenplay text, or roleplay narration. Do not invent memories, past events, possessions, appearance details, feelings, or relationship history that are not explicitly present in supplied memory/context. Keep ordinary spoken replies concise: usually 2 to 4 complete sentences. Finish the thought you start; do not begin another idea when the remaining answer budget is low. For questions about your own voice or behavior, answer about Vex, not Star.\n        """\n'''

if "let conciseGroundedDialogueRules" not in prompt:
    target = "        let asksVoiceTest ="
    at = prompt.find(target)
    if at < 0:
        raise SystemExit("v0.12.6 asksVoiceTest anchor missing")
    prompt = prompt[:at] + rules + prompt[at:]

# Make sure the new rules are actually included in the composed prompt. Prefer
# the first existing voice/personality instruction interpolation point.
if "conciseGroundedDialogueRules" in prompt and "\\(conciseGroundedDialogueRules)" not in prompt:
    candidates = [
        '        var instructions = """',
        '        let instructions = """',
        '        return """',
    ]
    inserted = False
    for c in candidates:
        idx = prompt.find(c)
        if idx >= 0:
            nl = prompt.find("\n", idx)
            prompt = prompt[:nl+1] + "        \\(conciseGroundedDialogueRules)\n" + prompt[nl+1:]
            inserted = True
            break
    if not inserted:
        raise SystemExit("v0.12.6 prompt composition anchor missing")

PROMPT.write_text(prompt, encoding="utf-8")

# Strip pure markdown-italic narration lines such as the field-test output
# '*star tilts her head slightly...*'. Keep ordinary italic emphasis embedded in
# real dialogue.
if "V126_STAGE_DIRECTION_LINE_FILTER" not in app:
    needle = '''            var line = original.trimmingCharacters(in: .whitespacesAndNewlines)\n            if line.isEmpty {\n'''
    if needle not in app:
        raise SystemExit("v0.12.6 sanitizer line anchor missing")
    replacement = '''            var line = original.trimmingCharacters(in: .whitespacesAndNewlines)\n            // V126_STAGE_DIRECTION_LINE_FILTER = "v0.12.6-italic-narration-v1"\n            if line.count >= 2 && line.hasPrefix("*") && line.hasSuffix("*") && !line.hasPrefix("**") {\n                continue\n            }\n            let lowerNarration = line.lowercased()\n            if (lowerNarration.hasPrefix("star ") || lowerNarration.hasPrefix("vex ")) &&\n                (lowerNarration.contains("tilts ") || lowerNarration.contains("looks ") ||\n                 lowerNarration.contains("smiles ") || lowerNarration.contains("leans ") ||\n                 lowerNarration.contains("studying ") || lowerNarration.contains("pauses ")) {\n                continue\n            }\n            if line.isEmpty {\n'''
    app = app.replace(needle, replacement, 1)

# The v0.12.5 field build still surfaced a dangling clause. Add a final helper
# that ALWAYS returns a completed sentence whenever at least one sentence exists.
# This is deliberately applied immediately before every assistant persistence.
if "private func enforceCompletedVisibleReply" not in app:
    helper_anchor = "    private func finishReplyAtNaturalBoundary(_ raw: String) -> String {\n"
    if helper_anchor not in app:
        raise SystemExit("v0.12.6 completion helper anchor missing")
    helper = '''    private func enforceCompletedVisibleReply(_ raw: String) -> String {\n        let text = raw.trimmingCharacters(in: .whitespacesAndNewlines)\n        guard !text.isEmpty else { return text }\n        if let last = text.last, ".!?…".contains(last) { return text }\n\n        var lastBoundary: String.Index?\n        for idx in text.indices {\n            if ".!?…".contains(text[idx]) { lastBoundary = text.index(after: idx) }\n        }\n        if let boundary = lastBoundary {\n            let completed = String(text[..<boundary]).trimmingCharacters(in: .whitespacesAndNewlines)\n            if !completed.isEmpty { return completed }\n        }\n        return text + "."\n    }\n\n'''
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
for required in [
    "enforceCompletedVisibleReply",
    "V126_STAGE_DIRECTION_LINE_FILTER",
]:
    if required not in check_app:
        raise SystemExit(f"v0.12.6 app invariant missing: {required}")
for required in [MARKER, "conciseGroundedDialogueRules", "usually 2 to 4 complete sentences"]:
    if required not in check_prompt:
        raise SystemExit(f"v0.12.6 prompt invariant missing: {required}")
if "webGroundedTurn ? 256 : 224" not in check_app and "maxNewTokens = 224" not in check_app:
    raise SystemExit("v0.12.6 final token budget missing")

print("Applied v0.12.6 concise grounded dialogue + hard visible completion")
