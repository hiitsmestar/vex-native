#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
MEMORY = Path("Tools/VexMemoryWorker.py")
bridge = BRIDGE.read_text(encoding="utf-8")
memory = MEMORY.read_text(encoding="utf-8")

# v0.11.7.52 recall hotfix:
# 1) expose the authoritative MemoryWorker /facts route the Bridge recall code expects;
# 2) restore direct factual personal-question classification that v0.11.7.2 narrowed too far;
# 3) restore the reply-variant globals used by the natural verified-memory formatter.

facts_method = r'''
    def facts(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        query = _clean(query, 5000)
        limit = max(1, min(30, int(limit or 8)))
        if query:
            result = self.search(query, memory_limit=limit, episode_limit=0)
            rows = result.get("memories") if isinstance(result, dict) else []
            return rows if isinstance(rows, list) else []

        with self.lock:
            rows = self.conn.execute(
                """
                SELECT * FROM memories
                WHERE active=1
                ORDER BY authority DESC, importance DESC, confidence DESC, updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [{
                "id": row["id"],
                "subject": row["subject"],
                "kind": row["kind"],
                "text": row["text"],
                "tags": row["tags"],
                "source_type": row["source_type"],
                "source_ref": row["source_ref"],
                "authority": row["authority"],
                "confidence": row["confidence"],
                "importance": row["importance"],
                "updated_at": row["updated_at"],
            } for row in rows]

'''
if "def facts(self, query: str, limit: int = 8)" not in memory:
    anchor = "    @staticmethod\n    def _fts_query(query: str) -> str:\n"
    if anchor not in memory:
        raise SystemExit("v0.11.7.52 recall hotfix MemoryWorker facts-method anchor missing")
    memory = memory.replace(anchor, facts_method + anchor, 1)

facts_route = r'''            if path == "/facts":
                query = _clean(payload.get("query"), 5000)
                try:
                    limit = int(payload.get("limit") or 8)
                except Exception:
                    limit = 8
                self._json(200, {"ok": True, "facts": DB.facts(query, limit)})
                return
'''
if 'if path == "/facts":' not in memory:
    route_anchor = '            if path == "/replace":\n'
    if route_anchor not in memory:
        route_anchor = '            if path == "/episode":\n'
    if route_anchor not in memory:
        raise SystemExit("v0.11.7.52 recall hotfix MemoryWorker facts-route anchor missing")
    memory = memory.replace(route_anchor, facts_route + route_anchor, 1)

# v0.11.7.3's natural verified-memory formatter calls _next_memory_reply_variant().
# Some later patch-chain replacements retained that function but dropped its module-level
# lock/counter declarations. Restore them without touching formatter semantics.
if "_MEMORY_REPLY_VARIANT_LOCK = threading.Lock()" not in bridge:
    variant_anchor = "def _next_memory_reply_variant() -> int:\n"
    if variant_anchor not in bridge:
        raise SystemExit("v0.11.7.52 recall hotfix reply-variant function missing")
    bridge = bridge.replace(
        variant_anchor,
        "_MEMORY_REPLY_VARIANT_LOCK = threading.Lock()\n_MEMORY_REPLY_VARIANT = 0\n\n\n" + variant_anchor,
        1,
    )
elif "_MEMORY_REPLY_VARIANT = 0" not in bridge:
    lock_anchor = "_MEMORY_REPLY_VARIANT_LOCK = threading.Lock()\n"
    bridge = bridge.replace(lock_anchor, lock_anchor + "_MEMORY_REPLY_VARIANT = 0\n", 1)

classifier_start = bridge.find("def _personal_memory_fact_question(message: str) -> bool:")
classifier_end = bridge.find("\n\ndef ", classifier_start + 5)
if classifier_start < 0 or classifier_end < 0:
    raise SystemExit("v0.11.7.52 recall hotfix personal-memory classifier missing")

classifier = r'''def _personal_memory_fact_question(message: str) -> bool:
    if _explicit_memory_correction_value(message) is not None:
        return False
    if _explicit_memory_write_value(message) is not None:
        return False

    normalized = str(message or "").lower().replace("’", "'")
    lower = " " + re.sub(r"[^a-z0-9']+", " ", normalized).strip() + " "
    if not lower.strip():
        return False

    recall_words = (
        " remember ", " remembered ", " memory ", " memories ",
        " know about me ", " know about us ", " know me ",
        " tell me what you know ", " tell me about me ",
    )
    personal_words = (
        " me ", " my ", " us ", " our ", " relationship ",
        " girlfriend ", " star ",
    )
    if any(word in lower for word in recall_words) and any(word in lower for word in personal_words):
        return True

    advice_words = (
        " should ", " could ", " would ", " can you ", " help me ", " recommend ",
        " suggest ", " plan ", " want to ", " need to ", " going to ", " tonight ",
        " tomorrow ", " next ", " best way ", " how do i ", " what should ",
    )
    if any(word in lower for word in advice_words):
        return False

    if not any(word in lower for word in (" my ", " me ", " our ", " us ")):
        return False

    fact_question_starts = (
        " what ", " which ", " where ", " who ", " when ", " describe ", " tell me ",
        " do you know ", " do i ", " am i ", " have i ", " did i ",
    )
    if not any(token in lower for token in fact_question_starts):
        return False

    factual_cues = (
        " color ", " hair ", " style ", " wear ", " look ", " appearance ", " home ",
        " house ", " live ", " name ", " named ", " called ", " age ", " height ", " size ",
        " favorite ", " prefer ", " preference ", " relationship ", " girlfriend ", " family ",
        " pet ", " pets ", " animal ", " animals ", " music ", " clothes ", " clothing ",
        " piercings ", " tattoos ", " nails ", " voice ", " work ", " project ", " vexnative ",
    )
    return any(cue in lower for cue in factual_cues)
'''
bridge = bridge[:classifier_start] + classifier + bridge[classifier_end:]

for marker in [
    '"agent_runtime_bundle": "0.11.7.52"',
    "def _personal_memory_fact_question(message: str) -> bool:",
    '" named "',
    'if _explicit_memory_correction_value(message) is not None:',
    'if _explicit_memory_write_value(message) is not None:',
    "_MEMORY_REPLY_VARIANT_LOCK = threading.Lock()",
    "_MEMORY_REPLY_VARIANT = 0",
]:
    if marker not in bridge:
        raise SystemExit(f"v0.11.7.52 recall Bridge marker missing: {marker}")
for marker in [
    "def facts(self, query: str, limit: int = 8)",
    'if path == "/facts":',
    '"facts": DB.facts(query, limit)',
    'if path == "/replace":',
]:
    if marker not in memory:
        raise SystemExit(f"v0.11.7.52 recall MemoryWorker marker missing: {marker}")

BRIDGE.write_text(bridge, encoding="utf-8")
MEMORY.write_text(memory, encoding="utf-8")
compile(bridge, str(BRIDGE), "exec")
compile(memory, str(MEMORY), "exec")
print("Applied v0.11.7.52 authoritative personal-memory recall hotfix")
