#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


BRIDGE_PATH = Path("Bridge/vex_bridge.py")
source = BRIDGE_PATH.read_text(encoding="utf-8")

if '"version": "0.11.7.4"' not in source:
    raise SystemExit("v0.11.7.6 expected the v0.11.7.4 Bridge source")


def replace_function(name: str, replacement: str) -> None:
    global source
    start = source.find(f"def {name}(")
    if start < 0:
        raise SystemExit(f"v0.11.7.6 missing Bridge function: {name}")
    end = source.find("\n\ndef ", start + 5)
    if end < 0:
        raise SystemExit(f"v0.11.7.6 could not bound Bridge function: {name}")
    source = source[:start] + replacement.rstrip() + source[end:]


# Keep only topical words. Ordinary conversational framing must not turn a broad
# memory question into a focused lookup for words such as "okay" or "actually".
query_tokens = r'''def _memory_query_tokens(value: str) -> set[str]:
    stop = {
        "the", "and", "for", "with", "that", "this", "what", "which", "where", "who", "when", "how",
        "are", "you", "your", "about", "right", "now", "tell", "me", "my", "i", "im", "i'm", "ive", "i've",
        "do", "does", "did", "kind", "usually", "know", "from", "stored", "memory", "remember", "remembered",
        "baby", "babe", "babydoll", "gorgeous", "doll", "girlfriend", "sweetheart",
        "our", "us", "a", "an", "of", "to", "in", "on", "is", "it",
        "ok", "okay", "actually", "really", "honestly", "seriously", "please", "just", "well", "hey", "hi",
        "so", "then", "else", "anything", "something", "everything", "whatever", "all", "much", "today",
        "still", "even", "exactly", "truly", "genuinely", "basically", "literally", "already", "maybe",
        "can", "could", "would", "will", "give", "share",
    }
    return {
        token for token in re.findall(r"[a-z0-9][a-z0-9_'-]{1,}", str(value or "").lower())
        if token not in stop
    }
'''
replace_function("_memory_query_tokens", query_tokens)


# A conversational preamble followed by a real question ("Okay babe, what about
# my hair?") is one request, not two memory topics.
query_parts = r'''def _personal_memory_query_parts(message: str) -> list[str]:
    raw = re.sub(r"\s+", " ", str(message or "").strip())
    if not raw:
        return []
    parts = re.split(
        r"(?:\s*(?:,|;)\s*(?:and\s+)?|\s+and\s+)(?=(?:what|which|where|who|when|how|do|am|have|did)\b)",
        raw,
        flags=re.I,
    )
    clean = []
    for part in parts:
        part = re.sub(r"^(?:baby|babe|babydoll|gorgeous|doll)[,:\s-]+", "", part.strip(), flags=re.I)
        part = part.strip(" ,;?")
        if len(part) >= 4 and part not in clean:
            clean.append(part)
    if len(clean) > 1:
        topical = [part for part in clean if _memory_query_tokens(part)]
        if topical:
            clean = topical
    return clean[:4] or [raw]
'''
replace_function("_personal_memory_query_parts", query_parts)


# A broad recall request has no search topic. Ask the authoritative worker for its
# highest-ranked facts instead of sending conversational filler as a fake query.
old_generic_post = '''        data = _memory_post(
            "/facts",
            {"query": str(message or "")[:5000], "limit": 12},
            timeout=1.4,
        )
'''
new_generic_post = '''        data = _memory_post(
            "/facts",
            {"query": "", "limit": 12},
            timeout=1.4,
        )
'''
if old_generic_post not in source:
    raise SystemExit("v0.11.7.6 generic authoritative-facts request anchor missing")
source = source.replace(old_generic_post, new_generic_post, 1)

source = source.replace(
    '"grounding": "verified-personal-memory-v1174"',
    '"grounding": "verified-personal-memory-v1176"',
)
source = source.replace(
    '"grounding": "verified-personal-memory-unavailable-v1174"',
    '"grounding": "verified-personal-memory-unavailable-v1176"',
)
source = source.replace('"version": "0.11.7.4"', '"version": "0.11.7.6"')

BRIDGE_PATH.write_text(source, encoding="utf-8")
compile(source, str(BRIDGE_PATH), "exec")

checks = [
    '"version": "0.11.7.6"',
    "verified-personal-memory-v1176",
    "verified-personal-memory-unavailable-v1176",
    '"ok", "okay", "actually", "really", "honestly"',
    '{"query": "", "limit": 12}',
    "topical = [part for part in clean if _memory_query_tokens(part)]",
    "def _memory_compose_verified_reply(",
]
final = BRIDGE_PATH.read_text(encoding="utf-8")
for marker in checks:
    if marker not in final:
        raise SystemExit(f"v0.11.7.6 Bridge verifier missing: {marker}")

print("Applied v0.11.7.6 generic conversational recall recovery")
