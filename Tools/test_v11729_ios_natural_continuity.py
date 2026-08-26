#!/usr/bin/env python3
from pathlib import Path

app = Path("VexNative/AppModel.swift").read_text(encoding="utf-8")
prompt = Path("VexNative/Core/PromptComposer.swift").read_text(encoding="utf-8")
memory = Path("VexNative/Core/MemoryEngine.swift").read_text(encoding="utf-8")

required_app = [
    "let groundedDirective = isQwen3 ? nativeGroundedQwen3Directive(for: text) : nil",
    "private func nativeGroundedQwen3Directive(for userText: String) -> String?",
    "groundedDirective: groundedDirective",
]
for marker in required_app:
    assert marker in app, f"AppModel missing {marker}"

assert ("maxNewTokens = 72" in app or "webGroundedTurn ? 240 : 72" in app), "ordinary Qwen3 token budget was not widened"
assert ("temperature = 0.90" in app or "webGroundedTurn ? 0.45 : 0.90" in app), "ordinary Qwen3 temperature was not widened"
assert "if isQwen3, let grounded = nativeGroundedQwen3Reply(for: text)" not in app, "canned native fast path still active"
assert "private func nativeGroundedQwen3Reply(for userText: String)" not in app, "old canned reply function still active"

required_prompt = [
    "groundedDirective: String? = nil",
    "let retrievalLimit = focusedTurn ? 6 : (isQwen3 ? 2 : 6)",
    "memory.kind == .rule || memory.kind == .lesson",
    "Star's actual newest message:",
    "Grounding constraints for this turn:",
    "AUTHORITATIVE TURN FACTS",
    "newest explicit correction from Star overrides stale memory",
    "compact = String(groundedModelUserText.prefix(cap))",
]
for marker in required_prompt:
    assert marker in prompt, f"PromptComposer missing {marker}"

assert "if focusedTurn {\n            relevant = []" not in prompt, "focused turns still discard memory"
assert "learnCandidate(from userText: String)" in memory, "memory learner missing"
assert "local model's own output" in memory, "generated-output memory guard missing"
assert "MemoryEngine.learnCandidate(from: text)" in app, "learning is not sourced from Star's input"
assert "learnCandidate(from: finalAnswer)" not in app, "generated reply is incorrectly being learned as fact"

actual_pos = prompt.index("Star's actual newest message:")
constraint_pos = prompt.index("Grounding constraints for this turn:")
assert actual_pos < constraint_pos, "actual user wording is not prioritized before constraints"

print("v11729 natural continuity regressions passed")
