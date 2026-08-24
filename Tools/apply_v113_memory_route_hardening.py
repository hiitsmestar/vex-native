#!/usr/bin/env python3
from pathlib import Path
import re

path = Path("Bridge/vex_bridge.py")
text = path.read_text(encoding="utf-8")

# v0.11.3.3 field fix:
# - keep natural personal-fact routing from v0.11.3.2
# - split multi-part natural questions into focused memory queries
# - re-rank returned facts against each clause so generic high-authority profile
#   facts cannot crowd out the specific thing Star actually asked about
# - keep this Bridge-only so the installed v0.11.2 Memory Worker/database remain intact
helper_marker = 'def _memory_record_turn(message: str, reply: str) -> None:\n'
helper = r'''def _personal_memory_fact_question(message: str) -> bool:
    lower = " " + str(message or "").lower().replace("’", "'").strip() + " "
    if not lower.strip():
        return False

    recall_words = (" remember", " memory", " memories", " know about me", " know about us")
    personal_words = (" me ", " my ", " i ", " i'm ", " i've ", " us ", " our ", " relationship", " girlfriend", " star")
    if any(word in lower for word in recall_words) and any(word in lower for word in personal_words):
        return True

    advice_words = (
        " should ", " could ", " would ", " can you ", " help me ", " recommend ",
        " suggest ", " plan ", " want to ", " need to ", " going to ", " tonight ",
        " tomorrow ", " next ", " best way ", " how do i "
    )
    if any(word in lower for word in advice_words):
        return False

    has_personal_anchor = any(word in lower for word in (" my ", " me ", " i ", " i'm ", " i've ", " our ", " us "))
    if not has_personal_anchor:
        return False

    fact_question_starts = (
        " what ", " which ", " where ", " who ", " when ", " describe ", " tell me ",
        " do you know ", " do i ", " am i ", " have i ", " did i "
    )
    has_fact_question = any(token in lower for token in fact_question_starts)
    if not has_fact_question:
        return False

    factual_cues = (
        " color ", " hair ", " style ", " wear ", " look ", " appearance ", " home ",
        " house ", " live ", " name ", " age ", " height ", " size ", " favorite ",
        " prefer ", " preference ", " relationship ", " girlfriend ", " family ",
        " pets ", " animals ", " music ", " clothes ", " clothing ", " piercings ",
        " tattoos ", " nails ", " voice ", " work ", " project ", " vexnative "
    )
    return any(cue in lower for cue in factual_cues)


def _memory_query_tokens(value: str) -> set[str]:
    stop = {
        "the", "and", "for", "with", "that", "this", "what", "which", "where", "who", "when", "how",
        "are", "you", "your", "about", "right", "now", "tell", "me", "my", "i", "im", "i'm", "ive", "i've",
        "do", "does", "did", "kind", "usually", "know", "from", "stored", "memory", "remember", "baby", "babe",
        "our", "us", "a", "an", "of", "to", "in", "on", "is", "it"
    }
    return {
        token for token in re.findall(r"[a-z0-9][a-z0-9_'-]{1,}", str(value or "").lower())
        if token not in stop
    }


def _personal_memory_query_parts(message: str) -> list[str]:
    raw = re.sub(r"\s+", " ", str(message or "").strip())
    if not raw:
        return []
    # Multi-part questions often look like "what X, what Y, and what Z?".
    # Split only when another question clause clearly starts so ordinary prose is preserved.
    parts = re.split(
        r"\s*(?:,|;)?\s+(?:and\s+)?(?=(?:what|which|where|who|when|do|am|have|did)\b)",
        raw,
        flags=re.I,
    )
    clean = []
    for part in parts:
        part = re.sub(r"^(?:baby|babe|babydoll|gorgeous|doll)[,:\s-]+", "", part.strip(), flags=re.I)
        part = part.strip(" ,;?")
        if len(part) >= 4 and part not in clean:
            clean.append(part)
    return clean[:4] or [raw]


def _best_fact_for_query(query: str, facts: list[dict], used: set[str]) -> str | None:
    query_tokens = _memory_query_tokens(query)
    best: tuple[float, str] | None = None
    for item in facts:
        if not isinstance(item, dict):
            continue
        fact = re.sub(r"\s+", " ", str(item.get("text") or "")).strip()
        if not fact or fact in used:
            continue
        fact_tokens = _memory_query_tokens(fact)
        overlap = len(query_tokens & fact_tokens)
        # Query overlap dominates authority here: authority already filtered the worker's
        # candidate pool, while this stage exists specifically to preserve user intent.
        score = overlap * 12.0
        kind = str(item.get("kind") or "")
        if kind == "appearance" and query_tokens & {"hair", "color", "look", "appearance", "piercings", "tattoos", "nails"}:
            score += 4.0
        if kind in {"profile", "identity"} and query_tokens & {"home", "house", "live", "name", "age", "height", "size"}:
            score += 3.0
        if kind == "preference" and query_tokens & {"style", "wear", "clothes", "clothing", "favorite", "prefer", "preference"}:
            score += 4.0
        if kind == "relationship" and query_tokens & {"relationship", "girlfriend", "vex", "star"}:
            score += 4.0
        score += min(float(item.get("authority") or 0), 100.0) / 100.0
        if best is None or score > best[0]:
            best = (score, fact)

    if best is None:
        return None
    # For focused clauses, reject unrelated generic facts. Generic explicit recall
    # questions have no useful content tokens and may still accept the worker's top fact.
    if query_tokens and best[0] < 12.0:
        return None
    return best[1]


def _verified_personal_memory_reply(message: str) -> tuple[str, str] | None:
    parts = _personal_memory_query_parts(message)
    if not parts:
        return None

    selected: list[str] = []
    used: set[str] = set()
    for part in parts:
        data = _memory_post(
            "/facts",
            {"query": part[:5000], "limit": 8},
            timeout=1.4,
        )
        if not isinstance(data, dict):
            continue
        facts = data.get("facts") if isinstance(data.get("facts"), list) else []
        fact = _best_fact_for_query(part, facts, used)
        if fact:
            selected.append(fact)
            used.add(fact)

    # Generic one-part recall prompts still need a useful answer even when they contain
    # almost no topic words. Ask once with the full prompt and take up to three verified facts.
    if not selected and len(parts) == 1:
        data = _memory_post(
            "/facts",
            {"query": str(message or "")[:5000], "limit": 6},
            timeout=1.4,
        )
        if isinstance(data, dict):
            facts = data.get("facts") if isinstance(data.get("facts"), list) else []
            for item in facts:
                if not isinstance(item, dict):
                    continue
                fact = re.sub(r"\s+", " ", str(item.get("text") or "")).strip()
                if fact and fact not in used:
                    selected.append(fact)
                    used.add(fact)
                if len(selected) >= 3:
                    break

    if not selected:
        return None
    lines = ["Baby, pulling the specific bits you asked for from my stored memory. 🖤"]
    for index, fact in enumerate(selected[:4], 1):
        lines.append(f"{index}. {fact}")
    return "\n".join(lines), "pc-memory"


'''

helper_start = text.find("def _personal_memory_fact_question(message: str) -> bool:")
if helper_start >= 0:
    helper_end = text.find(helper_marker, helper_start)
    if helper_end < 0:
        raise SystemExit("v0.11.3.3: could not find end of existing memory helpers")
    text = text[:helper_start] + helper + text[helper_end:]
else:
    if helper_marker not in text:
        raise SystemExit("v0.11.3.3: memory helper insertion marker not found")
    if "def _memory_post(" not in text:
        raise SystemExit("v0.11.3.3: _memory_post missing before helper insertion")
    text = text.replace(helper_marker, helper + helper_marker, 1)

start = text.find('        if parsed.path == "/llm/chat":')
if start < 0:
    raise SystemExit("v0.11.3.3: /llm/chat route not found")
end = text.find('        if parsed.path == "/tts/speak":', start)
if end < 0:
    raise SystemExit("v0.11.3.3: /llm/chat end marker not found")
block = text[start:end]

for comment_marker in (
    '                # v0.11.3: explicit personal-memory questions are resolved here,',
    '                # v0.11.3.1: explicit personal-memory questions are resolved here,',
    '                # v0.11.3.2: explicit recall and ordinary factual questions about',
):
    old_start = block.find(comment_marker)
    if old_start >= 0:
        next_context = block.find('                context = {', old_start)
        next_cognition = block.find('                cognition_started = time.perf_counter()', old_start)
        candidates = [x for x in (next_context, next_cognition) if x >= 0]
        if candidates:
            block = block[:old_start] + block[min(candidates):]

marker = '"grounding": "verified-personal-memory-v1133"'
if marker not in block:
    pattern = re.compile(
        r'(\n\s*if not message or not isinstance\(history, list\):\n'
        r'\s*self\._json\(400, \{"ok": False, "error": "invalid cognition payload"\}\)\n'
        r'\s*return\n)',
        re.M,
    )
    match = pattern.search(block)
    if not match:
        raise SystemExit("v0.11.3.3: cognition payload validation anchor not found")

    insert = r'''
                # v0.11.3.3: natural personal fact questions use focused verified
                # memory retrieval before Qwen, preserving the exact topic(s) asked.
                if _personal_memory_fact_question(message):
                    recall_started = time.perf_counter()
                    verified_memory = _verified_personal_memory_reply(message)
                    recall_ms = int((time.perf_counter() - recall_started) * 1000)
                    if verified_memory is None:
                        self._json(503, {
                            "ok": False,
                            "error": "verified personal memory unavailable",
                            "grounding": "verified-personal-memory-unavailable-v1133",
                            "timing_ms": recall_ms,
                        })
                        return
                    reply, model = verified_memory
                    _memory_record_turn(message, reply)
                    self._json(200, {
                        "ok": True,
                        "reply": reply,
                        "model": model,
                        "grounding": "verified-personal-memory-v1133",
                        "memory": "persistent-pc",
                        "timing_ms": recall_ms,
                    })
                    return
'''
    block = block[:match.end()] + insert + block[match.end():]
    text = text[:start] + block + text[end:]

for stale in [
    '"version": "0.10.8"', '"version": "0.10.9"', '"version": "0.11.0"',
    '"version": "0.11.2"', '"version": "0.11.3"', '"version": "0.11.3.1"',
    '"version": "0.11.3.2"'
]:
    text = text.replace(stale, '"version": "0.11.3.3"')

path.write_text(text, encoding="utf-8")
compile(text, str(path), "exec")

final = path.read_text(encoding="utf-8")
start = final.find('        if parsed.path == "/llm/chat":')
end = final.find('        if parsed.path == "/tts/speak":', start)
block = final[start:end]
for required in [
    "def _personal_memory_fact_question(",
    "def _personal_memory_query_parts(",
    "def _best_fact_for_query(",
    "def _verified_personal_memory_reply(",
    'if _personal_memory_fact_question(message):',
    '"grounding": "verified-personal-memory-v1133"',
    '"grounding": "verified-personal-memory-unavailable-v1133"',
    '"version": "0.11.3.3"',
]:
    target = final if required.startswith("def ") or required.startswith('"version') else block
    if required not in target:
        raise SystemExit(f"v0.11.3.3 verifier missing: {required}")
print("Applied v0.11.3.3 query-faithful natural verified-memory recall")
