#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

MEMORY = Path("Tools/VexMemoryWorker.py")
BRIDGE = Path("Bridge/vex_bridge.py")
INSTALLER = Path("Tools/VexAgentRuntimeInstall.py")

mem = MEMORY.read_text(encoding="utf-8")
bridge = BRIDGE.read_text(encoding="utf-8")
installer = INSTALLER.read_text(encoding="utf-8")

# v0.11.7.78 fixes the field failure where /facts had a valid canonical
# core:star:profile row but recall_facts() discarded most/all of its contents.
# The old extractor split only on sentence punctuation, rejected chunks >420
# chars, and (for subject=star) required every returned sentence to literally
# contain the word "star". Real private profiles are commonly line-oriented and
# do not repeat the owner's name on every line.
# Workflow registration trigger: authoritative-memory field repair.

if 'VERSION = "0.11.2"' in mem:
    mem = mem.replace('VERSION = "0.11.2"', 'VERSION = "0.11.2.1"', 1)
elif 'VERSION = "0.11.2.1"' not in mem:
    raise SystemExit("v0.11.7.78 expected verified-memory worker v0.11.2")

start = mem.find("    def recall_facts(self, query: str, limit: int = 6) -> list[dict[str, Any]]:")
end = mem.find("    def stats(self) -> dict[str, Any]:", start)
if start < 0 or end < 0:
    raise SystemExit("v0.11.7.78 could not bound recall_facts")

replacement = r'''    @staticmethod
    def _v11778_profile_chunks(text_value: str) -> list[str]:
        """Split authoritative profile text without losing line-oriented facts."""
        raw = str(text_value or "").replace("\r\n", "\n").replace("\r", "\n")
        pieces = re.split(r"\n+|(?<=[.!?])\s+|\s+[•▪◦]\s+", raw)
        out: list[str] = []
        for piece in pieces:
            piece = re.sub(r"^[\s\-*•▪◦]+", "", piece)
            piece = re.sub(r"\s+", " ", piece).strip()
            if not piece:
                continue
            subparts = [piece]
            if len(piece) > 420:
                subparts = re.split(r"\s*(?:;|\|)\s*", piece)
            for part in subparts:
                part = re.sub(r"\s+", " ", part).strip()
                if 8 <= len(part) <= 420:
                    out.append(part)
        return out

    def recall_facts(self, query: str, limit: int = 6) -> list[dict[str, Any]]:
        """Return trusted Star facts from authoritative personal-memory records.

        Ownership is established by canonical_key/subject, not by requiring each
        individual line of a Star profile to repeat the literal word "Star".
        Raw chat episodes, teaching examples and behavioral rules remain excluded.
        """
        query = _clean(query, 5000)
        low = query.lower()
        query_tokens = {
            token for token in re.findall(r"[a-z0-9][a-z0-9_'-]{1,}", low)
            if token not in {
                "the", "and", "for", "with", "that", "this", "what", "who", "are", "you", "your",
                "about", "right", "now", "tell", "me", "things", "thing", "specific", "factual", "actually",
                "remember", "remembered", "memory", "memories", "know", "known", "our", "us"
            }
        }
        kinds = ("identity", "preference", "appearance", "profile", "relationship", "project", "continuity", "hardware")
        placeholders = ",".join("?" for _ in kinds)
        with self.lock:
            rows = self.conn.execute(
                f"""
                SELECT * FROM memories
                WHERE active=1
                  AND (canonical_key='core:star:profile' OR subject IN ('star','vex-star'))
                  AND kind IN ({placeholders})
                  AND authority >= 70
                  AND confidence >= 0.70
                ORDER BY
                  CASE WHEN canonical_key='core:star:profile' THEN 0 ELSE 1 END,
                  authority DESC, importance DESC, confidence DESC, updated_at DESC
                LIMIT 100
                """,
                kinds,
            ).fetchall()

        kind_weight = {
            "identity": 8.0,
            "preference": 7.4,
            "appearance": 7.1,
            "relationship": 7.0,
            "profile": 7.2,
            "project": 5.8,
            "hardware": 5.5,
            "continuity": 4.8,
        }
        wants_us = any(token in low for token in [" us", "our ", "relationship", "girlfriend", "together"])
        candidates: list[tuple[float, dict[str, Any]]] = []
        seen: set[str] = set()
        for row in rows:
            text_value = str(row["text"] or "").strip()
            if not text_value:
                continue
            chunks = self._v11778_profile_chunks(text_value)
            for sentence in chunks:
                lower_sentence = sentence.lower()
                if lower_sentence.startswith((
                    "address the user", "never ", "do not ", "don't ", "treat ", "preserve ",
                    "teaching example", "vex should ", "when star ", "if star ", "questions like ",
                    "you are vex", "speak in first person", "keep the relationship voice"
                )):
                    continue
                key = re.sub(r"[^a-z0-9]+", " ", lower_sentence).strip()
                if not key or key in seen:
                    continue
                seen.add(key)
                score = kind_weight.get(str(row["kind"]), 4.0)
                score += float(row["importance"] or 0) * 1.8
                score += float(row["confidence"] or 0) * 1.3
                score += float(row["authority"] or 0) / 100.0
                if str(row["canonical_key"]) == "core:star:profile":
                    score += 3.0
                if wants_us and str(row["kind"]) == "relationship":
                    score += 3.0
                if query_tokens:
                    words = set(re.findall(r"[a-z0-9][a-z0-9_'-]{1,}", lower_sentence))
                    score += len(query_tokens & words) * 2.4
                candidates.append((score, {
                    "text": sentence,
                    "kind": str(row["kind"]),
                    "subject": str(row["subject"]),
                    "canonical_key": str(row["canonical_key"]),
                    "source_type": str(row["source_type"]),
                    "source_ref": str(row["source_ref"]),
                    "authority": int(row["authority"]),
                    "confidence": float(row["confidence"]),
                }))

        candidates.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in candidates[:max(1, min(32, int(limit)))]]

'''
mem = mem[:start] + replacement + mem[end:]

setup_anchor = '''            except sqlite3.OperationalError:\n                self.fts_available = False\n            c.commit()\n'''
setup_repair = '''            except sqlite3.OperationalError:\n                self.fts_available = False\n            if self.fts_available:\n                memory_rows = int(c.execute("SELECT COUNT(*) FROM memories WHERE active=1").fetchone()[0])\n                memory_fts_rows = int(c.execute("SELECT COUNT(*) FROM memories_fts").fetchone()[0])\n                if memory_fts_rows != memory_rows:\n                    c.execute("DELETE FROM memories_fts")\n                    c.execute(\n                        "INSERT INTO memories_fts(memory_id,text,tags,subject) "\n                        "SELECT id,text,tags,subject FROM memories WHERE active=1"\n                    )\n                episode_rows = int(c.execute("SELECT COUNT(*) FROM episodes").fetchone()[0])\n                episode_fts_rows = int(c.execute("SELECT COUNT(*) FROM episodes_fts").fetchone()[0])\n                if episode_fts_rows != episode_rows:\n                    c.execute("DELETE FROM episodes_fts")\n                    c.execute(\n                        "INSERT INTO episodes_fts(episode_id,text) SELECT id,text FROM episodes"\n                    )\n            c.commit()\n'''
if setup_anchor in mem:
    mem = mem.replace(setup_anchor, setup_repair, 1)
elif 'memory_fts_rows != memory_rows' not in mem:
    raise SystemExit("v0.11.7.78 memory FTS repair anchor missing")

facts_old = '''                facts = DB.recall_facts(query, limit=int(payload.get("limit") or 6))\n                self._json(200, {"ok": True, "facts": facts, "stats": DB.stats()})\n                return\n'''
facts_new = '''                facts = DB.recall_facts(query, limit=int(payload.get("limit") or 6))\n                self._json(200, {\n                    "ok": True,\n                    "facts": facts,\n                    "fact_count": len(facts),\n                    "extractor": "authoritative-profile-v11778",\n                    "stats": DB.stats(),\n                })\n                return\n'''
if facts_old in mem:
    mem = mem.replace(facts_old, facts_new, 1)
elif '"extractor": "authoritative-profile-v11778"' not in mem:
    raise SystemExit("v0.11.7.78 /facts diagnostics anchor missing")

bridge = bridge.replace('"agent_runtime_bundle": "0.11.7.77"', '"agent_runtime_bundle": "0.11.7.78"')
installer = installer.replace('BUNDLE_VERSION = "0.11.7.77"', 'BUNDLE_VERSION = "0.11.7.78"')
installer = installer.replace('Vex Agent Runtime v0.11.7.77', 'Vex Agent Runtime v0.11.7.78')

MEMORY.write_text(mem, encoding="utf-8")
BRIDGE.write_text(bridge, encoding="utf-8")
INSTALLER.write_text(installer, encoding="utf-8")
compile(mem, str(MEMORY), "exec")
compile(bridge, str(BRIDGE), "exec")
compile(installer, str(INSTALLER), "exec")

checks = [
    ("worker identity", 'VERSION = "0.11.2.1"' in mem),
    ("profile chunker", "def _v11778_profile_chunks(" in mem),
    ("canonical ownership", "canonical_key='core:star:profile'" in mem),
    ("no literal Star requirement", 'and "star" not in lower_sentence' not in mem),
    ("FTS self repair", "memory_fts_rows != memory_rows" in mem),
    ("fact diagnostics", '"extractor": "authoritative-profile-v11778"' in mem),
    ("bundle identity", '"agent_runtime_bundle": "0.11.7.78"' in bridge),
    ("installer identity", 'BUNDLE_VERSION = "0.11.7.78"' in installer),
    ("window broker preserved", 'parsed.path == "/windows/window-action"' in bridge),
    ("app broker preserved", 'parsed.path == "/windows/apps"' in bridge),
    ("recall routing preserved", "pc-memory-star-query-v11775" in bridge),
]
missing = [name for name, ok in checks if not ok]
if missing:
    raise SystemExit("v0.11.7.78 verifier failed: " + ", ".join(missing))

print("Applied v0.11.7.78 authoritative Star profile extraction + memory index repair")
