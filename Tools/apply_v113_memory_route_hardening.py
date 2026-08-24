#!/usr/bin/env python3
from pathlib import Path
import re

path = Path("Bridge/vex_bridge.py")
text = path.read_text(encoding="utf-8")

# v0.11.3.2 field fix:
# - keep the self-contained verified-memory helpers from v0.11.3.1
# - recognize ordinary personal fact questions, not only prompts containing
#   literal words such as "remember" or "memory"
# - resolve those questions before the slower Qwen path so stored facts remain
#   fast and grounded while normal advice/creative requests still use cognition
helper_marker = 'def _memory_record_turn(message: str, reply: str) -> None:\n'
helper = r'''def _personal_memory_fact_question(message: str) -> bool:
    lower = " " + str(message or "").lower().replace("’", "'").strip() + " "
    if not lower.strip():
        return False

    # Explicit recall language remains the strongest signal.
    recall_words = (" remember", " memory", " memories", " know about me", " know about us")
    personal_words = (" me ", " my ", " i ", " i'm ", " i've ", " us ", " our ", " relationship", " girlfriend", " star")
    if any(word in lower for word in recall_words) and any(word in lower for word in personal_words):
        return True

    # Natural factual questions about Star should not require magic wording.
    # Exclude advice/planning requests so questions like "what should I wear?"
    # continue to use cognition rather than being mistaken for memory lookup.
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


def _verified_personal_memory_reply(message: str) -> tuple[str, str] | None:
    data = _memory_post(
        "/facts",
        {"query": str(message or "")[:5000], "limit": 8},
        timeout=1.4,
    )
    if not isinstance(data, dict):
        return None
    facts = data.get("facts") if isinstance(data.get("facts"), list) else []
    clean: list[str] = []
    for item in facts:
        if not isinstance(item, dict):
            continue
        fact = str(item.get("text") or "").strip()
        if fact and fact not in clean:
            clean.append(fact)
        if len(clean) >= 4:
            break
    if not clean:
        return None
    lines = ["Baby, pulling that from my stored memory. 🖤"]
    for index, fact in enumerate(clean, 1):
        lines.append(f"{index}. {fact}")
    return "\n".join(lines), "pc-memory"


'''

# Replace the old self-contained helper block if v0.11.3.1 already injected it;
# otherwise insert it before the memory turn recorder.
helper_start = text.find("def _personal_memory_fact_question(message: str) -> bool:")
if helper_start >= 0:
    helper_end = text.find(helper_marker, helper_start)
    if helper_end < 0:
        raise SystemExit("v0.11.3.2: could not find end of existing memory helpers")
    text = text[:helper_start] + helper + text[helper_end:]
else:
    if helper_marker not in text:
        raise SystemExit("v0.11.3.2: memory helper insertion marker not found")
    if "def _memory_post(" not in text:
        raise SystemExit("v0.11.3.2: _memory_post missing before helper insertion")
    text = text.replace(helper_marker, helper + helper_marker, 1)

start = text.find('        if parsed.path == "/llm/chat":')
if start < 0:
    raise SystemExit("v0.11.3.2: /llm/chat route not found")
end = text.find('        if parsed.path == "/tts/speak":', start)
if end < 0:
    raise SystemExit("v0.11.3.2: /llm/chat end marker not found")
block = text[start:end]

# Remove earlier v0.11.3/v0.11.3.1 live recall blocks before inserting the
# normalized v0.11.3.2 route exactly once.
for comment_marker in (
    '                # v0.11.3: explicit personal-memory questions are resolved here,',
    '                # v0.11.3.1: explicit personal-memory questions are resolved here,',
):
    old_start = block.find(comment_marker)
    if old_start >= 0:
        next_context = block.find('                context = {', old_start)
        next_cognition = block.find('                cognition_started = time.perf_counter()', old_start)
        candidates = [x for x in (next_context, next_cognition) if x >= 0]
        if candidates:
            block = block[:old_start] + block[min(candidates):]

marker = '"grounding": "verified-personal-memory-v1132"'
if marker not in block:
    pattern = re.compile(
        r'(\n\s*if not message or not isinstance\(history, list\):\n'
        r'\s*self\._json\(400, \{"ok": False, "error": "invalid cognition payload"\}\)\n'
        r'\s*return\n)',
        re.M,
    )
    match = pattern.search(block)
    if not match:
        raise SystemExit("v0.11.3.2: cognition payload validation anchor not found")

    insert = r'''
                # v0.11.3.2: explicit recall and ordinary factual questions about
                # Star are resolved from verified PC memory before Qwen generation.
                if _personal_memory_fact_question(message):
                    recall_started = time.perf_counter()
                    verified_memory = _verified_personal_memory_reply(message)
                    recall_ms = int((time.perf_counter() - recall_started) * 1000)
                    if verified_memory is None:
                        self._json(503, {
                            "ok": False,
                            "error": "verified personal memory unavailable",
                            "grounding": "verified-personal-memory-unavailable-v1132",
                            "timing_ms": recall_ms,
                        })
                        return
                    reply, model = verified_memory
                    _memory_record_turn(message, reply)
                    self._json(200, {
                        "ok": True,
                        "reply": reply,
                        "model": model,
                        "grounding": "verified-personal-memory-v1132",
                        "memory": "persistent-pc",
                        "timing_ms": recall_ms,
                    })
                    return
'''
    block = block[:match.end()] + insert + block[match.end():]
    text = text[:start] + block + text[end:]

for stale in ['"version": "0.10.8"', '"version": "0.10.9"', '"version": "0.11.0"', '"version": "0.11.2"', '"version": "0.11.3"', '"version": "0.11.3.1"']:
    text = text.replace(stale, '"version": "0.11.3.2"')

path.write_text(text, encoding="utf-8")
compile(text, str(path), "exec")

final = path.read_text(encoding="utf-8")
start = final.find('        if parsed.path == "/llm/chat":')
end = final.find('        if parsed.path == "/tts/speak":', start)
block = final[start:end]
for required in [
    "def _personal_memory_fact_question(",
    "def _verified_personal_memory_reply(",
    'if _personal_memory_fact_question(message):',
    '"grounding": "verified-personal-memory-v1132"',
    '"grounding": "verified-personal-memory-unavailable-v1132"',
    '"version": "0.11.3.2"',
    '" hair "',
    '" home "',
]:
    target = final if required.startswith("def ") or required.startswith('"version') or required in ('" hair "', '" home "') else block
    if required not in target:
        raise SystemExit(f"v0.11.3.2 verifier missing: {required}")
print("Applied v0.11.3.2 natural personal-fact routing + verified memory fast path")
