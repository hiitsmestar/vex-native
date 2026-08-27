#!/usr/bin/env python3
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "VexNative" / "AppModel.swift"
PROMPT = ROOT / "VexNative" / "Core" / "PromptComposer.swift"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def replace_or_keep(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    return replace_once(text, old, new, label)


app = APP.read_text(encoding="utf-8")

# The roundtrip chain may already have changed the literal Qwen values. Match the
# semantic slot instead of requiring the old v0.11.7.30 source text verbatim.
app, count = re.subn(
    r'(if filename\.contains\("qwen3"\) \{\n\s*contextSize = )\d+',
    r'\g<1>3072',
    app,
    count=1,
)
if count != 1:
    raise SystemExit(f"Qwen3 context window: expected one semantic match, found {count}")

app = replace_or_keep(
    app,
    'if isQwen3, let grounded = nativeGroundedQwen3Reply(for: text) {',
    'if isQwen3, shouldUseNativeGrounding(for: text), let grounded = nativeGroundedQwen3Reply(for: text) {',
    "native grounding gate",
)

matches = list(re.finditer(
    r'(?ms)^        if isQwen3 \{\n(.*?)^        \} else if isTinyQwen25 \{',
    app,
))
if len(matches) != 1:
    raise SystemExit(f"Qwen3 generation block: expected one semantic block, found {len(matches)}")
m = matches[0]
block = m.group(1)
for label, pattern, replacement in [
    ("maxNewTokens", r'(^\s*maxNewTokens = )\d+', r'\g<1>96'),
    ("temperature", r'(^\s*temperature = )[0-9.]+', r'\g<1>0.88'),
    ("topP", r'(^\s*topP = )[0-9.]+', r'\g<1>0.92'),
    ("topK", r'(^\s*topK = )\d+', r'\g<1>48'),
]:
    block, n = re.subn(pattern, replacement, block, count=1, flags=re.MULTILINE)
    if n != 1:
        raise SystemExit(f"Qwen3 generation {label}: expected one assignment, found {n}")
app = app[:m.start(1)] + block + app[m.end(1):]

anchor = '''    private func normalizedIntentText(_ text: String) -> String {\n'''
insert = '''    // v0.11.7.30: native replies are correctness guardrails only. Ordinary\n    // conversation must still reach the local model so Vex can vary naturally\n    // instead of returning the same canned sentence on every cleared-chat test.\n    private func shouldUseNativeGrounding(for userText: String) -> Bool {\n        let lower = normalizedIntentText(userText)\n        return clarifiesRelationshipDowngrade(lower) ||\n            assertsRelationshipTruth(lower) ||\n            asksSeparateHomesTexting(lower) ||\n            asksClarifyOtherSide(lower) ||\n            correctsNakedVsOutfit(lower)\n    }\n\n'''
if insert not in app:
    app = replace_once(app, anchor, insert + anchor, "native grounding helper")

old_remember = '''    func rememberLastExchange() {\n        guard !profile.messages.isEmpty else { return }\n        let chunk = profile.messages.suffix(2).map {\n            "\\($0.role == .user ? \"Star\" : \"Vex\"): \\($0.content)"\n        }.joined(separator: " | ")\n\n        profile.memories = MemoryEngine.deduplicatedAppend(\n            BrainMemory(text: chunk, kind: .note, importance: 0.7),\n            to: profile.memories\n        )\n        persist()\n    }\n'''
new_remember = '''    func rememberLastExchange() {\n        guard let userMessage = profile.messages.reversed().first(where: { $0.role == .user }) else { return }\n\n        // Permanent memory must come from Star-authored material, never from a\n        // generated Vex sentence that could contain a hallucination or stock reply.\n        profile.memories = MemoryEngine.deduplicatedAppend(\n            BrainMemory(\n                text: userMessage.content,\n                kind: .note,\n                importance: 0.70,\n                confidence: 0.82,\n                evidenceCount: 1,\n                lastConfirmedAt: Date(),\n                source: "user-manual"\n            ),\n            to: profile.memories\n        )\n        persist()\n    }\n'''
app = replace_or_keep(app, old_remember, new_remember, "manual memory source boundary")
APP.write_text(app, encoding="utf-8")

prompt = PROMPT.read_text(encoding="utf-8")

old_relevant = '''        let relevant: [BrainMemory]\n        if focusedTurn {\n            relevant = []\n        } else {\n            let memoryLimit = isQwen3 ? 1 : 6\n            relevant = MemoryEngine.retrieve(\n                query: newestUserText,\n                from: profile.memories,\n                limit: memoryLimit\n            )\n        }\n'''
new_relevant = '''        let relevant: [BrainMemory]\n        let memoryLimit = isQwen3 ? (focusedTurn ? 2 : 3) : 6\n        relevant = MemoryEngine.retrieve(\n            query: newestUserText,\n            from: profile.memories,\n            limit: memoryLimit\n        )\n'''
prompt = replace_or_keep(prompt, old_relevant, new_relevant, "focused memory retrieval")

old_profile = '''        let personaLimit = focusedTurn ? 420 : 760\n        let userLimit = focusedTurn ? 0 : 280\n        let personaBlock = isQwen3 ? String(profile.persona.prefix(personaLimit)) : profile.persona\n        let userBlock: String\n        if isQwen3 && focusedTurn {\n            userBlock = "(not needed for this short turn)"\n        } else {\n            userBlock = isQwen3 ? String(profile.userProfile.prefix(userLimit)) : profile.userProfile\n        }\n'''
new_profile = '''        let personaLimit = focusedTurn ? 640 : 760\n        let userLimit = focusedTurn ? 220 : 280\n        let personaBlock = isQwen3 ? String(profile.persona.prefix(personaLimit)) : profile.persona\n        let userBlock = isQwen3 ? String(profile.userProfile.prefix(userLimit)) : profile.userProfile\n'''
prompt = replace_or_keep(prompt, old_profile, new_profile, "focused profile continuity")

prompt = replace_or_keep(
    prompt,
    'Treat CURRENT VEX STATE, the newest user correction, and the rewritten newest request as closed-world truth for this turn.',
    'Treat CURRENT VEX STATE, the newest user correction, and the grounding constraints as closed-world truth for factual details. The newest Star message itself remains the conversation you must answer.',
    "closed-world wording",
)

old_recent = '''        let recent: [ChatMessage]\n        if focusedTurn {\n            recent = Array(profile.messages.suffix(1))\n        } else {\n            let recentLimit = isQwen3 ? 5 : maxRecentMessages\n            recent = Array(profile.messages.suffix(recentLimit))\n        }\n'''
new_recent = '''        let recent: [ChatMessage]\n        if focusedTurn {\n            // Keep enough immediate history for references, rhythm, and anti-parrot\n            // checks. A one-message window made cleared chats sound like templates.\n            recent = Array(profile.messages.suffix(4))\n        } else {\n            let recentLimit = isQwen3 ? 5 : maxRecentMessages\n            recent = Array(profile.messages.suffix(recentLimit))\n        }\n'''
prompt = replace_or_keep(prompt, old_recent, new_recent, "focused recent context")

prompt = replace_or_keep(
    prompt,
    'let cap = isQwen3 ? (focusedTurn ? 760 : 150) : 600',
    'let cap = isQwen3 ? (focusedTurn ? 1200 : 220) : 600',
    "Qwen3 recent-message cap",
)

old_latest = '''            if isQwen3 && index == recent.count - 1 && message.role == .user {\n                compact = String(modelUserText.prefix(cap))\n                if retryMode {\n                    compact += "\\nYour first draft was rejected. Give a genuinely different direct answer in 1 to 2 sentences."\n                }\n                compact += "\\n/no_think"\n            } else {\n'''
new_latest = '''            if isQwen3 && index == recent.count - 1 && message.role == .user {\n                let groundingPrefix: String\n                if modelUserText == newestUserText {\n                    groundingPrefix = ""\n                } else {\n                    groundingPrefix = "GROUNDING CONSTRAINTS (facts only; do not answer these as if Star said them):\\n\\(modelUserText)\\n\\n"\n                }\n                let naturalTurn = groundingPrefix + "STAR'S NEWEST MESSAGE (verbatim):\\n" + newestUserText\n                compact = String(naturalTurn.prefix(cap))\n                if retryMode {\n                    compact += "\\nYour first draft was rejected. Give a genuinely different direct answer in 1 to 2 sentences."\n                }\n                compact += "\\n/no_think"\n            } else {\n'''
prompt = replace_or_keep(prompt, old_latest, new_latest, "verbatim newest-message preservation")

PROMPT.write_text(prompt, encoding="utf-8")

for path, markers in [
    (APP, [
        'contextSize = 3072',
        'shouldUseNativeGrounding(for: text)',
        'maxNewTokens = 96',
        'temperature = 0.88',
        'topP = 0.92',
        'topK = 48',
        'source: "user-manual"',
    ]),
    (PROMPT, [
        'STAR\'S NEWEST MESSAGE (verbatim)',
        'focusedTurn ? 1200 : 220',
        'focusedTurn ? 2 : 3',
    ]),
]:
    data = path.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in data:
            raise SystemExit(f"{path}: missing continuity marker: {marker}")

print("Applied VexNative v0.11.7.43 roundtrip-compatible natural continuity patch")
