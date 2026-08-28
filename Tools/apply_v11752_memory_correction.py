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
    raise SystemExit("v0.11.7.52 expected proven Bridge v0.11.7.39 identity")
if '"agent_runtime_bundle": "0.11.7.51"' not in bridge:
    raise SystemExit("v0.11.7.52 expected Agent Runtime bundle v0.11.7.51")
if 'BUNDLE_VERSION = "0.11.7.51"' not in installer:
    raise SystemExit("v0.11.7.52 expected installer v0.11.7.51")
if "def _explicit_memory_store(value: str) -> bool:" not in bridge:
    raise SystemExit("v0.11.7.52 expected .51 explicit memory write layer")

classifier_anchor = "def _personal_memory_fact_question(message: str) -> bool:\n"
helpers = r'''def _explicit_memory_correction_value(message: str) -> tuple[str, str] | None:
    raw = re.sub(r"\s+", " ", str(message or "").replace("’", "'")).strip()
    raw = raw.strip().strip('"“”').strip()
    if not raw:
        return None
    match = re.match(r"^(?:correction|correct|update|change)\s*:\s*(.+)$", raw, flags=re.I)
    if not match:
        return None
    body = match.group(1).strip()
    # The first sentence carries the mutation.  Follow-on wording such as
    # "Replace the old fact and remember ..." is instruction, not memory text.
    first = re.split(r"(?<=[.!?])\s+", body, maxsplit=1)[0].strip()
    pair = re.match(r"^(?P<new>.+?),\s*not\s+(?P<old>[^,.!?]+)[.!?]?$", first, flags=re.I)
    if not pair:
        return None
    new_fact = pair.group("new").strip().strip('"“”').strip()
    old_value = pair.group("old").strip().strip('"“”').strip()
    if len(new_fact) < 3 or len(new_fact) > 5000 or len(old_value) < 1 or len(old_value) > 500:
        return None
    return new_fact, old_value


def _explicit_memory_replace(new_fact: str, old_value: str) -> tuple[bool, str | None]:
    new_text = re.sub(r"\s+", " ", str(new_fact or "")).strip()[:5000]
    old_hint = re.sub(r"\s+", " ", str(old_value or "")).strip()[:500]
    if not new_text or not old_hint:
        return False, None

    found = _memory_post(
        "/search",
        {"query": old_hint, "memory_limit": 24, "episode_limit": 0},
        timeout=3.0,
    )
    memories = found.get("memories") if isinstance(found, dict) and isinstance(found.get("memories"), list) else []
    old_fold = old_hint.casefold()
    new_tokens = set(re.findall(r"[a-z0-9][a-z0-9_-]+", new_text.casefold()))
    candidates = []
    for item in memories:
        if not isinstance(item, dict):
            continue
        old_text = re.sub(r"\s+", " ", str(item.get("text") or "")).strip()
        if old_fold not in old_text.casefold():
            continue
        if str(item.get("kind") or "") != "explicit_user_memory":
            continue
        if not str(item.get("source_type") or "").startswith("user-explicit"):
            continue
        old_tokens = set(re.findall(r"[a-z0-9][a-z0-9_-]+", old_text.casefold()))
        overlap = len(new_tokens & old_tokens)
        candidates.append((overlap, float(item.get("updated_at") or 0.0), old_text))
    if not candidates:
        return False, None
    candidates.sort(reverse=True)
    old_text = candidates[0][2]

    # .51 used a hash of the exact explicit text as its canonical slot. Reusing
    # that canonical key makes MemoryDB.upsert_memory UPDATE the existing row;
    # the worker then refreshes FTS for the same id, so stale text stops winning.
    digest = hashlib.sha256(old_text.encode("utf-8", "ignore")).hexdigest()[:20]
    canonical_key = "explicit:star:" + digest
    now = time.time()
    result = _memory_post(
        "/sync",
        {
            "profile": {
                "memories": [{
                    "canonical_key": canonical_key,
                    "subject": "star",
                    "kind": "explicit_user_memory",
                    "text": new_text,
                    "tags": ["explicit", "user-authored", "correction", "current"],
                    "source_type": "user-explicit-correction",
                    "source_ref": "vexnative-live",
                    "authority": 100,
                    "confidence": 1.0,
                    "importance": 0.96,
                    "updated_at": now,
                }]
            }
        },
        timeout=4.0,
    )
    if not isinstance(result, dict) or result.get("ok") is not True:
        return False, old_text

    check_new = _memory_post(
        "/search",
        {"query": new_text, "memory_limit": 24, "episode_limit": 0},
        timeout=3.0,
    )
    current = check_new.get("memories") if isinstance(check_new, dict) and isinstance(check_new.get("memories"), list) else []
    new_fold = new_text.casefold()
    exact_new = any(
        str(item.get("text") or "").strip().casefold() == new_fold
        for item in current if isinstance(item, dict)
    )
    if not exact_new:
        return False, old_text

    check_old = _memory_post(
        "/search",
        {"query": old_hint, "memory_limit": 24, "episode_limit": 0},
        timeout=3.0,
    )
    stale = check_old.get("memories") if isinstance(check_old, dict) and isinstance(check_old.get("memories"), list) else []
    old_exact_fold = old_text.casefold()
    old_still_active = any(
        str(item.get("text") or "").strip().casefold() == old_exact_fold
        for item in stale if isinstance(item, dict)
    )
    return bool(exact_new and not old_still_active), old_text


'''
if "def _explicit_memory_correction_value(message: str) -> tuple[str, str] | None:" not in bridge:
    if classifier_anchor not in bridge:
        raise SystemExit("v0.11.7.52 memory classifier anchor missing")
    bridge = bridge.replace(classifier_anchor, helpers + classifier_anchor, 1)

old_guard = '''def _personal_memory_fact_question(message: str) -> bool:\n    if _explicit_memory_write_value(message) is not None:\n        return False\n'''
new_guard = '''def _personal_memory_fact_question(message: str) -> bool:\n    if _explicit_memory_correction_value(message) is not None:\n        return False\n    if _explicit_memory_write_value(message) is not None:\n        return False\n'''
if new_guard not in bridge:
    if old_guard not in bridge:
        raise SystemExit("v0.11.7.52 .51 memory classifier guard missing")
    bridge = bridge.replace(old_guard, new_guard, 1)

start = bridge.find('        if parsed.path == "/llm/chat":')
end = bridge.find('        if parsed.path == "/tts/speak":', start)
if start < 0 or end < 0:
    raise SystemExit("v0.11.7.52 cognition route anchors missing")
block = bridge[start:end]
if '"explicit-personal-memory-correction-v11752"' not in block:
    anchor = 'explicit_memory = _explicit_memory_write_value(message)\n'
    pos = block.find(anchor)
    if pos < 0:
        raise SystemExit("v0.11.7.52 .51 explicit write route anchor missing")
    line_start = block.rfind("\n", 0, pos) + 1
    indent = block[line_start:pos]
    route_template = '''
# v0.11.7.52: explicit corrections are mutations. Find the prior explicit fact,
# reuse its canonical slot, and let MemoryDB newest-evidence semantics replace it.
correction = _explicit_memory_correction_value(message)
if correction is not None:
    new_fact, old_value = correction
    replaced, old_fact = _explicit_memory_replace(new_fact, old_value)
    if replaced:
        shown = new_fact[:240]
        reply = f'Got it, baby - correction saved. I will remember "{shown}" as the current fact. 🖤'
        grounding = "explicit-personal-memory-correction-v11752"
    else:
        reply = "Baby, I understood that as a correction, but I could not verify replacing the old persistent-memory fact, so I am not going to pretend I updated it. 🖤"
        grounding = "explicit-personal-memory-correction-failed-v11752"
    _memory_record_turn(message, reply)
    self._json(200, {
        "ok": True,
        "reply": reply,
        "model": "pc-memory",
        "grounding": grounding,
        "memory": "persistent-pc",
        "memory_correction": bool(replaced),
        "superseded": bool(replaced and old_fact),
    })
    return
'''
    route = textwrap.indent(textwrap.dedent(route_template).lstrip("\n"), indent)
    block = block[:line_start] + route + block[line_start:]
    bridge = bridge[:start] + block + bridge[end:]

bridge = bridge.replace('"agent_runtime_bundle": "0.11.7.51"', '"agent_runtime_bundle": "0.11.7.52"', 1)
installer = installer.replace('BUNDLE_VERSION = "0.11.7.51"', 'BUNDLE_VERSION = "0.11.7.52"', 1)
installer = installer.replace("Vex Agent Runtime v0.11.7.51 installed.", "Vex Agent Runtime v0.11.7.52 installed.", 1)

BRIDGE.write_text(bridge, encoding="utf-8")
INSTALLER.write_text(installer, encoding="utf-8")
compile(bridge, str(BRIDGE), "exec")
compile(installer, str(INSTALLER), "exec")

for marker in [
    "def _explicit_memory_correction_value(message: str) -> tuple[str, str] | None:",
    "def _explicit_memory_replace(new_fact: str, old_value: str) -> tuple[bool, str | None]:",
    '"explicit-personal-memory-correction-v11752"',
    '"memory_correction": bool(replaced)',
    '"agent_runtime_bundle": "0.11.7.52"',
    '"version": "0.11.7.39"',
]:
    if marker not in bridge:
        raise SystemExit(f"v0.11.7.52 Bridge marker missing: {marker}")
if 'BUNDLE_VERSION = "0.11.7.52"' not in installer:
    raise SystemExit("v0.11.7.52 installer marker missing")

print("Applied v0.11.7.52 newest-correction-wins persistent-memory routing")
