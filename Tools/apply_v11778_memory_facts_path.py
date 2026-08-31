#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

bridge_path = Path("Bridge/vex_bridge.py")
installer_path = Path("Tools/VexAgentRuntimeInstall.py")
worker_path = Path("Tools/VexMemoryWorker.py")

bridge = bridge_path.read_text(encoding="utf-8")
installer = installer_path.read_text(encoding="utf-8")
worker = worker_path.read_text(encoding="utf-8")

# Field diagnosis for .77 found a protocol mismatch: Bridge recall calls POST /facts,
# while the packaged MemoryWorker only implemented /search, /sync, /import and /episode.
# .78 repairs the worker contract and also heals legacy/stale FTS indexes at startup.

# ---------------------------------------------------------------------------
# 1) Backfill existing SQLite rows into FTS so upgrades do not require reimporting
#    the user's persistent memory database.
# ---------------------------------------------------------------------------
fts_anchor = '''            except sqlite3.OperationalError:\n                self.fts_available = False\n            c.commit()\n'''
fts_replacement = '''            except sqlite3.OperationalError:\n                self.fts_available = False\n            if self.fts_available:\n                # Heal databases created by older builds where authoritative rows\n                # can exist in memories while their FTS shadow rows are absent.\n                c.execute(\n                    "DELETE FROM memories_fts WHERE memory_id NOT IN (SELECT id FROM memories WHERE active=1)"\n                )\n                c.execute(\n                    """\n                    INSERT INTO memories_fts(memory_id, text, tags, subject)\n                    SELECT m.id, m.text, m.tags, m.subject\n                    FROM memories m\n                    WHERE m.active=1\n                      AND NOT EXISTS (SELECT 1 FROM memories_fts f WHERE f.memory_id=m.id)\n                    """\n                )\n                c.execute(\n                    "DELETE FROM episodes_fts WHERE episode_id NOT IN (SELECT id FROM episodes)"\n                )\n                c.execute(\n                    """\n                    INSERT INTO episodes_fts(episode_id, text)\n                    SELECT e.id, e.text\n                    FROM episodes e\n                    WHERE NOT EXISTS (SELECT 1 FROM episodes_fts f WHERE f.episode_id=e.id)\n                    """\n                )\n            c.commit()\n'''
if fts_anchor not in worker:
    raise SystemExit("v0.11.7.78 memory FTS setup anchor missing")
worker = worker.replace(fts_anchor, fts_replacement, 1)

# ---------------------------------------------------------------------------
# 2) Expose the authoritative /facts contract already used by Bridge recall.
#    Facts come only from persistent memories, never conversational episodes.
# ---------------------------------------------------------------------------
search_anchor = '''        return {"memories": memories, "episodes": episodes}\n\n    def stats(self) -> dict[str, Any]:\n'''
facts_method = '''        return {"memories": memories, "episodes": episodes}\n\n    def facts(self, query: str, limit: int = 8) -> list[dict[str, Any]]:\n        result = self.search(\n            query,\n            memory_limit=max(1, min(40, int(limit))),\n            episode_limit=0,\n        )\n        memories = result.get("memories") if isinstance(result, dict) else []\n        if not isinstance(memories, list):\n            return []\n        facts: list[dict[str, Any]] = []\n        for item in memories:\n            if not isinstance(item, dict):\n                continue\n            # Keep grounded recall on high-authority, high-confidence records.\n            # Canonical Star profile/rules are well above these thresholds.\n            try:\n                authority = int(item.get("authority") or 0)\n                confidence = float(item.get("confidence") or 0.0)\n            except Exception:\n                continue\n            if authority < 80 or confidence < 0.80:\n                continue\n            facts.append(item)\n            if len(facts) >= max(1, min(40, int(limit))):\n                break\n        return facts\n\n    def stats(self) -> dict[str, Any]:\n'''
if search_anchor not in worker:
    raise SystemExit("v0.11.7.78 memory search/stats anchor missing")
worker = worker.replace(search_anchor, facts_method, 1)

post_anchor = '''            if path == "/search":\n                query = _clean(payload.get("query"), 5000)\n                result = DB.search(\n                    query,\n                    memory_limit=int(payload.get("memory_limit") or 8),\n                    episode_limit=int(payload.get("episode_limit") or 4),\n                )\n                self._json(200, {"ok": True, **result, "stats": DB.stats()})\n                return\n            if path == "/sync":\n'''
post_replacement = '''            if path == "/search":\n                query = _clean(payload.get("query"), 5000)\n                result = DB.search(\n                    query,\n                    memory_limit=int(payload.get("memory_limit") or 8),\n                    episode_limit=int(payload.get("episode_limit") or 4),\n                )\n                self._json(200, {"ok": True, **result, "stats": DB.stats()})\n                return\n            if path == "/facts":\n                query = _clean(payload.get("query"), 5000)\n                facts = DB.facts(query, limit=int(payload.get("limit") or 8))\n                self._json(200, {"ok": True, "facts": facts, "stats": DB.stats()})\n                return\n            if path == "/sync":\n'''
if post_anchor not in worker:
    raise SystemExit("v0.11.7.78 memory POST routing anchor missing")
worker = worker.replace(post_anchor, post_replacement, 1)

worker = worker.replace('VERSION = "0.11.0"', 'VERSION = "0.11.1"', 1)

# ---------------------------------------------------------------------------
# 3) Advance cumulative Agent Runtime identity; Bridge protocol itself stays .39.
# ---------------------------------------------------------------------------
if '"agent_runtime_bundle": "0.11.7.77"' not in bridge:
    raise SystemExit("v0.11.7.78 expected .77 Bridge bundle identity missing")
bridge = bridge.replace('"agent_runtime_bundle": "0.11.7.77"', '"agent_runtime_bundle": "0.11.7.78"', 1)
if 'BUNDLE_VERSION = "0.11.7.77"' not in installer:
    raise SystemExit("v0.11.7.78 expected .77 installer identity missing")
installer = installer.replace('BUNDLE_VERSION = "0.11.7.77"', 'BUNDLE_VERSION = "0.11.7.78"', 1)
installer = installer.replace('Vex Agent Runtime v0.11.7.77', 'Vex Agent Runtime v0.11.7.78')

bridge_path.write_text(bridge, encoding="utf-8")
installer_path.write_text(installer, encoding="utf-8")
worker_path.write_text(worker, encoding="utf-8")

compile(bridge, str(bridge_path), "exec")
compile(installer, str(installer_path), "exec")
compile(worker, str(worker_path), "exec")

checks = [
    ('bundle identity', '"agent_runtime_bundle": "0.11.7.78"' in bridge),
    ('installer identity', 'BUNDLE_VERSION = "0.11.7.78"' in installer),
    ('worker version', 'VERSION = "0.11.1"' in worker),
    ('facts method', 'def facts(self, query: str, limit: int = 8)' in worker),
    ('facts endpoint', 'if path == "/facts":' in worker),
    ('facts payload', '"facts": facts' in worker),
    ('memory fts repair', 'INSERT INTO memories_fts(memory_id, text, tags, subject)' in worker),
    ('episode fts repair', 'INSERT INTO episodes_fts(episode_id, text)' in worker),
    ('star recall caller preserved', 'pc-memory-star-query-v11775' in bridge),
    ('window broker preserved', 'def _v11777_window_action(' in bridge),
]
missing = [name for name, ok in checks if not ok]
if missing:
    raise SystemExit("v0.11.7.78 verifier failed: " + ", ".join(missing))

print("Applied v0.11.7.78 MemoryWorker /facts + FTS repair")
