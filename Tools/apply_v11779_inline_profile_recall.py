#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

bridge_path = Path("Bridge/vex_bridge.py")
installer_path = Path("Tools/VexAgentRuntimeInstall.py")
worker_path = Path("Tools/VexMemoryWorker.py")

bridge = bridge_path.read_text(encoding="utf-8")
installer = installer_path.read_text(encoding="utf-8")
worker = worker_path.read_text(encoding="utf-8")

# Field diagnosis after iPhone v0.11.7.51 + Agent Runtime v0.11.7.78:
# Remote Support proves MemoryWorker v0.11.3 is healthy and already contains
# hundreds of persistent rows. Broad Star recall still returned no trusted fact.
# Do not depend solely on FTS for canonical identity/profile records. For broad
# Star-oriented probes, read authoritative Star-subject rows directly first,
# then add ordinary FTS results. This preserves provenance while making the
# canonical core:star:profile record retrievable even if FTS ranking/indexing
# is imperfect on an existing field database.

old_facts = '''    def facts(self, query: str, limit: int = 8) -> list[dict[str, Any]]:\n        result = self.search(\n            query,\n            memory_limit=max(1, min(40, int(limit))),\n            episode_limit=0,\n        )\n        memories = result.get("memories") if isinstance(result, dict) else []\n        if not isinstance(memories, list):\n            return []\n        facts: list[dict[str, Any]] = []\n        for item in memories:\n            if not isinstance(item, dict):\n                continue\n            try:\n                authority = int(item.get("authority") or 0)\n                confidence = float(item.get("confidence") or 0.0)\n            except Exception:\n                continue\n            if authority < 80 or confidence < 0.80:\n                continue\n            facts.append(item)\n            if len(facts) >= max(1, min(40, int(limit))):\n                break\n        return facts\n'''

new_facts = '''    def facts(self, query: str, limit: int = 8) -> list[dict[str, Any]]:\n        cap = max(1, min(40, int(limit)))\n        query_clean = _clean(query, 5000).lower()\n        tokens = set(re.findall(r"[a-z0-9][a-z0-9_'-]{1,}", query_clean))\n        broad_star_tokens = {\n            "star", "profile", "preference", "preferences", "appearance",\n            "routine", "routines", "relationship", "favorite", "identity",\n            "personal", "remember", "memory",\n        }\n\n        facts: list[dict[str, Any]] = []\n        seen: set[str] = set()\n\n        def append_row(row: Any) -> None:\n            if row is None:\n                return\n            item = {\n                "id": row["id"],\n                "subject": row["subject"],\n                "kind": row["kind"],\n                "text": row["text"],\n                "tags": row["tags"],\n                "source_type": row["source_type"],\n                "source_ref": row["source_ref"],\n                "authority": row["authority"],\n                "confidence": row["confidence"],\n                "importance": row["importance"],\n                "updated_at": row["updated_at"],\n            }\n            key = str(item.get("id") or "")\n            if not key or key in seen:\n                return\n            try:\n                authority = int(item.get("authority") or 0)\n                confidence = float(item.get("confidence") or 0.0)\n            except Exception:\n                return\n            if authority < 80 or confidence < 0.80:\n                return\n            seen.add(key)\n            facts.append(item)\n\n        # Canonical personal identity/profile rows are authoritative structured\n        # memory, not fuzzy prose. Broad Star recall should not require FTS to\n        # rediscover their subject label. Prioritize them directly.\n        if tokens & broad_star_tokens:\n            with self.lock:\n                direct_rows = self.conn.execute(\n                    """\n                    SELECT * FROM memories\n                    WHERE active=1\n                      AND authority>=80\n                      AND confidence>=0.80\n                      AND (subject='star' OR canonical_key='core:star:profile')\n                    ORDER BY\n                      CASE WHEN canonical_key='core:star:profile' THEN 0 ELSE 1 END,\n                      importance DESC, confidence DESC, authority DESC, updated_at DESC\n                    LIMIT ?\n                    """,\n                    (cap,),\n                ).fetchall()\n            for row in direct_rows:\n                append_row(row)\n                if len(facts) >= cap:\n                    return facts\n\n        result = self.search(query, memory_limit=cap, episode_limit=0)\n        memories = result.get("memories") if isinstance(result, dict) else []\n        if isinstance(memories, list):\n            for item in memories:\n                if not isinstance(item, dict):\n                    continue\n                key = str(item.get("id") or "")\n                if not key or key in seen:\n                    continue\n                try:\n                    authority = int(item.get("authority") or 0)\n                    confidence = float(item.get("confidence") or 0.0)\n                except Exception:\n                    continue\n                if authority < 80 or confidence < 0.80:\n                    continue\n                seen.add(key)\n                facts.append(item)\n                if len(facts) >= cap:\n                    break\n        return facts\n'''

if old_facts not in worker:
    raise SystemExit("v0.11.7.79 expected v0.11.3 facts() implementation missing")
worker = worker.replace(old_facts, new_facts, 1)

if 'VERSION = "0.11.3"' not in worker:
    raise SystemExit("v0.11.7.79 expected MemoryWorker v0.11.3 identity missing")
worker = worker.replace('VERSION = "0.11.3"', 'VERSION = "0.11.4"', 1)

if '"agent_runtime_bundle": "0.11.7.78"' not in bridge:
    raise SystemExit("v0.11.7.79 expected .78 Bridge bundle identity missing")
bridge = bridge.replace('"agent_runtime_bundle": "0.11.7.78"', '"agent_runtime_bundle": "0.11.7.79"', 1)
if 'BUNDLE_VERSION = "0.11.7.78"' not in installer:
    raise SystemExit("v0.11.7.79 expected .78 installer identity missing")
installer = installer.replace('BUNDLE_VERSION = "0.11.7.78"', 'BUNDLE_VERSION = "0.11.7.79"', 1)
installer = installer.replace('Vex Agent Runtime v0.11.7.78', 'Vex Agent Runtime v0.11.7.79')

bridge_path.write_text(bridge, encoding="utf-8")
installer_path.write_text(installer, encoding="utf-8")
worker_path.write_text(worker, encoding="utf-8")

compile(bridge, str(bridge_path), "exec")
compile(installer, str(installer_path), "exec")
compile(worker, str(worker_path), "exec")

checks = [
    ('bundle identity', '"agent_runtime_bundle": "0.11.7.79"' in bridge),
    ('installer identity', 'BUNDLE_VERSION = "0.11.7.79"' in installer),
    ('worker version', 'VERSION = "0.11.4"' in worker),
    ('direct Star lookup', "subject='star' OR canonical_key='core:star:profile'" in worker),
    ('canonical priority', "canonical_key='core:star:profile' THEN 0" in worker),
    ('facts endpoint preserved', 'if path == "/facts":' in worker),
    ('Star recall caller preserved', 'pc-memory-star-query-v11775' in bridge),
    ('window broker preserved', 'def _v11777_window_action(' in bridge),
]
missing = [name for name, ok in checks if not ok]
if missing:
    raise SystemExit("v0.11.7.79 verifier failed: " + ", ".join(missing))

print("Applied v0.11.7.79 canonical Star profile direct-recall fallback")
