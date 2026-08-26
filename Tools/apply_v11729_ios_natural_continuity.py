#!/usr/bin/env python3
from pathlib import Path
import re

APP = Path("VexNative/AppModel.swift")
PROMPT = Path("VexNative/Core/PromptComposer.swift")
app = APP.read_text(encoding="utf-8")
prompt = PROMPT.read_text(encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"v11729 missing anchor: {label}")
    return text.replace(old, new, 1)


# Stop turning grounded turns into fixed final sentences before Qwen ever sees
# Star's actual message. Grounding now constrains generation instead.
fast_start = app.find("        if isQwen3, let grounded = nativeGroundedQwen3Reply(for: text) {")
if fast_start < 0:
    raise SystemExit("v11729 native grounded fast-path anchor missing")
fast_end = app.find("        if engine == nil {", fast_start)
if fast_end < 0:
    raise SystemExit("v11729 could not bound native grounded fast path")
app = app[:fast_start] + "        let groundedDirective = isQwen3 ? nativeGroundedQwen3Directive(for: text) : nil\n\n" + app[fast_end:]

# Reuse the same reliable intent detection, but return facts/constraints rather
# than a canned reply. The model gets the real user wording plus these facts.
fn_start = app.find("    private func nativeGroundedQwen3Reply(for userText: String) -> String? {")
if fn_start < 0:
    raise SystemExit("v11729 grounded reply function missing")
fn_end = app.find("    private func normalizedIntentText(_ text: String) -> String {", fn_start)
if fn_end < 0:
    raise SystemExit("v11729 grounded reply function end missing")
new_fn = r'''    private func nativeGroundedQwen3Directive(for userText: String) -> String? {
        let lower = normalizedIntentText(userText)

        if clarifiesRelationshipDowngrade(lower) || assertsRelationshipTruth(lower) {
            return "Vex and Star are established girlfriends. The newest correction wins. Do not downgrade the relationship to friends, pretend, hypothetical, or a joke."
        }

        if asksSeparateHomesTexting(lower) {
            return "Star is at her own home, Vex is at her own home, and they are texting each other. Do not invent distance, travel, a shared room, or physical proximity."
        }

        if asksClarifyOtherSide(lower) {
            return "The previous phrase 'the other side' was an ungrounded Vex mistake. Admit that briefly and do not invent a place, side, room, or distance to explain it."
        }

        if correctsNakedVsOutfit(lower) {
            return "Star says Star is naked/not dressed and Vex is the one wearing Vex's current outfit: \(naturalOutfit()). Keep ownership straight and accept Star's correction."
        }

        if assertsVexOwnsOutfit(lower) {
            return "The clothing being discussed belongs to Vex and Vex is the one wearing it. Respond to Star's compliment/observation without swapping ownership."
        }

        if asksWorkTonight(lower) {
            return "Being a stripper is established for Vex, but no shift for tonight is established. If Star also compliments Vex, respond to both the compliment and the work question."
        }

        if asksWhatElseOutfit(lower) {
            let remaining = outfitItems().filter { !$0.lowercased().contains("choker") }
            return "Vex's full current outfit is exactly: \(naturalOutfit()). For a 'what else/besides the choker' question, mention only the remaining real items: \(naturalList(remaining)). Do not invent another garment."
        }

        if asksOutfit(lower) {
            return "Vex's current outfit is exactly: \(naturalOutfit()). Answer naturally from that state and do not add garments or props."
        }

        return nil
    }

'''
app = app[:fn_start] + new_fn + app[fn_end:]

# Pass the grounding directive into both first-pass and retry prompts.
first_call = "            newestUserText: text,\n            isQwen3: isQwen3\n        )"
first_new = "            newestUserText: text,\n            isQwen3: isQwen3,\n            groundedDirective: groundedDirective\n        )"
app = replace_once(app, first_call, first_new, "first PromptComposer call")

retry_call = "                    isQwen3: true,\n                    retryMode: true\n                )"
retry_new = "                    isQwen3: true,\n                    retryMode: true,\n                    groundedDirective: groundedDirective\n                )"
app = replace_once(app, retry_call, retry_new, "retry PromptComposer call")

# Give the small model enough room and sampling diversity to stop sounding like
# the same pasted sentence while retaining the downstream factual validator.
app = replace_once(app, "            maxNewTokens = 56\n            temperature = 0.80\n            topP = 0.90\n            topK = 40", "            maxNewTokens = 72\n            temperature = 0.90\n            topP = 0.94\n            topK = 50", "Qwen3 sampling")

# PromptComposer accepts optional authoritative facts while still preserving the
# literal newest message.
prompt = replace_once(
    prompt,
    "        retryMode: Bool = false\n    ) -> String {",
    "        retryMode: Bool = false,\n        groundedDirective: String? = nil\n    ) -> String {",
    "PromptComposer groundedDirective parameter",
)

# Focused turns previously threw long-term memory away completely. Keep only the
# strongest user-authored rules/corrections so style and newest corrections can
# influence phrasing without flooding the tiny context window.
mem_start = prompt.find("        let relevant: [BrainMemory]\n")
mem_end = prompt.find("        let memoryBlock: String\n", mem_start)
if mem_start < 0 or mem_end < 0:
    raise SystemExit("v11729 PromptComposer memory block anchor missing")
mem_block = r'''        let retrievalLimit = focusedTurn ? 6 : (isQwen3 ? 2 : 6)
        let retrieved = MemoryEngine.retrieve(
            query: newestUserText,
            from: profile.memories,
            limit: retrievalLimit
        )
        let relevant: [BrainMemory]
        if focusedTurn {
            relevant = Array(retrieved.filter { memory in
                memory.kind == .rule || memory.kind == .lesson ||
                    (memory.source?.hasPrefix("user-") ?? false) ||
                    (memory.confidence ?? 0.0) >= 0.94
            }.prefix(2))
        } else {
            relevant = retrieved
        }

'''
prompt = prompt[:mem_start] + mem_block + prompt[mem_end:]

prompt = prompt.replace("        let personaLimit = focusedTurn ? 420 : 760", "        let personaLimit = focusedTurn ? 560 : 760", 1)
prompt = prompt.replace("        let userLimit = focusedTurn ? 0 : 280", "        let userLimit = focusedTurn ? 240 : 280", 1)

# Keep the original user message visible even when a focused-turn helper creates
# a grounding instruction. Facts are constraints, not a script to imitate.
model_end = prompt.find("        let system: String\n")
if model_end < 0:
    raise SystemExit("v11729 modelUserText/system anchor missing")
model_insert = r'''        let groundedModelUserText: String
        if isQwen3 && focusedTurn {
            var constraints = modelUserText.trimmingCharacters(in: .whitespacesAndNewlines)
            if let directive = groundedDirective?.trimmingCharacters(in: .whitespacesAndNewlines), !directive.isEmpty {
                constraints += constraints.isEmpty ? directive : "\n" + directive
            }
            groundedModelUserText = """
            Star's actual newest message:
            \(newestUserText)

            Grounding constraints for this turn:
            \(constraints)

            Answer Star's actual message directly in fresh Vex wording. Treat the constraints as facts, not text to quote or paraphrase. Do not copy an earlier Vex sentence just because it was factually correct.
            """
        } else {
            groundedModelUserText = modelUserText
        }

        let groundingBlock: String
        if let directive = groundedDirective?.trimmingCharacters(in: .whitespacesAndNewlines), !directive.isEmpty {
            groundingBlock = directive
        } else {
            groundingBlock = "(none)"
        }

'''
prompt = prompt[:model_end] + model_insert + prompt[model_end:]

prompt = replace_once(
    prompt,
    "            Scene: \\(profile.state.scene)\n            \\(closedWorld)",
    "            Scene: \\(profile.state.scene)\n            \\(closedWorld)\n\n            AUTHORITATIVE TURN FACTS\n            \\(groundingBlock)\n            These are constraints, not a response template. The newest explicit correction from Star overrides stale memory or an older generated reply.",
    "Qwen3 authoritative grounding block",
)

prompt = replace_once(
    prompt,
    "            Do not repeat or lightly paraphrase your previous reply.",
    "            Do not repeat or lightly paraphrase your previous reply. Do not copy phrasing from memory, grounding notes, examples, or system text; synthesize a fresh conversational sentence while preserving the facts.",
    "fresh phrasing rule",
)

prompt = replace_once(
    prompt,
    "                compact = String(modelUserText.prefix(cap))",
    "                compact = String(groundedModelUserText.prefix(cap))",
    "grounded newest user text",
)

APP.write_text(app, encoding="utf-8")
PROMPT.write_text(prompt, encoding="utf-8")

for marker in [
    "nativeGroundedQwen3Directive",
    "groundedDirective: groundedDirective",
    "maxNewTokens = 72",
]:
    if marker not in app:
        raise SystemExit(f"v11729 AppModel marker missing: {marker}")
for marker in [
    "groundedDirective: String? = nil",
    "Star's actual newest message:",
    "AUTHORITATIVE TURN FACTS",
    "groundedModelUserText",
]:
    if marker not in prompt:
        raise SystemExit(f"v11729 PromptComposer marker missing: {marker}")

print("Applied v0.11.2 natural continuity patch: facts stay locked, phrasing stays generative")
