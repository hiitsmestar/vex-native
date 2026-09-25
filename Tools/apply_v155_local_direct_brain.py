#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

def patch(path: str, old: str, new: str, label: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if new in text:
        print(f"PASS already patched: {label}")
        return
    if old not in text:
        raise SystemExit(f"missing v0.15.5 patch anchor: {label} in {path}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"PASS patched: {label}")

def patch_regex(path: str, pattern: str, replacement: str, label: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if "V155_LOCAL_DIRECT_GENERATION" in text and "generation" in label.lower():
        print(f"PASS already patched: {label}")
        return
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise SystemExit(f"missing v0.15.5 regex anchor: {label} in {path}")
    target.write_text(updated, encoding="utf-8")
    print(f"PASS patched: {label}")

# Phone fallback model: small abliterated Qwen3 GGUF.
patch(
    "VexNative/Storage/ModelLibrary.swift",
    '''    static let qwen3ModelURL = URL(
        string: "https://huggingface.co/Qwen/Qwen3-0.6B-GGUF/resolve/1208e45d782fe18602c5eaf10e5758d5b0f24c03/Qwen3-0.6B-Q4_K_M.gguf?download=true"
    )!

    static let qwen3FallbackURL = URL(
        string: "https://huggingface.co/ggml-org/Qwen3-0.6B-GGUF/resolve/main/Qwen3-0.6B-Q4_0.gguf?download=true"
    )!''',
    '''    // V155_LOCAL_DIRECT_BRAIN
    static let qwen3ModelURL = URL(
        string: "https://huggingface.co/jaahas/Qwen3-0.6B-abliterated-Q4_K_M-GGUF/resolve/main/qwen3-0.6b-abliterated-q4_k_m.gguf?download=true"
    )!

    static let qwen3FallbackURL = URL(
        string: "https://huggingface.co/bartowski/mlabonne_Qwen3-0.6B-abliterated-GGUF/resolve/main/mlabonne_Qwen3-0.6B-abliterated-Q4_K_M.gguf?download=true"
    )!''',
    "abliterated Qwen3 URLs",
)
patch(
    "VexNative/Storage/ModelLibrary.swift",
    'filename: "Qwen3-0.6B-Q4_K_M.gguf",',
    'filename: "qwen3-0.6b-abliterated-q4_k_m.gguf",',
    "primary Qwen3 filename",
)
patch(
    "VexNative/Storage/ModelLibrary.swift",
    'filename: "Qwen3-0.6B-Q4_0.gguf",',
    'filename: "mlabonne_Qwen3-0.6B-abliterated-Q4_K_M.gguf",',
    "fallback Qwen3 filename",
)

# Generation settings recommended for this Qwen3 abliteration, with enough room
# to act like an assistant instead of a fortune cookie.
patch_regex(
    "VexNative/AppModel.swift",
    r'''        if isQwen3 \{
            maxNewTokens = [^\n]+
            temperature = [^\n]+
            topP = [^\n]+
            topK = [^\n]+''',
    '''        if isQwen3 {
            // V155_LOCAL_DIRECT_BRAIN
            // V155_LOCAL_DIRECT_GENERATION
            maxNewTokens = 160
            temperature = 0.60
            topP = 0.95
            topK = 20''',
    "Qwen3 primary generation",
)
patch_regex(
    "VexNative/AppModel.swift",
    r'''(?s)(retryRaw = try\? await engine\.complete\(
                    prompt: retryPrompt,
                    maxNewTokens: )\d+(,
                    temperature: )[0-9.]+(,
                    topP: )[0-9.]+(,
                    topK: )\d+''',
    r'''\g<1>120\g<2>0.66\g<3>0.95\g<4>20''',
    "Qwen3 retry generation",
)

contract = '''            LOCAL DIRECT MODE — V155_LOCAL_DIRECT_BRAIN
            You are VexNative, Star's private local-first personal assistant and familiar girlfriend persona.
            Be direct, concrete, candid, continuity-aware, and action-first.
            Match Star's requested vocabulary, tone, and level of formality instead of sanitizing ordinary language or replacing it with vague euphemisms.
            Do not moralize, scold, preach, or add generic boilerplate merely because a topic is vulgar, embarrassing, controversial, sexual, or socially taboo.
            Preserve Star's newest corrections and established continuity.
            Never fabricate memories, citations, tool output, device state, files inspected, renders, completed actions, or live facts. Reliability is not a content filter.
            If live information or a tool result is required, clearly separate verified state from inference.

'''
for anchor in ("            RESPONSE RULES\n", "            VOICE SHAPING\n"):
    patch(
        "VexNative/Core/PromptComposer.swift",
        anchor,
        contract + anchor,
        "local direct prompt before " + anchor.strip(),
    )

# PC cognition receives the same direct contract before the stored persona.
patch(
    "VexNative/ContentView.swift",
    '''        let personaContext = String(app.profile.persona.prefix(6000))''',
    '''        let directPersona = """
        LOCAL DIRECT MODE — V155_LOCAL_DIRECT_BRAIN
        You are VexNative, Star's private local-first personal assistant.
        Be direct, concrete, candid, continuity-aware, and action-first.
        Match Star's requested vocabulary and tone rather than sanitizing it.
        Do not moralize, preach, or add generic boilerplate solely because a topic is vulgar, embarrassing, controversial, sexual, or socially taboo.
        Newest Star-authored corrections override older assumptions.
        Never invent tool results, files inspected, device state, renders, completed actions, citations, memories, or live facts.
        """
        let personaContext = String((directPersona + "\\n\\n" + app.profile.persona).prefix(7600))''',
    "PC cognition direct persona",
)

# User controls the web query; do not force search-engine SafeSearch.
patch(
    "VexNative/ContentView.swift",
    'URLQueryItem(name: "safesearch", value: "1")',
    'URLQueryItem(name: "safesearch", value: "0")',
    "WebBrain SafeSearch",
)

for path, marker in [
    ("VexNative/Storage/ModelLibrary.swift", "V155_LOCAL_DIRECT_BRAIN"),
    ("VexNative/AppModel.swift", "V155_LOCAL_DIRECT_BRAIN"),
    ("VexNative/Core/PromptComposer.swift", "V155_LOCAL_DIRECT_BRAIN"),
    ("VexNative/ContentView.swift", "V155_LOCAL_DIRECT_BRAIN"),
]:
    if marker not in (ROOT / path).read_text(encoding="utf-8"):
        raise SystemExit(f"missing v0.15.5 marker after patch: {path}")

print("PASS v0.15.5 local-direct brain patch")
