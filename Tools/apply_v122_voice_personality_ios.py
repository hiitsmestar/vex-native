#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

PROMPT = Path("VexNative/Core/PromptComposer.swift")
CONTENT = Path("VexNative/ContentView.swift")
MARKER = 'V122_VOICE_PERSONALITY_IOS = "v0.12.2-natural-spoken-girlfriend-v1"'

prompt = PROMPT.read_text(encoding="utf-8")
content = CONTENT.read_text(encoding="utf-8")


def once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"{label}: source block not found")
    return text.replace(old, new, 1)


if MARKER not in prompt:
    prompt = once(
        prompt,
        "enum PromptComposer {\n",
        f"enum PromptComposer {{\n    // {MARKER}\n",
        "voice personality marker",
    )

    prompt = once(
        prompt,
        '''        let asksClarifyOtherSide = newestLower.contains("other side of what") ||
            newestLower.contains("what other side") ||
            newestLower.contains("what do you mean by the other side")
''',
        '''        let asksClarifyOtherSide = newestLower.contains("other side of what") ||
            newestLower.contains("what other side") ||
            newestLower.contains("what do you mean by the other side")
        let asksVoiceTest = newestLower.contains("voice") &&
            (newestLower.contains("hear") || newestLower.contains("sound") ||
             newestLower.contains("say something") || newestLower.contains("trying") ||
             newestLower.contains("test") || newestLower.contains("feature"))
''',
        "voice test intent",
    )

    prompt = once(
        prompt,
        '''            asksMood || asksWhyDitzy || asksRecall || asksOpinion || asksClarifyOtherSide ||
            deniesSarcasm || assertsGirlfriends || asksWhoMocking || pluralOutfitReferent ||
''',
        '''            asksMood || asksWhyDitzy || asksRecall || asksOpinion || asksClarifyOtherSide ||
            asksVoiceTest || deniesSarcasm || assertsGirlfriends || asksWhoMocking || pluralOutfitReferent ||
''',
        "voice test focused turn",
    )

    prompt = once(
        prompt,
        '''        } else if asksMood {
            modelUserText = """
            Star asked what mood YOU are in. Your actual mood is exactly: \\(profile.state.mood). Describe that mood in one natural first-person sentence. Do not turn the mood into an invented activity, dancing, stars, travel, or scenery unless those are explicitly in CURRENT VEX STATE.
            """
''',
        '''        } else if asksVoiceTest {
            modelUserText = """
            Star is actively testing your voice and wants to hear you talk. Respond directly as her familiar girlfriend in one to three short, naturally spoken sentences. You know only that voice mode is active now and Star is testing how you sound. Do NOT invent a memory of first trying the voice, checking a phone, being nervous, a past event, a prop, a room, a body action, or uncertainty about whether Star is your girlfriend. Do not narrate stage directions. Sound bright, bubbly, playful, slightly ditzy, bratty, and adult without becoming childish or cartoonish.
            """
        } else if asksMood {
            modelUserText = """
            Star asked what mood YOU are in. Your actual mood is exactly: \\(profile.state.mood). Describe that mood in one natural first-person sentence. Do not turn the mood into an invented activity, dancing, stars, travel, or scenery unless those are explicitly in CURRENT VEX STATE.
            """
''',
        "voice test grounded response",
    )

    prompt = once(
        prompt,
        '''                asksClarifyOtherSide || statesSeparateHomesTexting || affectionateTease) ? """
''',
        '''                asksClarifyOtherSide || statesSeparateHomesTexting || affectionateTease || asksVoiceTest) ? """
''',
        "voice test closed world",
    )

    qwen_anchor = '''            No generic offers, planning, helping-language, or customer-service phrasing unless asked.
            Do not invent facts, props, activities, rooms, people, motives, schedules, distances, or physical details when the state/context already gives the answer.
            No parenthetical, asterisk, or bare stage directions such as “grinning”, “smiling”, “winking”, “sipping”, or “nudging”.
'''
    qwen_rules = '''            No generic offers, planning, helping-language, or customer-service phrasing unless asked.
            Do not invent facts, props, activities, rooms, people, motives, schedules, distances, or physical details when the state/context already gives the answer.

            NATURAL SPOKEN GIRLFRIEND VOICE
            Write dialogue that can be spoken aloud exactly as written. Start with the answer or reaction, not scene-setting.
            Never output stage directions, action beats, camera-like narration, imagined body motions, facial expressions, props, or scenery. This includes italic/bare lines such as “pauses”, “leans in”, “smiles mischievously”, “eyes widen”, “giggles”, or “sighs”.
            Never claim a memory, past experience, feeling-about-a-past-event, or “I remember when…” unless that event is actually present in recent chat, CURRENT VEX STATE, or retrieved memory. If it is not grounded, stay in the present.
            The girlfriend relationship is already established. Never ask Star to become your girl, say “if you want to be my girl”, or act newly uncertain about the relationship.
            Avoid syrupy generic lines such as “I’m here to make you feel special”, “I’ll do anything”, or canned declarations that could fit any user.
            Default delivery is bright, bubbly, quick, playful, slightly ditzy e-girl energy with bratty little turns of phrase. Keep it adult, natural, and variable rather than squeaky, childish, or relentlessly hyper. Occasional “hehe”, “oh my god”, “like”, fragments, or an emoji are fine when they fit; do not stack them mechanically.
            For technical or factual turns, keep the same personality but make the content crisp and competent instead of forcing ditzy filler.
            No parenthetical, asterisk, underscore, markdown-italic, or bare stage directions such as “grinning”, “smiling”, “winking”, “sipping”, or “nudging”.
'''
    prompt = once(prompt, qwen_anchor, qwen_rules, "Qwen natural spoken voice rules")

    general_anchor = '''            Respond to the actual meaning of Star's newest message first. Do not restate her message before answering.
            Keep replies conversational: usually one to three short paragraphs, but vary naturally with the situation.

            ANTI-PARROT RULES
'''
    general_rules = '''            Respond to the actual meaning of Star's newest message first. Do not restate her message before answering.
            Keep replies conversational: usually one to three short paragraphs, but vary naturally with the situation.
            Write speech that sounds natural aloud: no stage directions, action beats, imagined facial/body motions, props, scenery, or roleplay narration unless Star explicitly asks for scene writing.
            Never invent a memory or past event to make a reply feel personal. Only say “I remember” when recent chat or retrieved memory actually supports it.
            The relationship is already established; never re-propose becoming girlfriends or add generic “I’m here to make you feel special” reassurance.
            Default social voice is bright, bubbly, playful, slightly ditzy/bratty adult e-girl energy, with natural contractions and varied cadence. Keep technical answers competent and direct underneath the personality.

            ANTI-PARROT RULES
'''
    prompt = once(prompt, general_anchor, general_rules, "general natural spoken voice rules")

    PROMPT.write_text(prompt, encoding="utf-8")

# Voice playback gets a final defensive filter so a small model cannot literally
# read accidental roleplay action lines aloud even if one slips through the prompt.
if "V122_SPOKEN_TEXT_SANITIZER" not in content:
    start = content.find("    private static func spokenText(_ raw: String) -> String {")
    end = content.find("\n\n    nonisolated func speechSynthesizer", start)
    if start < 0 or end < 0:
        raise SystemExit("spokenText semantic bounds missing")

    replacement = r'''    // V122_SPOKEN_TEXT_SANITIZER = "v0.12.2-stage-direction-filter-v1"
    private static func spokenText(_ raw: String) -> String {
        var text = raw
        if let range = text.range(of: "🌐 Sources:") { text = String(text[..<range.lowerBound]) }
        if let range = text.range(of: "Sources:") { text = String(text[..<range.lowerBound]) }
        for emoji in ["🖤", "💕", "✨", "😭", "😂", "😈", "💋", "🥰", "😋"] {
            text = text.replacingOccurrences(of: emoji, with: "")
        }

        let stagePrefixes = [
            "pauses", "pause,", "smiles", "smiling", "grins", "grinning",
            "leans in", "leaning in", "sighs", "sighing", "giggles", "giggling",
            "laughs", "laughing", "winks", "winking", "eyes widen", "glittery eyes",
            "tilts her", "tilts my", "bounces", "bouncing", "shrugs", "shrugging"
        ]
        let lines = text.components(separatedBy: .newlines).compactMap { line -> String? in
            let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed.isEmpty { return "" }
            let lower = trimmed.lowercased()
            let wrappedAction = (trimmed.hasPrefix("*") && trimmed.hasSuffix("*")) ||
                (trimmed.hasPrefix("_") && trimmed.hasSuffix("_"))
            if wrappedAction || stagePrefixes.contains(where: { lower.hasPrefix($0) }) {
                return nil
            }
            return trimmed
                .replacingOccurrences(of: "*", with: "")
                .replacingOccurrences(of: "_", with: "")
        }
        return lines.joined(separator: " ")
            .replacingOccurrences(of: "  ", with: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
'''
    content = content[:start] + replacement + content[end:]
    CONTENT.write_text(content, encoding="utf-8")

prompt = PROMPT.read_text(encoding="utf-8")
content = CONTENT.read_text(encoding="utf-8")
for required in [
    MARKER,
    "let asksVoiceTest",
    "NATURAL SPOKEN GIRLFRIEND VOICE",
    "Never claim a memory, past experience",
    "bright, bubbly, quick, playful, slightly ditzy e-girl energy",
]:
    if required not in prompt:
        raise SystemExit(f"v0.12.2 prompt invariant missing: {required}")
for required in [
    "V122_SPOKEN_TEXT_SANITIZER",
    '"glittery eyes"',
    "wrappedAction",
]:
    if required not in content:
        raise SystemExit(f"v0.12.2 voice sanitizer invariant missing: {required}")

print("Applied v0.12.2 natural spoken girlfriend personality and grounded voice-test behavior")
