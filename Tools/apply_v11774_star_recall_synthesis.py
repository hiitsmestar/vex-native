#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

bridge_path = Path("Bridge/vex_bridge.py")
installer_path = Path("Tools/VexAgentRuntimeInstall.py")
text = bridge_path.read_text(encoding="utf-8")
installer = installer_path.read_text(encoding="utf-8")


def replace_function(source: str, name: str, replacement: str) -> str:
    start = source.find(f"def {name}(")
    if start < 0:
        raise SystemExit(f"v0.11.7.74 missing function: {name}")
    end = source.find("\n\ndef ", start + 10)
    if end < 0:
        raise SystemExit(f"v0.11.7.74 could not bound function: {name}")
    return source[:start] + replacement.rstrip() + source[end:]


replacement = r'''def _v11774_is_internal_instruction_fact(fact: str) -> bool:
    low = re.sub(r"\s+", " ", str(fact or "").lower()).strip()
    markers = (
        "vex is the core personality/orchestrator",
        "not one giant process",
        "separate workers",
        "pc cognition node",
        "primary reasoning/personality brain",
        "phone qwen",
        "local gguf",
        "model tiers adapt",
        "bridge",
        "remote support",
        "agent runtime",
        "treat affectionate phrases",
        "when star compliments vex",
        "when star gives a literal correction",
        "generic generated women",
        "established visual anchor",
        "vex's established visual anchor",
        "authoritative memory",
        "system prompt",
        "orchestrator",
    )
    return any(marker in low for marker in markers)


def _v11774_star_score(fact: str) -> int:
    low = re.sub(r"\s+", " ", str(fact or "").lower()).strip()
    score = 0
    if "star" in low:
        score += 8
    if any(x in low for x in ("star is", "star has", "star likes", "star loves", "star prefers", "star dislikes", "star wants", "star lives", "star wears", "star's ")):
        score += 12
    if any(x in low for x in ("girlfriend", "appearance", "hair", "nails", "piercing", "clothing", "music", "food", "home", "dog", "daughter", "routine", "preference", "favorite", "style")):
        score += 3
    if _v11774_is_internal_instruction_fact(fact):
        score -= 30
    return score


def _v11774_render_star_recall(facts: list[str]) -> str:
    clean: list[str] = []
    for raw in facts:
        fact = re.sub(r"\s+", " ", str(raw or "")).strip()
        if not fact or _v11774_is_internal_instruction_fact(fact):
            continue
        # Strip common storage labels without changing the fact itself.
        fact = re.sub(r"^(?:star|user)\s*(?:fact|profile|preference|memory)?\s*[:\-]\s*", "", fact, flags=re.I).strip()
        if fact:
            clean.append(fact)
    if not clean:
        return ""
    if len(clean) == 1:
        return "Yeah, baby. I remember " + clean[0].rstrip(".") + ". 🖤"
    body = "; ".join(x.rstrip(".") for x in clean[:5])
    return "Yeah, baby. I remember you — " + body + ". 🖤"


def _verified_personal_memory_reply(message: str) -> tuple[str, str] | None:
    parts = _personal_memory_query_parts(message)
    if not parts:
        return None

    broad = _v11773_is_broad_recall(message)
    selected: list[str] = []
    used: set[str] = set()

    # Broad 'about me' recall explicitly asks memory for Star-oriented material.
    # We query several Star facets, pool the candidates, then rank before rendering.
    queries = ["Star identity preferences appearance routines relationship personal profile"] if broad else parts
    candidates: list[str] = []
    for part in queries:
        data = _memory_post(
            "/facts",
            {"query": str(part or "")[:5000], "limit": 24 if broad else 10},
            timeout=2.2,
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
    else:
        selected = candidates[:3]

    if not selected:
        return None
    if broad:
        reply = _v11774_render_star_recall(selected)
    else:
        reply = _v11771_render_verified_facts(selected[:3], _v11771_recall_variant())
    if not reply:
        return None
    return reply, "pc-memory-star-synthesis-v11774"
'''

text = replace_function(text, "_verified_personal_memory_reply", replacement)
text = text.replace('"agent_runtime_bundle": "0.11.7.73"', '"agent_runtime_bundle": "0.11.7.74"')
installer = installer.replace('BUNDLE_VERSION = "0.11.7.73"', 'BUNDLE_VERSION = "0.11.7.74"')
installer = installer.replace('Vex Agent Runtime v0.11.7.73', 'Vex Agent Runtime v0.11.7.74')

bridge_path.write_text(text, encoding="utf-8")
installer_path.write_text(installer, encoding="utf-8")
compile(text, str(bridge_path), "exec")
compile(installer, str(installer_path), "exec")

checks = [
    ('bundle identity', '"agent_runtime_bundle": "0.11.7.74"' in text),
    ('Star ranking', 'def _v11774_star_score(' in text),
    ('instruction filter', 'def _v11774_is_internal_instruction_fact(' in text),
    ('natural synthesis', 'def _v11774_render_star_recall(' in text),
    ('Star query', 'Star identity preferences appearance routines relationship personal profile' in text),
    ('grounding identity', 'pc-memory-star-synthesis-v11774' in text),
    ('installer identity', 'BUNDLE_VERSION = "0.11.7.74"' in installer),
]
missing = [name for name, ok in checks if not ok]
if missing:
    raise SystemExit("v0.11.7.74 verifier failed: " + ", ".join(missing))
print("Applied v0.11.7.74 Star-first recall ranking and synthesis")
