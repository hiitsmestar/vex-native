#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

APP = Path("VexNative/AppModel.swift")
MARKER = 'V125_HARD_REPLY_COMPLETION_IOS = "v0.12.5-hard-complete-replies-v1"'

app = APP.read_text(encoding="utf-8")

# Field test on v0.12.4 still hit the 128-token ceiling on a normal spoken turn.
# Give Qwen3 enough room to finish while staying well below the 240-token
# research/web budget.
if "webGroundedTurn ? 240 : 128" in app:
    app = app.replace("webGroundedTurn ? 240 : 128", "webGroundedTurn ? 240 : 192", 1)
elif "maxNewTokens = 128" in app:
    app = app.replace("maxNewTokens = 128", "maxNewTokens = 192", 1)
elif "webGroundedTurn ? 240 : 192" not in app and "maxNewTokens = 192" not in app:
    raise SystemExit("v0.12.5 conversational token-budget anchor missing")

# v0.12.4 placed the boundary guard immediately before one final persistence
# append. That can miss alternate/retry paths in the generated AppModel. Apply
# the guard at the point every raw completion first becomes visible dialogue,
# and also to retry completions, so every model path is normalized before any
# later role repair or candidate selection.
primary_old = "var finalAnswer = cleanGeneratedReply(answer)"
primary_new = "var finalAnswer = finishReplyAtNaturalBoundary(cleanGeneratedReply(answer))"
if primary_old in app:
    app = app.replace(primary_old, primary_new, 1)
elif primary_new not in app:
    raise SystemExit("v0.12.5 primary completion anchor missing")

retry_old = "let retryAnswer = repairQwen3RoleTerms(cleanGeneratedReply(retryRaw))"
retry_new = "let retryAnswer = repairQwen3RoleTerms(finishReplyAtNaturalBoundary(cleanGeneratedReply(retryRaw)))"
if retry_old in app:
    app = app.replace(retry_old, retry_new, 1)

# Keep a final defensive pass at every persistence site that writes finalAnswer.
append_anchor = "profile.messages.append(ChatMessage(role: .assistant, content: finalAnswer))"
if append_anchor in app:
    guarded = "finalAnswer = finishReplyAtNaturalBoundary(finalAnswer)\n            " + append_anchor
    # Replace only unguarded occurrences. Existing v0.12.4 guarded occurrence is
    # harmless; this catches any alternate generated path.
    pieces = app.split(append_anchor)
    rebuilt = pieces[0]
    for idx, tail in enumerate(pieces[1:], start=1):
        before = rebuilt[-120:]
        if "finishReplyAtNaturalBoundary(finalAnswer)" in before:
            rebuilt += append_anchor
        else:
            rebuilt += "finalAnswer = finishReplyAtNaturalBoundary(finalAnswer)\n            " + append_anchor
        rebuilt += tail
    app = rebuilt

# Marker next to the helper makes the built source easy to verify.
if MARKER not in app:
    anchor = 'V124_REPLY_COMPLETION_IOS = "v0.12.4-complete-spoken-replies-v1"'
    if anchor not in app:
        raise SystemExit("v0.12.5 v0.12.4 helper marker missing")
    app = app.replace(anchor, anchor + '\n    // ' + MARKER, 1)

APP.write_text(app, encoding="utf-8")

check = APP.read_text(encoding="utf-8")
for required in [
    MARKER,
    "finishReplyAtNaturalBoundary(cleanGeneratedReply(answer))",
]:
    if required not in check:
        raise SystemExit(f"v0.12.5 invariant missing: {required}")
if "webGroundedTurn ? 240 : 192" not in check and "maxNewTokens = 192" not in check:
    raise SystemExit("v0.12.5 final conversational token budget missing")

print("Applied v0.12.5 hard complete-reply guard + 192-token conversational budget")
