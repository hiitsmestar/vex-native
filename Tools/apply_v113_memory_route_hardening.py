#!/usr/bin/env python3
from pathlib import Path
import re

path = Path("Bridge/vex_bridge.py")
text = path.read_text(encoding="utf-8")

# v0.11.3.1 field fix: v0.11.2's patch can abort before writing Bridge source
# when an old cognition-timing marker is absent. That left the v0.11.3 route
# calling helper functions that were never actually written into vex_bridge.py.
# Make this patch self-contained instead of depending on the earlier patch having
# finished successfully.
helper_marker = 'def _memory_record_turn(message: str, reply: str) -> None:\n'
helper = r'''def _personal_memory_fact_question(message: str) -> bool:
    lower = str(message or "").lower().replace("’", "'").strip()
    if not lower:
        return False
    recall_words = ("remember", "memory", "memories", "know about me", "know about us")
    if not any(word in lower for word in recall_words):
        return False
    personal_words = (" me", "my ", "about me", " us", "our ", "relationship", "girlfriend", "star")
    return any(word in (" " + lower) for word in personal_words)


def _verified_personal_memory_reply(message: str) -> tuple[str, str] | None:
    data = _memory_post(
        "/facts",
        {"query": str(message or "")[:5000], "limit": 6},
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
        if len(clean) >= 3:
            break
    if not clean:
        return None
    lines = ["Baby, actual stored-memory answer — no glitter improv this time. 🖤"]
    for index, fact in enumerate(clean, 1):
        lines.append(f"{index}. {fact}")
    return "\n".join(lines), "pc-memory"


'''

if "def _personal_memory_fact_question(" not in text:
    if helper_marker not in text:
        raise SystemExit("v0.11.3.1: memory helper insertion marker not found")
    if "def _memory_post(" not in text:
        raise SystemExit("v0.11.3.1: _memory_post missing before helper insertion")
    text = text.replace(helper_marker, helper + helper_marker, 1)

start = text.find('        if parsed.path == "/llm/chat":')
if start < 0:
    raise SystemExit("v0.11.3.1: /llm/chat route not found")
end = text.find('        if parsed.path == "/tts/speak":', start)
if end < 0:
    raise SystemExit("v0.11.3.1: /llm/chat end marker not found")
block = text[start:end]

# Remove the older v0.11.3 block if it is already present in a partially patched tree.
old_start = block.find('                # v0.11.3: explicit personal-memory questions are resolved here,')
if old_start >= 0:
    old_end_marker = '                    return\n'
    # The route contains several returns; terminate at the final response return by
    # locating the next context construction or cognition marker after the block.
    next_context = block.find('                context = {', old_start)
    next_cognition = block.find('                cognition_started = time.perf_counter()', old_start)
    candidates = [x for x in (next_context, next_cognition) if x >= 0]
    if candidates:
        old_end = min(candidates)
        block = block[:old_start] + block[old_end:]

marker = '"grounding": "verified-personal-memory-v1131"'
if marker not in block:
    pattern = re.compile(
        r'(\n\s*if not message or not isinstance\(history, list\):\n'
        r'\s*self\._json\(400, \{"ok": False, "error": "invalid cognition payload"\}\)\n'
        r'\s*return\n)',
        re.M,
    )
    match = pattern.search(block)
    if not match:
        raise SystemExit("v0.11.3.1: cognition payload validation anchor not found")

    insert = r'''
                # v0.11.3.1: explicit personal-memory questions are resolved here,
                # inside the live /llm/chat route, before any Qwen generation.
                if _personal_memory_fact_question(message):
                    recall_started = time.perf_counter()
                    verified_memory = _verified_personal_memory_reply(message)
                    recall_ms = int((time.perf_counter() - recall_started) * 1000)
                    if verified_memory is None:
                        self._json(503, {
                            "ok": False,
                            "error": "verified personal memory unavailable",
                            "grounding": "verified-personal-memory-unavailable-v1131",
                            "timing_ms": recall_ms,
                        })
                        return
                    reply, model = verified_memory
                    _memory_record_turn(message, reply)
                    self._json(200, {
                        "ok": True,
                        "reply": reply,
                        "model": model,
                        "grounding": "verified-personal-memory-v1131",
                        "memory": "persistent-pc",
                        "timing_ms": recall_ms,
                    })
                    return
'''
    block = block[:match.end()] + insert + block[match.end():]
    text = text[:start] + block + text[end:]

for stale in ['"version": "0.10.8"', '"version": "0.10.9"', '"version": "0.11.0"', '"version": "0.11.2"', '"version": "0.11.3"']:
    text = text.replace(stale, '"version": "0.11.3.1"')

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
    '"grounding": "verified-personal-memory-v1131"',
    '"grounding": "verified-personal-memory-unavailable-v1131"',
    'verified personal memory unavailable',
]:
    target = final if required.startswith("def ") else block
    if required not in target:
        raise SystemExit(f"v0.11.3.1 verifier missing: {required}")
print("Applied v0.11.3.1 self-contained verified memory helpers + live route")
