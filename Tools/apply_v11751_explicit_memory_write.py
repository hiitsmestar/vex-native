#!/usr/bin/env python3
from __future__ import annotations

import re
import textwrap
from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
INSTALLER = Path("Tools/VexAgentRuntimeInstall.py")

bridge = BRIDGE.read_text(encoding="utf-8")
installer = INSTALLER.read_text(encoding="utf-8")

if '"version": "0.11.7.39"' not in bridge:
    raise SystemExit("v0.11.7.51 expected proven Bridge v0.11.7.39 identity")
if '"agent_runtime_bundle": "0.11.7.50"' not in bridge:
    raise SystemExit("v0.11.7.51 expected Agent Runtime bundle v0.11.7.50")
if 'BUNDLE_VERSION = "0.11.7.50"' not in installer:
    raise SystemExit("v0.11.7.51 expected installer v0.11.7.50")
if "def _memory_post(" not in bridge or "def _memory_record_turn(" not in bridge:
    raise SystemExit("v0.11.7.51 persistent-memory helpers missing")

classifier_anchor = "def _personal_memory_fact_question(message: str) -> bool:\n"
helpers = r'''def _explicit_memory_write_value(message: str) -> str | None:
    raw = re.sub(r"\s+", " ", str(message or "").replace("’", "'")).strip()
    if not raw:
        return None
    low = raw.lower()

    recall_prefixes = (
        "do you remember", "can you remember", "could you remember",
        "remember when", "remember what", "remember where", "remember who",
        "remember how", "remember why", "remember if", "remember whether",
    )
    if any(low.startswith(prefix) for prefix in recall_prefixes):
        return None

    remainder = None
    match = re.match(r"^(?:please\s+)?(?:remember|save|store)\b\s*(.*)$", raw, flags=re.I)
    if match:
        remainder = match.group(1).strip()
    else:
        keep = re.match(r"^(?:please\s+)?keep\s+(.+?)\s+in\s+(?:your\s+)?memory\s*[.!]?$", raw, flags=re.I)
        if keep:
            remainder = keep.group(1).strip()
    if remainder is None:
        return None

    if raw.endswith("?") and ":" not in remainder:
        return None

    if ":" in remainder:
        tail = remainder.split(":", 1)[1].strip()
        if tail:
            remainder = tail
    else:
        remainder = re.sub(r"^(?:this|that)\s+", "", remainder, flags=re.I)
        remainder = re.sub(r"^for\s+me\s+", "", remainder, flags=re.I)
        remainder = re.sub(r"^(?:this|that)\s+", "", remainder, flags=re.I)

    value = remainder.strip().strip('"').strip()
    if len(value) < 2 or len(value) > 5000:
        return None
    return value


def _explicit_memory_store(value: str) -> bool:
    text_value = re.sub(r"\s+", " ", str(value or "")).strip()[:5000]
    if not text_value:
        return False
    digest = hashlib.sha256(text_value.encode("utf-8", "ignore")).hexdigest()[:20]
    now = time.time()
    result = _memory_post(
        "/sync",
        {
            "profile": {
                "memories": [{
                    "canonical_key": "explicit:star:" + digest,
                    "subject": "star",
                    "kind": "explicit_user_memory",
                    "text": text_value,
                    "tags": ["explicit", "user-authored", "remember"],
                    "source_type": "user-explicit",
                    "source_ref": "vexnative-live",
                    "authority": 100,
                    "confidence": 1.0,
                    "importance": 0.92,
                    "created_at": now,
                    "updated_at": now,
                }]
            }
        },
        timeout=4.0,
    )
    if not isinstance(result, dict):
        return False

    check = _memory_post(
        "/search",
        {"query": text_value, "memory_limit": 16, "episode_limit": 0},
        timeout=2.5,
    )
    memories = check.get("memories") if isinstance(check, dict) and isinstance(check.get("memories"), list) else []
    expected = text_value.casefold()
    return any(
        str(item.get("text") or "").strip().casefold() == expected
        for item in memories
        if isinstance(item, dict)
    )


'''
if "def _explicit_memory_write_value(message: str) -> str | None:" not in bridge:
    if classifier_anchor not in bridge:
        raise SystemExit("v0.11.7.51 personal-memory recall classifier anchor missing")
    bridge = bridge.replace(classifier_anchor, helpers + classifier_anchor, 1)

classifier_guard = '''def _personal_memory_fact_question(message: str) -> bool:\n'''
classifier_guarded = '''def _personal_memory_fact_question(message: str) -> bool:\n    if _explicit_memory_write_value(message) is not None:\n        return False\n'''
if classifier_guarded not in bridge:
    if classifier_guard not in bridge:
        raise SystemExit("v0.11.7.51 recall classifier definition missing")
    bridge = bridge.replace(classifier_guard, classifier_guarded, 1)

start = bridge.find('        if parsed.path == "/llm/chat":')
if start < 0:
    raise SystemExit("v0.11.7.51 /llm/chat route missing")
end = bridge.find('        if parsed.path == "/tts/speak":', start)
if end < 0:
    raise SystemExit("v0.11.7.51 /llm/chat end marker missing")
block = bridge[start:end]

if '"explicit-personal-memory-write-v11751"' not in block:
    pattern = re.compile(
        r'(\n(?P<indent>\s*)if not message or not isinstance\(history, list\):\n'
        r'(?P=indent)\s*self\._json\(400, \{"ok": False, "error": "invalid cognition payload"\}\)\n'
        r'(?P=indent)\s*return\n)',
        re.M,
    )
    match = pattern.search(block)
    if not match:
        raise SystemExit("v0.11.7.51 cognition payload validation anchor missing")

    indent = match.group("indent")
    route_template = '''
# v0.11.7.51: explicit remember/save/store is a trusted WRITE,
# not a question asking verified memory for an existing fact.
explicit_memory = _explicit_memory_write_value(message)
if explicit_memory is not None:
    stored = _explicit_memory_store(explicit_memory)
    if stored:
        shown = explicit_memory[:240]
        reply = f'Got it, baby - I will remember "{shown}". 🖤'
        grounding = "explicit-personal-memory-write-v11751"
    else:
        reply = "Baby, I understood that as something you wanted me to remember, but the persistent memory write did not verify, so I am not going to pretend I saved it. 🖤"
        grounding = "explicit-personal-memory-write-failed-v11751"
    _memory_record_turn(message, reply)
    self._json(200, {
        "ok": True,
        "reply": reply,
        "model": "pc-memory",
        "grounding": grounding,
        "memory": "persistent-pc",
        "memory_write": bool(stored),
    })
    return
'''
    write_route = textwrap.indent(textwrap.dedent(route_template).lstrip("\n"), indent)
    block = block[:match.end()] + write_route + block[match.end():]
    bridge = bridge[:start] + block + bridge[end:]

bridge = bridge.replace('"agent_runtime_bundle": "0.11.7.50"', '"agent_runtime_bundle": "0.11.7.51"', 1)
installer = installer.replace('BUNDLE_VERSION = "0.11.7.50"', 'BUNDLE_VERSION = "0.11.7.51"', 1)
installer = installer.replace("Vex Agent Runtime v0.11.7.50 installed.", "Vex Agent Runtime v0.11.7.51 installed.", 1)

BRIDGE.write_text(bridge, encoding="utf-8")
INSTALLER.write_text(installer, encoding="utf-8")
compile(bridge, str(BRIDGE), "exec")
compile(installer, str(INSTALLER), "exec")

final_start = bridge.find('        if parsed.path == "/llm/chat":')
final_end = bridge.find('        if parsed.path == "/tts/speak":', final_start)
final_block = bridge[final_start:final_end]
for marker in [
    "def _explicit_memory_write_value(message: str) -> str | None:",
    "def _explicit_memory_store(value: str) -> bool:",
    "if _explicit_memory_write_value(message) is not None:",
    '"agent_runtime_bundle": "0.11.7.51"',
    '"version": "0.11.7.39"',
]:
    if marker not in bridge:
        raise SystemExit(f"v0.11.7.51 Bridge marker missing: {marker}")
for marker in [
    'explicit_memory = _explicit_memory_write_value(message)',
    '"explicit-personal-memory-write-v11751"',
    '"memory_write": bool(stored)',
]:
    if marker not in final_block:
        raise SystemExit(f"v0.11.7.51 cognition block marker missing: {marker}")
if 'BUNDLE_VERSION = "0.11.7.51"' not in installer:
    raise SystemExit("v0.11.7.51 installer marker missing")

print("Applied v0.11.7.51 explicit persistent-memory write routing")
