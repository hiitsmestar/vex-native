#!/usr/bin/env python3
from __future__ import annotations

import textwrap
from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
MEMORY = Path("Tools/VexMemoryWorker.py")
bridge = BRIDGE.read_text(encoding="utf-8")
memory = MEMORY.read_text(encoding="utf-8")

# v0.11.7.52 hotfix: stop guessing MemoryWorker canonical keys. The .51 /sync
# path deliberately owns canonicalization, so correction now replaces the exact
# verified memory row by its returned id through a tiny loopback-only /replace API.
replace_method = r'''
    def replace_memory(self, memory_id: str, expected_old_text: str, item: dict[str, Any], default_source: str = "user-explicit-correction") -> bool:
        memory_id = _clean(memory_id, 200)
        expected_old = _clean(expected_old_text, 24000)
        text = _clean(item.get("text"), 24000)
        if not memory_id or not expected_old or not text:
            return False
        with self.lock:
            existing = self.conn.execute(
                "SELECT * FROM memories WHERE id=? AND active=1", (memory_id,)
            ).fetchone()
            if not existing:
                return False
            if str(existing["kind"] or "") != "explicit_user_memory":
                return False
            if _clean(existing["text"], 24000).casefold() != expected_old.casefold():
                return False

            subject = _clean(item.get("subject") or existing["subject"], 200).lower()
            kind = _clean(item.get("kind") or existing["kind"], 80).lower() or "explicit_user_memory"
            tags_value = item.get("tags")
            if isinstance(tags_value, list):
                tags = " ".join(_clean(v, 120) for v in tags_value if _clean(v, 120))
            else:
                tags = _clean(tags_value, 1000) or str(existing["tags"] or "")
            source_type = _clean(item.get("source_type") or item.get("source") or default_source, 120)
            source_ref = _clean(item.get("source_ref"), 500) or str(existing["source_ref"] or "")
            authority = max(int(existing["authority"]), max(0, min(100, int(item.get("authority") or 100))))
            confidence = max(float(existing["confidence"]), max(0.0, min(1.0, float(item.get("confidence") if item.get("confidence") is not None else 1.0))))
            importance = max(float(existing["importance"]), max(0.0, min(1.0, float(item.get("importance") if item.get("importance") is not None else 0.96))))
            updated_at = max(_now(), _timestamp(item.get("updated_at")))

            self.conn.execute(
                """
                UPDATE memories SET subject=?, kind=?, text=?, tags=?, source_type=?, source_ref=?,
                    authority=?, confidence=?, importance=?, updated_at=?, active=1
                WHERE id=?
                """,
                (
                    subject, kind, text, tags, source_type, source_ref,
                    authority, confidence, importance, updated_at, memory_id,
                ),
            )
            self._sync_memory_fts(memory_id, text, tags, subject)
            self.conn.commit()
            return True

'''

if "def replace_memory(self, memory_id: str, expected_old_text: str" not in memory:
    anchor = "    @staticmethod\n    def _fts_query(query: str) -> str:\n"
    if anchor not in memory:
        raise SystemExit("v0.11.7.52 MemoryWorker replace-method anchor missing")
    memory = memory.replace(anchor, replace_method + anchor, 1)

replace_route = r'''            if path == "/replace":
                item = payload.get("memory") if isinstance(payload.get("memory"), dict) else {}
                replaced = DB.replace_memory(
                    _clean(payload.get("memory_id"), 200),
                    _clean(payload.get("expected_old_text"), 24000),
                    item,
                    default_source=_clean(payload.get("source"), 120) or "user-explicit-correction",
                )
                self._json(200, {"ok": True, "replaced": bool(replaced), "stats": DB.stats()})
                return
'''
if 'if path == "/replace":' not in memory:
    route_anchor = '            if path == "/episode":\n'
    if route_anchor not in memory:
        raise SystemExit("v0.11.7.52 MemoryWorker replace-route anchor missing")
    memory = memory.replace(route_anchor, replace_route + route_anchor, 1)

start = bridge.find("def _explicit_memory_replace(new_fact: str, old_value: str) -> tuple[bool, str | None]:")
end = bridge.find("\n\ndef _personal_memory_fact_question", start)
if start < 0 or end < 0:
    raise SystemExit("v0.11.7.52 Bridge correction helper anchors missing")

new_helper = r'''def _explicit_memory_replace(new_fact: str, old_value: str) -> tuple[bool, str | None]:
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
        memory_id = str(item.get("id") or "").strip()
        if not memory_id or old_fold not in old_text.casefold():
            continue
        if str(item.get("kind") or "") != "explicit_user_memory":
            continue
        old_tokens = set(re.findall(r"[a-z0-9][a-z0-9_-]+", old_text.casefold()))
        overlap = len(new_tokens & old_tokens)
        candidates.append((overlap, float(item.get("updated_at") or 0.0), memory_id, old_text))
    if not candidates:
        return False, None
    candidates.sort(reverse=True)
    memory_id, old_text = candidates[0][2], candidates[0][3]

    now = time.time()
    result = _memory_post(
        "/replace",
        {
            "memory_id": memory_id,
            "expected_old_text": old_text,
            "memory": {
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
            },
            "source": "user-explicit-correction",
        },
        timeout=4.0,
    )
    if not isinstance(result, dict) or result.get("ok") is not True or result.get("replaced") is not True:
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
bridge = bridge[:start] + new_helper + bridge[end:]

for marker in [
    '"agent_runtime_bundle": "0.11.7.52"',
    '"explicit-personal-memory-correction-v11752"',
    '"memory_id": memory_id',
    '"/replace"',
]:
    if marker not in bridge:
        raise SystemExit(f"v0.11.7.52 Bridge row-replace marker missing: {marker}")
for marker in [
    "def replace_memory(self, memory_id: str, expected_old_text: str",
    'if path == "/replace":',
    '"replaced": bool(replaced)',
]:
    if marker not in memory:
        raise SystemExit(f"v0.11.7.52 MemoryWorker row-replace marker missing: {marker}")

BRIDGE.write_text(bridge, encoding="utf-8")
MEMORY.write_text(memory, encoding="utf-8")
compile(bridge, str(BRIDGE), "exec")
compile(memory, str(MEMORY), "exec")
print("Applied v0.11.7.52 exact-row memory correction hotfix")
