#!/usr/bin/env python3
from pathlib import Path
import re

path = Path("Bridge/vex_bridge.py")
text = path.read_text(encoding="utf-8")

start = text.find('        if parsed.path == "/llm/chat":')
if start < 0:
    raise SystemExit("v0.11.3: /llm/chat route not found")
end = text.find('        if parsed.path == "/tts/speak":', start)
if end < 0:
    raise SystemExit("v0.11.3: /llm/chat end marker not found")
block = text[start:end]

marker = '"grounding": "verified-personal-memory-v113"'
if marker not in block:
    # Anchor immediately after payload validation inside the live /llm/chat handler.
    # v0.11.2 inserted its route using a generic `context = {` marker; field testing
    # proved that marker was not reliable enough across the long historical patch chain.
    pattern = re.compile(
        r'(\n\s*if not message or not isinstance\(history, list\):\n'
        r'\s*self\._json\(400, \{"ok": False, "error": "invalid cognition payload"\}\)\n'
        r'\s*return\n)',
        re.M,
    )
    match = pattern.search(block)
    if not match:
        raise SystemExit("v0.11.3: cognition payload validation anchor not found")

    insert = r'''
                # v0.11.3: explicit personal-memory questions are resolved here,
                # inside the live /llm/chat route, before any Qwen generation.
                # If verified memory is unavailable we fail closed instead of letting
                # the small model invent personal history.
                if _personal_memory_fact_question(message):
                    recall_started = time.perf_counter()
                    verified_memory = _verified_personal_memory_reply(message)
                    recall_ms = int((time.perf_counter() - recall_started) * 1000)
                    if verified_memory is None:
                        self._json(503, {
                            "ok": False,
                            "error": "verified personal memory unavailable",
                            "grounding": "verified-personal-memory-unavailable-v113",
                            "timing_ms": recall_ms,
                        })
                        return
                    reply, model = verified_memory
                    _memory_record_turn(message, reply)
                    self._json(200, {
                        "ok": True,
                        "reply": reply,
                        "model": model,
                        "grounding": "verified-personal-memory-v113",
                        "memory": "persistent-pc",
                        "timing_ms": recall_ms,
                    })
                    return
'''
    block = block[:match.end()] + insert + block[match.end():]
    text = text[:start] + block + text[end:]

# Make the Bridge status/version visible during field diagnostics. The historical
# patch chain can leave the status payload reporting an old component version even
# when the executable is new; normalize common stale values in the final source.
for stale in ['"version": "0.10.8"', '"version": "0.10.9"', '"version": "0.11.0"', '"version": "0.11.2"']:
    text = text.replace(stale, '"version": "0.11.3"')

path.write_text(text, encoding="utf-8")
compile(text, str(path), "exec")

final = path.read_text(encoding="utf-8")
start = final.find('        if parsed.path == "/llm/chat":')
end = final.find('        if parsed.path == "/tts/speak":', start)
block = final[start:end]
for required in [
    'if _personal_memory_fact_question(message):',
    '"grounding": "verified-personal-memory-v113"',
    '"grounding": "verified-personal-memory-unavailable-v113"',
    'verified personal memory unavailable',
]:
    if required not in block:
        raise SystemExit(f"v0.11.3 live-route verifier missing: {required}")
print("Applied v0.11.3 verified memory route hardening inside live /llm/chat")
