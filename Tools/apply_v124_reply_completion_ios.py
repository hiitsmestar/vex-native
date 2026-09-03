#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

APP = Path("VexNative/AppModel.swift")
MARKER = 'V124_REPLY_COMPLETION_IOS = "v0.12.4-complete-spoken-replies-v1"'

app = APP.read_text(encoding="utf-8")

# The Qwen3 phone model was capped at only 72 new tokens for ordinary chat. In
# field voice tests that was visibly cutting replies in the middle of a sentence.
# Give normal conversational turns enough room to finish while preserving the
# larger web/research budget and the tiny-model performance envelope.
replacements = [
    ("webGroundedTurn ? 240 : 72", "webGroundedTurn ? 240 : 128"),
    ("maxNewTokens = 72", "maxNewTokens = 128"),
]
changed_budget = False
for old, new in replacements:
    if old in app:
        app = app.replace(old, new, 1)
        changed_budget = True
        break
if not changed_budget and ("webGroundedTurn ? 240 : 128" not in app and "maxNewTokens = 128" not in app):
    raise SystemExit("v0.12.4 Qwen3 token-budget anchor missing")

# A second defensive layer prevents a token-limited draft from ending visibly or
# audibly on a dangling partial sentence. If the model produced one or more full
# sentences and then started another sentence it could not finish, keep the full
# sentences and drop only the dangling tail.
if "private func finishReplyAtNaturalBoundary" not in app:
    helper_anchor = "    private func cleanGeneratedReply(_ raw: String) -> String {\n"
    if helper_anchor not in app:
        raise SystemExit("v0.12.4 cleanup helper anchor missing")
    helper = r'''    // V124_REPLY_COMPLETION_IOS = "v0.12.4-complete-spoken-replies-v1"
    private func finishReplyAtNaturalBoundary(_ raw: String) -> String {
        let text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return text }

        let terminal = CharacterSet(charactersIn: ".!?…")
        if let lastScalar = text.unicodeScalars.last, terminal.contains(lastScalar) {
            return text
        }

        var lastBoundary: String.Index?
        var cursor = text.startIndex
        while cursor < text.endIndex {
            let ch = text[cursor]
            if ch == "." || ch == "!" || ch == "?" || ch == "…" {
                lastBoundary = text.index(after: cursor)
            }
            cursor = text.index(after: cursor)
        }

        guard let boundary = lastBoundary else { return text }
        let completed = String(text[..<boundary]).trimmingCharacters(in: .whitespacesAndNewlines)
        let dangling = String(text[boundary...]).trimmingCharacters(in: .whitespacesAndNewlines)

        // Only remove a meaningful dangling tail. Very short suffixes are often
        // punctuation-adjacent formatting rather than a genuinely cut sentence.
        guard dangling.count >= 8, completed.count >= 12 else { return text }
        return completed
    }

'''
    app = app.replace(helper_anchor, helper + helper_anchor, 1)

append_anchor = "            profile.messages.append(ChatMessage(role: .assistant, content: finalAnswer))\n"
if "finalAnswer = finishReplyAtNaturalBoundary(finalAnswer)" not in app:
    if append_anchor not in app:
        raise SystemExit("v0.12.4 final answer append anchor missing")
    app = app.replace(
        append_anchor,
        "            finalAnswer = finishReplyAtNaturalBoundary(finalAnswer)\n" + append_anchor,
        1,
    )

APP.write_text(app, encoding="utf-8")

app = APP.read_text(encoding="utf-8")
for required in [
    MARKER,
    "finishReplyAtNaturalBoundary",
    "finalAnswer = finishReplyAtNaturalBoundary(finalAnswer)",
]:
    if required not in app:
        raise SystemExit(f"v0.12.4 invariant missing: {required}")
if "webGroundedTurn ? 240 : 128" not in app and "maxNewTokens = 128" not in app:
    raise SystemExit("v0.12.4 final conversational token budget missing")

print("Applied v0.12.4 larger conversational budget + natural reply completion guard")
