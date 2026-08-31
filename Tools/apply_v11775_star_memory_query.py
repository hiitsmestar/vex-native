#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

# Build trigger: 2026-08-31 field recall repair.
bridge_path = Path("Bridge/vex_bridge.py")
installer_path = Path("Tools/VexAgentRuntimeInstall.py")
text = bridge_path.read_text(encoding="utf-8")
installer = installer_path.read_text(encoding="utf-8")


def replace_function(source: str, name: str, replacement: str) -> str:
    start = source.find(f"def {name}(")
    if start < 0:
        raise SystemExit(f"v0.11.7.75 missing function: {name}")
    end = source.find("\n\ndef ", start + 10)
    if end < 0:
        raise SystemExit(f"v0.11.7.75 could not bound function: {name}")
    return source[:start] + replacement.rstrip() + source[end:]


replacement = r'''def _verified_personal_memory_reply(message: str) -> tuple[str, str] | None:
    parts = _personal_memory_query_parts(message)
    if not parts:
        return None

    broad = _v11773_is_broad_recall(message)
    used: set[str] = set()
    candidates: list[str] = []

    # MemoryWorker indexes subject + text + tags. A long natural-language FTS
    # query can become over-constrained, so broad Star recall intentionally uses
    # several small OR-like probes and pools the results before ranking.
    if broad:
        queries = [
            "star",
            "profile",
            "preference",
            "appearance",
            "routine",
            "relationship",
            "favorite",
        ]
    else:
        queries = parts

    for part in queries:
        data = _memory_post(
            "/facts",
            {"query": str(part or "")[:5000], "limit": 32 if broad else 10},
            timeout=2.8,
        )
        if not isinstance(data, dict):
            continue
        facts = data.get("facts") if isinstance(data.get("facts"), list) else []
        for item in facts:
            fact = _v11771_fact_text(item)
            if not fact or _v11773_is_prompt_like_fact(fact, message):
                continue
            if broad and _v11774_is_internal_instruction_fact(fact):
                continue
            key = _v11773_normalize_recall_text(fact)
            if not key or key in used:
                continue
            used.add(key)
            candidates.append(fact)

    if broad:
        candidates.sort(key=lambda fact: (_v11774_star_score(fact), len(fact)), reverse=True)
        selected = [fact for fact in candidates if _v11774_star_score(fact) > 0][:5]
        # The authoritative user profile can be written as one long record that
        # does not repeat the word Star throughout. If the Star subject probe
        # returned it, keep the best non-internal record rather than reporting
        # a false "no trusted fact" result.
        if not selected:
            selected = [fact for fact in candidates if not _v11774_is_internal_instruction_fact(fact)][:3]
        if not selected:
            return None
        reply = _v11774_render_star_recall(selected)
    else:
        selected = candidates[:3]
        if not selected:
            return None
        reply = _v11771_render_verified_facts(selected, _v11771_recall_variant())

    if not reply:
        return None
    return reply, "pc-memory-star-query-v11775"
'''

text = replace_function(text, "_verified_personal_memory_reply", replacement)
text = text.replace('"agent_runtime_bundle": "0.11.7.74"', '"agent_runtime_bundle": "0.11.7.75"')
installer = installer.replace('BUNDLE_VERSION = "0.11.7.74"', 'BUNDLE_VERSION = "0.11.7.75"')
installer = installer.replace('Vex Agent Runtime v0.11.7.74', 'Vex Agent Runtime v0.11.7.75')

bridge_path.write_text(text, encoding="utf-8")
installer_path.write_text(installer, encoding="utf-8")
compile(text, str(bridge_path), "exec")
compile(installer, str(installer_path), "exec")

checks = [
    ('bundle identity', '"agent_runtime_bundle": "0.11.7.75"' in text),
    ('simple star probe', '"star",' in text),
    ('profile probe', '"profile",' in text),
    ('pooled ranking', 'candidates.sort(key=lambda fact: (_v11774_star_score(fact), len(fact)), reverse=True)' in text),
    ('fallback candidate', 'if not selected:' in text),
    ('grounding identity', 'pc-memory-star-query-v11775' in text),
    ('installer identity', 'BUNDLE_VERSION = "0.11.7.75"' in installer),
]
missing = [name for name, ok in checks if not ok]
if missing:
    raise SystemExit("v0.11.7.75 verifier failed: " + ", ".join(missing))
print("Applied v0.11.7.75 broad Star memory query fix")
