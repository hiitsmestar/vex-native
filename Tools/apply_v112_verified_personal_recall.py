#!/usr/bin/env python3
from pathlib import Path

# v0.11.2 fixes two field-test problems:
# 1) generic recall prompts such as "tell me three things you remember about me"
#    contain almost no keywords that overlap the stored facts, so pure FTS can
#    return weak/empty context and a 1.7B model improvises.
# 2) long CPU generations had no per-turn timing telemetry.

# ---------------------------------------------------------------------------
# Memory worker: add authoritative fact extraction endpoint.
# ---------------------------------------------------------------------------
mem_path = Path("Tools/VexMemoryWorker.py")
mem = mem_path.read_text(encoding="utf-8")

mem = mem.replace('VERSION = "0.11.0"', 'VERSION = "0.11.2"', 1)

facts_method_marker = '''    def stats(self) -> dict[str, Any]:
'''
facts_method = r'''    def recall_facts(self, query: str, limit: int = 6) -> list[dict[str, Any]]:
        """Return small authoritative fact sentences for explicit memory questions.

        This deliberately excludes raw chat episodes, teaching examples, and rule
        text. Old model prose is historical context, not a fact source.
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
                  AND subject IN ('star','vex-star')
                  AND kind IN ({placeholders})
                  AND authority >= 70
                  AND confidence >= 0.70
                ORDER BY authority DESC, importance DESC, confidence DESC, updated_at DESC
                LIMIT 80
                """,
                kinds,
            ).fetchall()

        kind_weight = {
            "identity": 8.0,
            "preference": 7.4,
            "appearance": 7.1,
            "relationship": 7.0,
            "profile": 6.4,
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
            # Split large profile blobs into atomic-ish sentences so a recall answer
            # does not have to hand a tiny model a 2k paragraph and hope it behaves.
            sentences = re.split(r"(?<=[.!?])\s+", text_value)
            for sentence in sentences:
                sentence = re.sub(r"\s+", " ", sentence).strip()
                if len(sentence) < 20 or len(sentence) > 420:
                    continue
                lower_sentence = sentence.lower()
                if lower_sentence.startswith((
                    "address the user", "never ", "do not ", "don't ", "treat ", "preserve ",
                    "teaching example", "vex should ", "when star ", "if star ", "questions like "
                )):
                    continue
                # Prefer statements actually about Star or the relationship.
                if row["subject"] == "star" and "star" not in lower_sentence:
                    continue
                key = re.sub(r"[^a-z0-9]+", " ", lower_sentence).strip()
                if not key or key in seen:
                    continue
                seen.add(key)
                score = kind_weight.get(str(row["kind"]), 4.0)
                score += float(row["importance"] or 0) * 1.8
                score += float(row["confidence"] or 0) * 1.3
                score += float(row["authority"] or 0) / 100.0
                if wants_us and str(row["kind"]) == "relationship":
                    score += 3.0
                if query_tokens:
                    words = set(re.findall(r"[a-z0-9][a-z0-9_'-]{1,}", lower_sentence))
                    score += len(query_tokens & words) * 2.4
                candidates.append((score, {
                    "text": sentence,
                    "kind": str(row["kind"]),
                    "subject": str(row["subject"]),
                    "source_type": str(row["source_type"]),
                    "source_ref": str(row["source_ref"]),
                    "authority": int(row["authority"]),
                    "confidence": float(row["confidence"]),
                }))

        candidates.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in candidates[:max(1, min(12, int(limit)))]]

'''
if "def recall_facts(" not in mem:
    if facts_method_marker not in mem:
        raise SystemExit("v0.11.2 recall_facts insertion marker missing")
    mem = mem.replace(facts_method_marker, facts_method + facts_method_marker, 1)

facts_route_marker = '''            if path == "/search":
'''
facts_route = r'''            if path == "/facts":
                query = _clean(payload.get("query"), 5000)
                facts = DB.recall_facts(query, limit=int(payload.get("limit") or 6))
                self._json(200, {"ok": True, "facts": facts, "stats": DB.stats()})
                return
            if path == "/search":
'''
if 'path == "/facts"' not in mem:
    if facts_route_marker not in mem:
        raise SystemExit("v0.11.2 /facts route marker missing")
    mem = mem.replace(facts_route_marker, facts_route, 1)

mem_path.write_text(mem, encoding="utf-8")
compile(mem, str(mem_path), "exec")

# ---------------------------------------------------------------------------
# Bridge: verified recall fast path + measured normal cognition.
# ---------------------------------------------------------------------------
bridge_path = Path("Bridge/vex_bridge.py")
text = bridge_path.read_text(encoding="utf-8")

helper_marker = '''def _memory_record_turn(message: str, reply: str) -> None:
'''
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
    model = _choose_ollama_model() or "pc-memory"
    lines = ["Baby, actual stored-memory answer — no glitter improv this time. 🖤"]
    for index, fact in enumerate(clean, 1):
        lines.append(f"{index}. {fact}")
    return "\n".join(lines), model


'''
if "def _personal_memory_fact_question(" not in text:
    if helper_marker not in text:
        raise SystemExit("v0.11.2 Bridge recall helper marker missing")
    text = text.replace(helper_marker, helper + helper_marker, 1)

# Insert the verified memory route immediately before normal context construction.
route_marker = '''                context = {
'''
route = '''                if _personal_memory_fact_question(message):
                    verified_memory = _verified_personal_memory_reply(message)
                    if verified_memory is not None:
                        reply, model = verified_memory
                        _memory_record_turn(message, reply)
                        self._json(200, {
                            "ok": True,
                            "reply": reply,
                            "model": model,
                            "grounding": "verified-personal-memory",
                            "memory": "persistent-pc",
                            "timing_ms": 0,
                        })
                        return
                context = {
'''
if '"grounding": "verified-personal-memory"' not in text:
    if route_marker not in text:
        raise SystemExit("v0.11.2 verified-memory route insertion marker missing")
    text = text.replace(route_marker, route, 1)

# Measure the expensive normal Ollama path so future field diagnostics can tell
# retrieval time from generation time instead of inferring from screenshots.
normal_old = '''                result = _ollama_chat(history, message, context=context)
                if result is None:
'''
normal_new = '''                cognition_started = time.perf_counter()
                result = _ollama_chat(history, message, context=context)
                cognition_ms = int((time.perf_counter() - cognition_started) * 1000)
                if result is None:
'''
if "cognition_started = time.perf_counter()" not in text:
    if normal_old not in text:
        raise SystemExit("v0.11.2 cognition timing start marker missing")
    text = text.replace(normal_old, normal_new, 1)

reply_old = '''                _memory_record_turn(message, reply)
                self._json(200, {"ok": True, "reply": reply, "model": model, "memory": "persistent-pc"})
'''
reply_new = '''                _memory_record_turn(message, reply)
                self._json(200, {
                    "ok": True,
                    "reply": reply,
                    "model": model,
                    "memory": "persistent-pc",
                    "timing_ms": cognition_ms,
                })
'''
if '"timing_ms": cognition_ms' not in text:
    if reply_old not in text:
        raise SystemExit("v0.11.2 cognition timing response marker missing")
    text = text.replace(reply_old, reply_new, 1)

bridge_path.write_text(text, encoding="utf-8")
compile(text, str(bridge_path), "exec")

for marker in [
    'VERSION = "0.11.2"',
    "def recall_facts(",
    'path == "/facts"',
    "def _personal_memory_fact_question(",
    '"grounding": "verified-personal-memory"',
    '"timing_ms": cognition_ms',
]:
    target = mem if marker in ['VERSION = "0.11.2"', "def recall_facts(", 'path == "/facts"'] else text
    if marker not in target:
        raise SystemExit(f"missing v0.11.2 marker: {marker}")

print("Applied v0.11.2 verified personal recall + cognition timing telemetry")
