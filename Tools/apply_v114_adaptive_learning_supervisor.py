#!/usr/bin/env python3
from pathlib import Path

path = Path("Bridge/vex_bridge.py")
text = path.read_text(encoding="utf-8")

insert_marker = "def _vex_background_services() -> None:\n"
if insert_marker not in text:
    raise SystemExit("v0.11.4: background service marker missing")

adaptive = r'''
# ---------------------------------------------------------------------------
# v0.11.4 Adaptive Learning Supervisor
#
# Purpose:
# - learn from actual exchanges and corrections while the machine is idle
# - make retained behavior guidance available to normal cognition every turn
# - keep a persistent gap/repair queue for capabilities that need attention
# - coordinate background cognition so research/adaptation do not fight each other
#
# This is not arbitrary binary self-rewriting. Learned behavior is persistent data;
# executable skills still go through the existing validated skill compiler and known
# repairs still go through the existing repair/maintenance paths.
# ---------------------------------------------------------------------------
ADAPTIVE_ROOT = CONFIG_PATH.parent / "adaptive"
ADAPTIVE_DB = ADAPTIVE_ROOT / "vex-adaptive.sqlite3"
ADAPTIVE_IDLE_SECONDS = 150
ADAPTIVE_LOOP_SECONDS = 60
ADAPTIVE_REVIEW_MIN = 2
ADAPTIVE_REVIEW_MAX = 12
_BACKGROUND_COGNITION_LOCK = threading.Lock()
_ADAPTIVE_DB_LOCK = threading.RLock()
_ADAPTIVE_LAST_FOREGROUND = time.time()
_ADAPTIVE_LAST_REVIEW = 0.0


def _adaptive_conn():
    import sqlite3
    ADAPTIVE_ROOT.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(ADAPTIVE_DB), timeout=12, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS experience (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at REAL NOT NULL,
            user_text TEXT NOT NULL,
            assistant_text TEXT NOT NULL,
            route TEXT NOT NULL DEFAULT 'conversation',
            success INTEGER NOT NULL DEFAULT 1,
            reviewed INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            kind TEXT NOT NULL,
            cue TEXT NOT NULL,
            guidance TEXT NOT NULL,
            confidence REAL NOT NULL,
            evidence TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 0,
            hits INTEGER NOT NULL DEFAULT 0,
            UNIQUE(kind, cue, guidance)
        );
        CREATE TABLE IF NOT EXISTS gaps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            request_text TEXT NOT NULL,
            category TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            priority INTEGER NOT NULL DEFAULT 50,
            status TEXT NOT NULL DEFAULT 'open'
        );
        CREATE INDEX IF NOT EXISTS idx_adaptive_exp_reviewed ON experience(reviewed, id);
        CREATE INDEX IF NOT EXISTS idx_adaptive_lessons_active ON lessons(active, confidence, updated_at);
        CREATE INDEX IF NOT EXISTS idx_adaptive_gaps_status ON gaps(status, priority, updated_at);
        """
    )
    conn.commit()
    return conn


def _adaptive_route_guess(reply: str) -> tuple[str, int]:
    low = str(reply or "").lower()
    if "stored memory" in low or "stored-memory" in low:
        return "verified-memory", 1
    if "pc cognition node didn't answer" in low or "startup-safe mode" in low:
        return "fallback", 0
    if any(x in low for x in ["traceback", "internal error", "failed to", "timed out", "timeout"]):
        return "error", 0
    return "conversation", 1


def _adaptive_record_exchange(message: str, reply: str) -> None:
    global _ADAPTIVE_LAST_FOREGROUND
    _ADAPTIVE_LAST_FOREGROUND = time.time()
    user_text = str(message or "").strip()[:12000]
    assistant_text = str(reply or "").strip()[:12000]
    if not user_text and not assistant_text:
        return
    route, success = _adaptive_route_guess(assistant_text)
    try:
        with _ADAPTIVE_DB_LOCK:
            conn = _adaptive_conn()
            conn.execute(
                "INSERT INTO experience(created_at,user_text,assistant_text,route,success,reviewed) VALUES (?,?,?,?,?,0)",
                (time.time(), user_text, assistant_text, route, int(success)),
            )
            conn.execute("DELETE FROM experience WHERE id NOT IN (SELECT id FROM experience ORDER BY id DESC LIMIT 1200)")
            conn.commit()
            conn.close()
    except Exception as exc:
        print(f"[adaptive] record warning: {exc}", flush=True)


def _adaptive_tokens(value: str) -> set[str]:
    stop = {
        "the", "and", "for", "with", "that", "this", "what", "which", "where", "who", "when", "how",
        "are", "you", "your", "about", "tell", "me", "my", "i", "im", "i'm", "our", "us", "a", "an",
        "of", "to", "in", "on", "is", "it", "be", "do", "does", "did", "can", "could", "would", "should"
    }
    return {
        token for token in re.findall(r"[a-z0-9][a-z0-9_'-]{1,}", str(value or "").lower())
        if token not in stop
    }


def _adaptive_capability_snapshot() -> dict:
    caps = {
        "persistent_personal_memory": "_personal_memory_grounding" in globals(),
        "source_grounded_idle_research": "_learning_worker_loop" in globals(),
        "validated_skill_compiler": "compile_and_execute_skill" in globals(),
        "self_repair_supervisor": "_sr_supervisor_loop" in globals(),
        "art_worker": "_art_status" in globals() or "_art_health" in globals(),
        "local_pc_cognition": "_ollama_chat" in globals(),
    }
    try:
        caps["skill_primitives"] = sorted(list(SAFE_SKILL_PRIMITIVES))[:20]
    except Exception:
        caps["skill_primitives"] = []
    try:
        caps["pc_tool_actions"] = list(PC_TOOL_ACTIONS)[:30]
    except Exception:
        caps["pc_tool_actions"] = []
    return caps


def _adaptive_store_lesson(kind: str, cue: str, guidance: str, confidence: float, evidence: str = "") -> bool:
    kind = re.sub(r"[^a-z0-9_-]", "", str(kind or "").lower())[:40] or "behavior"
    cue = re.sub(r"\s+", " ", str(cue or "")).strip()[:500]
    guidance = re.sub(r"\s+", " ", str(guidance or "")).strip()[:1200]
    evidence = re.sub(r"\s+", " ", str(evidence or "")).strip()[:500]
    try:
        confidence = max(0.0, min(1.0, float(confidence)))
    except Exception:
        confidence = 0.0
    if len(cue) < 3 or len(guidance) < 12 or confidence < 0.60:
        return False
    active = 1 if confidence >= 0.78 else 0
    now = time.time()
    try:
        with _ADAPTIVE_DB_LOCK:
            conn = _adaptive_conn()
            conn.execute(
                """INSERT INTO lessons(created_at,updated_at,kind,cue,guidance,confidence,evidence,active,hits)
                   VALUES (?,?,?,?,?,?,?,?,0)
                   ON CONFLICT(kind,cue,guidance) DO UPDATE SET
                     updated_at=excluded.updated_at,
                     confidence=MAX(confidence,excluded.confidence),
                     evidence=CASE WHEN excluded.evidence<>'' THEN excluded.evidence ELSE evidence END,
                     active=MAX(active,excluded.active)""",
                (now, now, kind, cue, guidance, confidence, evidence, active),
            )
            conn.commit()
            conn.close()
        return True
    except Exception as exc:
        print(f"[adaptive] lesson warning: {exc}", flush=True)
        return False


def _adaptive_open_gap(request_text: str, category: str, detail: str, priority: int = 60) -> None:
    request_text = re.sub(r"\s+", " ", str(request_text or "")).strip()[:1200]
    category = re.sub(r"[^a-z0-9_-]", "", str(category or "").lower())[:40] or "capability"
    detail = re.sub(r"\s+", " ", str(detail or "")).strip()[:1200]
    if len(request_text) < 4:
        return
    now = time.time()
    try:
        with _ADAPTIVE_DB_LOCK:
            conn = _adaptive_conn()
            recent = conn.execute(
                "SELECT id FROM gaps WHERE status='open' AND request_text=? AND category=? ORDER BY id DESC LIMIT 1",
                (request_text, category),
            ).fetchone()
            if recent is None:
                conn.execute(
                    "INSERT INTO gaps(created_at,updated_at,request_text,category,detail,priority,status) VALUES (?,?,?,?,?,?, 'open')",
                    (now, now, request_text, category, detail, int(priority)),
                )
            else:
                conn.execute(
                    "UPDATE gaps SET updated_at=?, detail=?, priority=MAX(priority,?) WHERE id=?",
                    (now, detail, int(priority), int(recent["id"])),
                )
            conn.commit()
            conn.close()
    except Exception as exc:
        print(f"[adaptive] gap warning: {exc}", flush=True)

    # Existing source-grounded learning engine researches unresolved capability gaps.
    try:
        _learning_queue_topic(request_text, reason="adaptive-gap", priority=max(45, min(90, int(priority))))
    except Exception:
        pass


def _adaptive_context(message: str) -> str:
    query_tokens = _adaptive_tokens(message)
    lines = [
        "ADAPTIVE LOCAL CAPABILITY CONTEXT",
        "Use these learned behavior/procedure notes naturally. They are not user facts and must not override explicit current instructions.",
    ]
    caps = _adaptive_capability_snapshot()
    enabled = [name for name, value in caps.items() if value is True]
    if enabled:
        lines.append("Available local systems: " + ", ".join(enabled) + ".")
    if caps.get("skill_primitives"):
        lines.append("Validated skill primitives: " + ", ".join(caps["skill_primitives"]) + ".")

    try:
        with _ADAPTIVE_DB_LOCK:
            conn = _adaptive_conn()
            rows = conn.execute(
                "SELECT id,kind,cue,guidance,confidence,hits,updated_at FROM lessons WHERE active=1 ORDER BY confidence DESC, updated_at DESC LIMIT 80"
            ).fetchall()
            scored = []
            for row in rows:
                lesson_tokens = _adaptive_tokens(str(row["cue"]) + " " + str(row["guidance"]))
                overlap = len(query_tokens & lesson_tokens)
                score = overlap * 8.0 + float(row["confidence"] or 0) * 2.0
                if str(row["kind"]) in {"conversation", "preference", "naturalness"}:
                    score += 0.5
                if query_tokens and overlap == 0 and score < 2.2:
                    continue
                scored.append((score, row))
            scored.sort(key=lambda pair: pair[0], reverse=True)
            selected = [row for _, row in scored[:6]]
            for row in selected:
                lines.append(f"[{row['kind']}] {row['guidance']}")
                conn.execute("UPDATE lessons SET hits=hits+1 WHERE id=?", (int(row["id"]),))
            conn.commit()
            conn.close()
    except Exception as exc:
        print(f"[adaptive] context warning: {exc}", flush=True)

    return "\n".join(lines)[:3500]


def _adaptive_unreviewed_rows():
    try:
        with _ADAPTIVE_DB_LOCK:
            conn = _adaptive_conn()
            rows = conn.execute(
                "SELECT * FROM experience WHERE reviewed=0 ORDER BY id ASC LIMIT ?",
                (ADAPTIVE_REVIEW_MAX,),
            ).fetchall()
            conn.close()
            return rows
    except Exception:
        return []


def _adaptive_model_review(rows) -> dict | None:
    model = _choose_ollama_model()
    if not model:
        return None
    caps = _adaptive_capability_snapshot()
    transcript = []
    for row in rows:
        transcript.append(
            f"EXCHANGE {row['id']}\nUSER: {str(row['user_text'])[:2400]}\nASSISTANT: {str(row['assistant_text'])[:2400]}\nROUTE: {row['route']} SUCCESS: {row['success']}"
        )
    prompt = f"""You are VexNative's idle adaptive-learning supervisor.

AVAILABLE LOCAL CAPABILITIES:
{json.dumps(caps, ensure_ascii=False)}

RECENT REAL EXCHANGES:
{chr(10).join(transcript)}

Learn only from evidence in those exchanges. Do not invent personal facts, emotions, events, tool successes, or capabilities. Extract reusable behavior/procedure lessons that would make future replies/actions more natural and accurate. Pay special attention to user corrections, mismatched intent, rigid keyword routing, repeated failures, successful tool patterns, and places where a known local capability should have been used.

Return JSON only with this schema:
{{
  "lessons": [{{"kind":"naturalness|routing|preference|capability|repair|conversation","cue":"short semantic cue","guidance":"concrete reusable guidance","confidence":0.0,"evidence":"short evidence"}}],
  "gaps": [{{"request":"the unresolved user intent","category":"routing|memory|tool|repair|capability","detail":"what needs study or repair","priority":50}}]
}}

Only activate strong lessons supported by explicit correction or repeated evidence. A weak guess should have confidence below 0.60. Never propose downloading or executing arbitrary code."""
    try:
        import requests
        response = requests.post(
            f"{OLLAMA_BASE}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "Analyze VexNative behavior from evidence and return strict JSON only."},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "think": False,
                "format": "json",
                "keep_alive": "20m",
                "options": {"temperature": 0.08, "top_p": 0.70, "num_ctx": 4096, "num_predict": 700},
            },
            timeout=150,
        )
        response.raise_for_status()
        payload = response.json()
        raw = _strip_reasoning_markup(str(((payload.get("message") or {}).get("content")) or "")).strip()
        if not raw:
            return None
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception as exc:
        print(f"[adaptive] review deferred: {exc}", flush=True)
        return None


def _adaptive_mark_reviewed(rows) -> None:
    ids = [int(row["id"]) for row in rows]
    if not ids:
        return
    placeholders = ",".join("?" for _ in ids)
    try:
        with _ADAPTIVE_DB_LOCK:
            conn = _adaptive_conn()
            conn.execute(f"UPDATE experience SET reviewed=1 WHERE id IN ({placeholders})", ids)
            conn.commit()
            conn.close()
    except Exception:
        pass


def _adaptive_safe_repair_probe(rows) -> None:
    text_blob = " ".join(str(row["assistant_text"] or "").lower() for row in rows)
    if "personal memory unavailable" in text_blob or "memory worker" in text_blob:
        try:
            health = _memory_worker_health(start_if_needed=True)
            if not health.get("ok"):
                _adaptive_open_gap("restore local personal memory worker health", "repair", str(health), 88)
        except Exception:
            pass


def _adaptive_worker_once(force: bool = False) -> dict:
    global _ADAPTIVE_LAST_REVIEW
    now = time.time()
    if not force and now - _ADAPTIVE_LAST_FOREGROUND < ADAPTIVE_IDLE_SECONDS:
        return {"ok": True, "idle": False, "detail": "foreground activity is recent"}
    if not force and now - _ADAPTIVE_LAST_REVIEW < 180:
        return {"ok": True, "idle": True, "detail": "adaptive review cooldown"}

    try:
        snap = _resource_snapshot()
        if bool(snap.get("art_running")) and not force:
            return {"ok": True, "idle": True, "detail": "art worker has priority"}
        available = int(snap.get("memory_available") or 0)
        if available and available < 1400 * 1024 * 1024 and not force:
            return {"ok": True, "idle": True, "detail": "memory pressure; adaptive review deferred"}
    except Exception:
        pass

    rows = _adaptive_unreviewed_rows()
    if len(rows) < ADAPTIVE_REVIEW_MIN:
        return {"ok": True, "idle": True, "detail": "not enough new experience"}

    _ADAPTIVE_LAST_REVIEW = now
    with _BACKGROUND_COGNITION_LOCK:
        data = _adaptive_model_review(rows)
    if not isinstance(data, dict):
        return {"ok": False, "detail": "local adaptive review unavailable"}

    learned = 0
    gaps = 0
    for item in data.get("lessons") or []:
        if not isinstance(item, dict):
            continue
        if _adaptive_store_lesson(
            item.get("kind"), item.get("cue"), item.get("guidance"), item.get("confidence"), item.get("evidence")
        ):
            learned += 1
    for item in data.get("gaps") or []:
        if not isinstance(item, dict):
            continue
        _adaptive_open_gap(
            item.get("request"), item.get("category"), item.get("detail"), int(item.get("priority") or 50)
        )
        gaps += 1

    _adaptive_safe_repair_probe(rows)
    _adaptive_mark_reviewed(rows)
    return {"ok": True, "reviewed": len(rows), "learned": learned, "gaps": gaps}


def _adaptive_status() -> dict:
    result = {"ok": True, "db": str(ADAPTIVE_DB), "idle_seconds": ADAPTIVE_IDLE_SECONDS}
    try:
        with _ADAPTIVE_DB_LOCK:
            conn = _adaptive_conn()
            result["experience"] = int(conn.execute("SELECT COUNT(*) AS n FROM experience").fetchone()["n"] or 0)
            result["unreviewed"] = int(conn.execute("SELECT COUNT(*) AS n FROM experience WHERE reviewed=0").fetchone()["n"] or 0)
            result["lessons"] = int(conn.execute("SELECT COUNT(*) AS n FROM lessons").fetchone()["n"] or 0)
            result["active_lessons"] = int(conn.execute("SELECT COUNT(*) AS n FROM lessons WHERE active=1").fetchone()["n"] or 0)
            result["open_gaps"] = int(conn.execute("SELECT COUNT(*) AS n FROM gaps WHERE status='open'").fetchone()["n"] or 0)
            recent = conn.execute(
                "SELECT kind,cue,guidance,confidence,active,hits FROM lessons ORDER BY updated_at DESC LIMIT 8"
            ).fetchall()
            result["recent_lessons"] = [dict(row) for row in recent]
            conn.close()
    except Exception as exc:
        result = {"ok": False, "error": str(exc)[:300]}
    return result


def _adaptive_worker_loop() -> None:
    time.sleep(90)
    while True:
        try:
            _adaptive_worker_once(force=False)
        except Exception as exc:
            print(f"[adaptive] worker warning: {exc}", flush=True)
        time.sleep(ADAPTIVE_LOOP_SECONDS)


'''

if "def _adaptive_worker_loop()" not in text:
    text = text.replace(insert_marker, adaptive + insert_marker, 1)

# Every completed turn becomes experience for idle review. Personal-memory storage
# remains independent and authoritative facts are still handled only by Memory Worker.
record_marker = '    _memory_post("/episode", payload, timeout=1.0)\n'
if record_marker not in text:
    raise SystemExit("v0.11.4: memory turn recorder marker missing")
if "_adaptive_record_exchange(message, reply)" not in text:
    text = text.replace(record_marker, record_marker + "    _adaptive_record_exchange(message, reply)\n", 1)

# Feed relevant learned behavior/capability context into normal cognition on every
# turn. This is semantic working context, not a keyword-triggered action path.
personal_marker = '    if personal_memory:\n        dynamic_system += "\\n\\n" + personal_memory\n'
if personal_marker not in text:
    raise SystemExit("v0.11.4: personal-memory grounding marker missing")
if "adaptive_context = _adaptive_context(message)" not in text:
    text = text.replace(
        personal_marker,
        personal_marker + '    adaptive_context = _adaptive_context(message)\n    if adaptive_context:\n        dynamic_system += "\\n\\n" + adaptive_context\n',
        1,
    )

# Coordinate source-grounded idle research with adaptive review on the low-memory
# PC so the two local Qwen background jobs do not run simultaneously.
learning_call = "    ok, detail = _learning_research_topic(row)\n"
if learning_call in text and "with _BACKGROUND_COGNITION_LOCK:\n        ok, detail = _learning_research_topic(row)" not in text:
    text = text.replace(
        learning_call,
        "    with _BACKGROUND_COGNITION_LOCK:\n        ok, detail = _learning_research_topic(row)\n",
        1,
    )

# Start adaptive review next to the existing self-repair and source-grounded learner.
thread_marker = '    threading.Thread(target=_learning_worker_loop, daemon=True, name="VexLearningEngine").start()\n'
if thread_marker not in text:
    raise SystemExit("v0.11.4: learning worker startup marker missing")
if "VexAdaptiveLearning" not in text:
    text = text.replace(
        thread_marker,
        thread_marker + '    threading.Thread(target=_adaptive_worker_loop, daemon=True, name="VexAdaptiveLearning").start()\n',
        1,
    )

# Authenticated diagnostics/control. /adaptive/run is a deliberate test hook;
# ordinary runtime learning remains automatic and idle-driven.
get_marker = '        if parsed.path == "/learning/status":\n'
if get_marker not in text:
    raise SystemExit("v0.11.4: learning GET route marker missing")
if 'parsed.path == "/adaptive/status"' not in text:
    text = text.replace(
        get_marker,
        '        if parsed.path == "/adaptive/status":\n            self._json(200, _adaptive_status())\n            return\n\n' + get_marker,
        1,
    )

post_marker = '        if parsed.path == "/learning/run":\n'
if post_marker not in text:
    raise SystemExit("v0.11.4: learning POST route marker missing")
if 'parsed.path == "/adaptive/run"' not in text:
    text = text.replace(
        post_marker,
        '        if parsed.path == "/adaptive/run":\n            result = _adaptive_worker_once(force=True)\n            self._json(200 if result.get("ok") else 503, result)\n            return\n\n' + post_marker,
        1,
    )

# Bridge version for field verification.
for stale in [
    '"version": "0.10.8"', '"version": "0.10.9"', '"version": "0.11.0"',
    '"version": "0.11.2"', '"version": "0.11.3"', '"version": "0.11.3.1"',
    '"version": "0.11.3.2"', '"version": "0.11.3.3"'
]:
    text = text.replace(stale, '"version": "0.11.4.0"')

path.write_text(text, encoding="utf-8")
compile(text, str(path), "exec")

final = path.read_text(encoding="utf-8")
checks = [
    "ADAPTIVE_DB",
    "def _adaptive_record_exchange(",
    "def _adaptive_model_review(",
    "def _adaptive_worker_loop(",
    "def _adaptive_context(",
    "VexAdaptiveLearning",
    'parsed.path == "/adaptive/status"',
    'parsed.path == "/adaptive/run"',
    "adaptive_context = _adaptive_context(message)",
    "_adaptive_record_exchange(message, reply)",
    '"version": "0.11.4.0"',
]
for marker in checks:
    if marker not in final:
        raise SystemExit(f"v0.11.4 verifier missing: {marker}")

print("Applied v0.11.4 idle adaptive-learning supervisor + capability context")
