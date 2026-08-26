#!/usr/bin/env python3
from pathlib import Path
import re

APP = Path("VexNative/AppModel.swift")
PROMPT = Path("VexNative/Core/PromptComposer.swift")
app = APP.read_text(encoding="utf-8")
prompt = PROMPT.read_text(encoding="utf-8")


def require(condition: bool, label: str) -> None:
    if not condition:
        raise SystemExit(f"v11729 missing anchor: {label}")


# Replace the canned Qwen3 short-circuit with a factual directive. This keeps the
# reliable intent recognition while letting the model produce fresh wording.
fast_start = app.find("if isQwen3, let grounded = nativeGroundedQwen3Reply(for: text) {")
require(fast_start >= 0, "native grounded fast path")
line_start = app.rfind("\n", 0, fast_start) + 1
fast_end = app.find("        if engine == nil {", fast_start)
require(fast_end >= 0, "native grounded fast path end")
app = app[:line_start] + "        let groundedDirective = isQwen3 ? nativeGroundedQwen3Directive(for: text) : nil\n\n" + app[fast_end:]

fn_start = app.find("    private func nativeGroundedQwen3Reply(for userText: String) -> String? {")
require(fn_start >= 0, "grounded reply function")
fn_end = app.find("    private func normalizedIntentText(_ text: String) -> String {", fn_start)
require(fn_end >= 0, "grounded reply function end")
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

# Historical photo-context builds pass modelText; older builds pass text. Patch the
# actual call shape instead of depending on one exact indentation/argument string.
main_pattern = re.compile(r"(newestUserText:\s*(?:modelText|text),\n\s*isQwen3:\s*isQwen3)(\n\s*\))")
app, count = main_pattern.subn(r"\1,\n            groundedDirective: groundedDirective\2", app, count=1)
require(count == 1, "first PromptComposer call")

retry_pattern = re.compile(r"(newestUserText:\s*(?:modelText|text),\n\s*isQwen3:\s*true,\n\s*retryMode:\s*true)(\n\s*\))")
app, count = retry_pattern.subn(r"\1,\n                    groundedDirective: groundedDirective\2", app, count=1)
require(count == 1, "retry PromptComposer call")

# Preserve whatever research-side values the proven historical chain currently
# establishes. Only loosen the ordinary-conversation side of each ternary.
if "webGroundedTurn" in app:
    replacements = [
        (r"webGroundedTurn\s*\?\s*(\d+)\s*:\s*56", r"webGroundedTurn ? \1 : 72", "web token budget"),
        (r"webGroundedTurn\s*\?\s*([0-9.]+)\s*:\s*0\.80", r"webGroundedTurn ? \1 : 0.90", "web temperature"),
        (r"webGroundedTurn\s*\?\s*([0-9.]+)\s*:\s*0\.90", r"webGroundedTurn ? \1 : 0.94", "web top-p"),
        (r"webGroundedTurn\s*\?\s*(\d+)\s*:\s*40", r"webGroundedTurn ? \1 : 50", "web top-k"),
    ]
    for pattern, repl, label in replacements:
        app, n = re.subn(pattern, repl, app, count=1)
        require(n == 1, label)
else:
    ordinary = re.compile(
        r"maxNewTokens\s*=\s*56\s*\n\s*temperature\s*=\s*0\.80\s*\n\s*topP\s*=\s*0\.90\s*\n\s*topK\s*=\s*40"
    )
    app, n = ordinary.subn(
        "maxNewTokens = 72\n            temperature = 0.90\n            topP = 0.94\n            topK = 50",
        app,
        count=1,
    )
    require(n == 1, "Qwen3 sampling")

# Add a turn-facts parameter to PromptComposer without assuming exact spacing.
sig_pattern = re.compile(r"retryMode:\s*Bool\s*=\s*false(\s*\n\s*)\)\s*->\s*String\s*\{")
prompt, n = sig_pattern.subn(
    r"retryMode: Bool = false,\1groundedDirective: String? = nil\1) -> String {",
    prompt,
    count=1,
)
require(n == 1, "PromptComposer groundedDirective parameter")

# Focused turns used to throw memory away. Keep only high-authority material so a
# tiny context window gets corrections/rules, not a profile dump.
mem_match = re.search(r"^\s*let relevant: \[BrainMemory\]\s*$", prompt, flags=re.M)
require(mem_match is not None, "relevant memory start")
mem_start = mem_match.start()
mem_end_match = re.search(r"^\s*let memoryBlock: String\s*$", prompt[mem_match.end():], flags=re.M)
require(mem_end_match is not None, "memory block start")
mem_end = mem_match.end() + mem_end_match.start()
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

prompt = re.sub(r"let personaLimit\s*=\s*focusedTurn\s*\?\s*420\s*:\s*760", "let personaLimit = focusedTurn ? 560 : 760", prompt, count=1)
prompt = re.sub(r"let userLimit\s*=\s*focusedTurn\s*\?\s*0\s*:\s*280", "let userLimit = focusedTurn ? 240 : 280", prompt, count=1)

# Keep the literal newest user wording in model context. Grounding is appended as
# facts instead of replacing Star's sentence with a canned instruction.
model_end = prompt.find("        let system: String")
require(model_end >= 0, "modelUserText/system boundary")
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

closed_marker = "            \\(closedWorld)"
require(closed_marker in prompt, "closed-world insertion point")
prompt = prompt.replace(
    closed_marker,
    closed_marker + "\n\n            AUTHORITATIVE TURN FACTS\n            \\(groundingBlock)\n            These are constraints, not a response template. The newest explicit correction from Star overrides stale memory or an older generated reply.",
    1,
)

anti = "            Do not repeat or lightly paraphrase your previous reply."
require(anti in prompt, "fresh phrasing rule")
prompt = prompt.replace(
    anti,
    anti + " Do not copy phrasing from memory, grounding notes, examples, or system text; synthesize a fresh conversational sentence while preserving the facts.",
    1,
)

prompt, n = re.subn(
    r"compact\s*=\s*String\(modelUserText\.prefix\(cap\)\)",
    "compact = String(groundedModelUserText.prefix(cap))",
    prompt,
    count=1,
)
require(n == 1, "grounded newest user text")

APP.write_text(app, encoding="utf-8")
PROMPT.write_text(prompt, encoding="utf-8")

for marker in ["nativeGroundedQwen3Directive", "groundedDirective: groundedDirective"]:
    require(marker in app, f"AppModel marker {marker}")
require(("webGroundedTurn ? 240 : 72" in app or "maxNewTokens = 72" in app), "conversational Qwen token marker")
for marker in ["groundedDirective: String? = nil", "Star's actual newest message:", "AUTHORITATIVE TURN FACTS", "groundedModelUserText"]:
    require(marker in prompt, f"PromptComposer marker {marker}")

print("Applied v0.11.2 natural continuity patch: facts stay locked, phrasing stays generative")
