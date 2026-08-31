#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re

bridge_path = Path("Bridge/vex_bridge.py")
installer_path = Path("Tools/VexAgentRuntimeInstall.py")
text = bridge_path.read_text(encoding="utf-8")
installer = installer_path.read_text(encoding="utf-8")


def replace_function(source: str, name: str, replacement: str) -> str:
    start = source.find(f"def {name}(")
    if start < 0:
        raise SystemExit(f"v0.11.7.73 missing function: {name}")
    end = source.find("\n\ndef ", start + 10)
    if end < 0:
        raise SystemExit(f"v0.11.7.73 could not bound function: {name}")
    return source[:start] + replacement.rstrip() + source[end:]


replacement = r'''def _v11773_normalize_recall_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _v11773_is_prompt_like_fact(fact: str, query: str) -> bool:
    fact = re.sub(r"\s+", " ", str(fact or "")).strip()
    if not fact:
        return True
    low = fact.lower()
    # A stored question/control utterance is conversational history, not a personal fact.
    if fact.endswith("?"):
        return True
    prompt_markers = (
        "what do you remember about me",
        "what do you know about me",
        "tell me what you remember",
        "can you remember",
        "do you remember me",
        "star's newest message",
        "newest message (verbatim)",
        "user asked:",
        "star asked:",
    )
    if any(marker in low for marker in prompt_markers):
        return True
    nf = _v11773_normalize_recall_text(fact)
    nq = _v11773_normalize_recall_text(query)
    if nf and nq and nf == nq:
        return True
    # Reject near-copies of the current prompt while still allowing a real fact that
    # happens to share one or two words with the question.
    if nf and nq:
        fs = set(nf.split())
        qs = set(nq.split())
        if len(fs) <= len(qs) + 3 and len(fs & qs) >= max(3, int(len(fs) * 0.78)):
            return True
    return False


def _v11773_is_broad_recall(message: str) -> bool:
    low = re.sub(r"\s+", " ", str(message or "").lower()).strip()
    broad = (
        "what do you remember about me",
        "what do you know about me",
        "tell me what you remember about me",
        "tell me about me",
        "what have you got saved about me",
        "what have you learned about me",
    )
    return any(phrase in low for phrase in broad)


def _verified_personal_memory_reply(message: str) -> tuple[str, str] | None:
    parts = _personal_memory_query_parts(message)
    if not parts:
        return None

    selected: list[str] = []
    used: set[str] = set()

    # Broad recall is intentionally query-neutral. /facts already ranks only
    # authoritative Star/vex-star identity/preference/profile/relationship/project
    # rows; feeding the literal question back into retrieval was allowing a synced
    # question-shaped row to win and echo Star's prompt.
    queries = [""] if _v11773_is_broad_recall(message) else parts
    for part in queries:
        data = _memory_post(
            "/facts",
            {"query": str(part or "")[:5000], "limit": 12 if not part else 8},
            timeout=1.6,
        )
        if not isinstance(data, dict):
            continue
        facts = data.get("facts") if isinstance(data.get("facts"), list) else []
        for item in facts:
            fact = _v11771_fact_text(item)
            if not fact or _v11773_is_prompt_like_fact(fact, message):
                continue
            key = _v11773_normalize_recall_text(fact)
            if not key or key in used:
                continue
            selected.append(fact)
            used.add(key)
            if len(selected) >= (4 if _v11773_is_broad_recall(message) else 3):
                break
        if selected and not _v11773_is_broad_recall(message):
            break

    if not selected:
        return None
    reply = _v11771_render_verified_facts(selected[:4], _v11771_recall_variant())
    if not reply:
        return None
    return reply, "pc-memory-facts-v11773"
'''

text = replace_function(text, "_verified_personal_memory_reply", replacement)
text = text.replace('"agent_runtime_bundle": "0.11.7.71"', '"agent_runtime_bundle": "0.11.7.73"')
installer = installer.replace('BUNDLE_VERSION = "0.11.7.72"', 'BUNDLE_VERSION = "0.11.7.73"')
installer = installer.replace('Vex Agent Runtime v0.11.7.72', 'Vex Agent Runtime v0.11.7.73')

bridge_path.write_text(text, encoding="utf-8")
installer_path.write_text(installer, encoding="utf-8")
compile(text, str(bridge_path), "exec")
compile(installer, str(installer_path), "exec")

checks = [
    ('bundle identity', '"agent_runtime_bundle": "0.11.7.73"' in text),
    ('prompt guard', 'def _v11773_is_prompt_like_fact(' in text),
    ('broad recall', 'def _v11773_is_broad_recall(' in text and 'queries = [""]' in text),
    ('question rejection', 'fact.endswith("?")' in text),
    ('new grounding identity', 'pc-memory-facts-v11773' in text),
    ('installer identity', 'BUNDLE_VERSION = "0.11.7.73"' in installer),
]
missing = [name for name, ok in checks if not ok]
if missing:
    raise SystemExit("v0.11.7.73 verifier failed: " + ", ".join(missing))
print("Applied v0.11.7.73 broad-recall prompt contamination guard")
