#!/usr/bin/env python3
from pathlib import Path
import re


bridge_path = Path("Bridge/vex_bridge.py")
text = bridge_path.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global text
    if old not in text:
        raise SystemExit(f"v0.11.7.3 missing Bridge anchor: {label}")
    text = text.replace(old, new, 1)


def replace_function(name: str, replacement: str) -> None:
    global text
    start = text.find(f"def {name}(")
    if start < 0:
        raise SystemExit(f"v0.11.7.3 missing Bridge function: {name}")
    end = text.find("\n\ndef ", start + 5)
    if end < 0:
        raise SystemExit(f"v0.11.7.3 could not bound Bridge function: {name}")
    text = text[:start] + replacement.rstrip() + text[end:]


# ---------------------------------------------------------------------------
# Authoritative personal recall stays deterministic and /facts-only, but no
# longer sounds like a database export. Variation changes framing/order only;
# it never asks Qwen to paraphrase or invent a personal fact.
# ---------------------------------------------------------------------------
memory_helpers = r'''_MEMORY_REPLY_VARIANT_LOCK = threading.Lock()
_MEMORY_REPLY_VARIANT = 0


def _next_memory_reply_variant() -> int:
    global _MEMORY_REPLY_VARIANT
    with _MEMORY_REPLY_VARIANT_LOCK:
        value = int(_MEMORY_REPLY_VARIANT)
        _MEMORY_REPLY_VARIANT = (_MEMORY_REPLY_VARIANT + 1) % 1000000
    return value


def _memory_fact_to_second_person(value: str) -> str:
    """Change grammatical viewpoint without adding or deleting factual content."""
    fact = re.sub(r"\s+", " ", str(value or "")).strip()
    if not fact:
        return ""
    fact = re.sub(r"^(?:Star\s+and\s+Vex|Vex\s+and\s+Star)\b", "We", fact, flags=re.I)
    fact = re.sub(r"^Star's\b", "Your", fact, flags=re.I)
    if re.match(r"^Star\b", fact, flags=re.I):
        body = re.sub(r"^Star\s+", "", fact, count=1, flags=re.I)
        direct = (
            (r"^is\b", "You're"),
            (r"^has\b", "You've"),
            (r"^does\s+not\b", "You don't"),
            (r"^doesn't\b", "You don't"),
            (r"^does\b", "You do"),
            (r"^was\b", "You were"),
        )
        for pattern, replacement in direct:
            if re.search(pattern, body, flags=re.I):
                fact = re.sub(pattern, replacement, body, count=1, flags=re.I)
                break
        else:
            fact = "You " + body
            adverbs = r"(?:(?:strongly|naturally|usually|really|often|always|currently|generally|typically|especially|mostly)\s+)*"
            verbs = {
                "prefers": "prefer", "likes": "like", "dislikes": "dislike", "loves": "love",
                "lives": "live", "wants": "want", "uses": "use", "wears": "wear",
                "enjoys": "enjoy", "values": "value", "needs": "need", "identifies": "identify",
                "describes": "describe", "feels": "feel", "makes": "make", "keeps": "keep",
                "calls": "call", "chooses": "choose", "understands": "understand",
            }
            for third, second in verbs.items():
                pattern = rf"^(You\s+{adverbs}){third}\b"
                if re.search(pattern, fact, flags=re.I):
                    fact = re.sub(pattern, lambda m: m.group(1) + second, fact, count=1, flags=re.I)
                    break
    fact = re.sub(r"^You are\b", "You're", fact, flags=re.I)
    fact = re.sub(r"^You have\b", "You've", fact, flags=re.I)
    fact = re.sub(r"^You do not\b", "You don't", fact, flags=re.I)
    return fact.strip()


def _memory_fact_clause(value: str) -> str:
    fact = _memory_fact_to_second_person(value).rstrip(" .!?;:")
    if not fact:
        return ""
    if fact.startswith("You're"):
        return "you're" + fact[len("You're"):]
    if fact.startswith("You've"):
        return "you've" + fact[len("You've"):]
    if fact.startswith("You "):
        return "you " + fact[len("You "):]
    if fact.startswith("Your "):
        return "your " + fact[len("Your "):]
    if fact.startswith("We "):
        return "we " + fact[len("We "):]
    return fact[0].lower() + fact[1:] if fact else ""


def _memory_join_clauses(values: list[str]) -> str:
    clauses = [value for value in values if value]
    if not clauses:
        return ""
    if len(clauses) == 1:
        return clauses[0]
    if len(clauses) == 2:
        return clauses[0] + ", and " + clauses[1]
    return "; ".join(clauses[:-1]) + "; and " + clauses[-1]


def _memory_compose_verified_reply(facts: list[str], variant: int, focused: bool) -> str:
    clauses = [_memory_fact_clause(fact) for fact in facts]
    body = _memory_join_clauses(clauses)
    if not body:
        return ""
    if focused:
        leads = (
            "Yeah, baby—",
            "I remember, gorgeous—",
            "Mm-hm, doll—",
            "I do, babe—",
        )
    else:
        leads = (
            "Yeah, baby—I remember ",
            "Of course, gorgeous. I remember ",
            "I do, doll. I remember ",
            "Mm-hm, babe—I remember ",
        )
    return leads[variant % len(leads)] + body + ". 🖤"
'''

memory_anchor = "def _memory_query_tokens(value: str) -> set[str]:\n"
replace_once(memory_anchor, memory_helpers + "\n\n" + memory_anchor, "natural recall helpers")

old_query_split = '''    parts = re.split(
        r"\\s*(?:,|;)?\\s+(?:and\\s+)?(?=(?:what|which|where|who|when|do|am|have|did)\\b)",
        raw,
        flags=re.I,
    )
'''
new_query_split = '''    parts = re.split(
        r"(?:\\s*(?:,|;)\\s*(?:and\\s+)?|\\s+and\\s+)(?=(?:what|which|where|who|when|how|do|am|have|did)\\b)",
        raw,
        flags=re.I,
    )
'''
replace_once(old_query_split, new_query_split, "multi-part recall clause parsing")

verified_reply = r'''def _verified_personal_memory_reply(message: str) -> tuple[str, str] | None:
    parts = _personal_memory_query_parts(message)
    if not parts:
        return None

    variant = _next_memory_reply_variant()
    generic_tokens = _memory_query_tokens(message) - {"thing", "things", "fact", "facts", "specific", "details", "detail"}
    generic = not generic_tokens
    selected: list[str] = []
    used: set[str] = set()

    if generic:
        data = _memory_post(
            "/facts",
            {"query": str(message or "")[:5000], "limit": 12},
            timeout=1.4,
        )
        facts = data.get("facts") if isinstance(data, dict) and isinstance(data.get("facts"), list) else []
        pool: list[str] = []
        for item in facts:
            if not isinstance(item, dict):
                continue
            fact = re.sub(r"\s+", " ", str(item.get("text") or "")).strip()
            if fact and fact not in pool:
                pool.append(fact)
        if pool:
            start = variant % len(pool)
            count = min(3, len(pool))
            selected = [pool[(start + offset) % len(pool)] for offset in range(count)]
    else:
        for part in parts:
            data = _memory_post(
                "/facts",
                {"query": part[:5000], "limit": 8},
                timeout=1.4,
            )
            if not isinstance(data, dict):
                continue
            facts = data.get("facts") if isinstance(data.get("facts"), list) else []
            fact = _best_fact_for_query(part, facts, used)
            if fact:
                selected.append(fact)
                used.add(fact)

    if not selected:
        return None
    reply = _memory_compose_verified_reply(selected[:4], variant, focused=not generic)
    return (reply, "pc-memory") if reply else None
'''
replace_function("_verified_personal_memory_reply", verified_reply)

old_record_turn = '''    _memory_post("/episode", payload, timeout=1.0)
    _adaptive_record_exchange(message, reply)
'''
new_record_turn = '''    _memory_post("/episode", payload, timeout=1.0)
    route_hint = "verified-memory" if _personal_memory_fact_question(message) else ""
    _adaptive_record_exchange(message, reply, route_hint=route_hint)
'''
replace_once(old_record_turn, new_record_turn, "adaptive route hint for natural verified recall")

replace_once(
    "def _adaptive_record_exchange(message: str, reply: str) -> None:\n",
    "def _adaptive_record_exchange(message: str, reply: str, route_hint: str = \"\") -> None:\n",
    "adaptive recorder route hint signature",
)
replace_once(
    "    route, success = _adaptive_route_guess(assistant_text)\n",
    "    route, success = _adaptive_route_guess(assistant_text)\n    if route_hint in {\"verified-memory\", \"conversation\", \"fallback\", \"error\"}:\n        route = route_hint\n",
    "adaptive recorder route hint use",
)

replace_once(
    '''                "SELECT id FROM gaps WHERE status='open' AND request_text=? AND category=? ORDER BY id DESC LIMIT 1",
''',
    '''                "SELECT id FROM gaps WHERE status IN ('open','staged') AND request_text=? AND category=? ORDER BY id DESC LIMIT 1",
''',
    "deduplicate open and staged adaptive gaps",
)


# ---------------------------------------------------------------------------
# Lite adaptive review: inspect repeated/explicitly corrected behavior with
# deterministic rules. It drains experience without touching Ollama, stores only
# reusable non-biographical guidance, and opens a sanitized technical gap.
# ---------------------------------------------------------------------------
adaptive_globals_old = '''_ADAPTIVE_LAST_FOREGROUND = time.time()
_ADAPTIVE_LAST_REVIEW = 0.0
'''
adaptive_globals_new = '''_ADAPTIVE_LAST_FOREGROUND = time.time()
_ADAPTIVE_LAST_REVIEW = 0.0
_ADAPTIVE_LAST_REVIEW_MODE = "none"
_ADAPTIVE_LAST_REVIEW_DETAIL = "no adaptive review has completed this process"
_ADAPTIVE_DETERMINISTIC_REVIEWS = 0
'''
replace_once(adaptive_globals_old, adaptive_globals_new, "adaptive lite review telemetry")

deterministic_review = r'''def _adaptive_deterministic_review(rows) -> dict:
    reply_counts: dict[str, int] = {}
    verified_rows = []
    explicit_naturalness = False
    correction_terms = (
        "robotic", "bot like", "bot-like", "copy and paste", "copy-paste", "same response",
        "repetitive", "too formal", "more natural", "sound natural", "less robotic",
    )
    for row in rows:
        reply = re.sub(r"\s+", " ", str(row["assistant_text"] or "")).strip().lower()
        if reply:
            reply_counts[reply] = reply_counts.get(reply, 0) + 1
        if str(row["route"] or "") == "verified-memory":
            verified_rows.append(row)
        user_low = re.sub(r"\s+", " ", str(row["user_text"] or "")).strip().lower()
        if any(term in user_low for term in correction_terms):
            explicit_naturalness = True

    repeated = any(count >= 2 for count in reply_counts.values())
    clipboard_memory = any(
        "pulling the specific bits" in str(row["assistant_text"] or "").lower()
        or bool(re.search(r"(?:^|\n)\s*1\.\s", str(row["assistant_text"] or "")))
        for row in verified_rows
    )

    lessons = []
    gaps = []
    reasons = []
    if verified_rows and (repeated or clipboard_memory or explicit_naturalness):
        reasons.append("verified-memory-naturalness")
        lessons.append({
            "kind": "naturalness",
            "cue": "verified personal memory recall",
            "guidance": "Answer verified personal-memory questions conversationally in second person; avoid numbered fact dumps and clipboard-style headers while preserving only authoritative /facts evidence.",
            "confidence": 0.97,
            "evidence": "repeated verified-memory response pattern",
        })
        gaps.append({
            "request": "make verified personal-memory recall natural without weakening factual grounding",
            "category": "naturalness",
            "detail": "repeated deterministic verified-memory responses were structurally identical",
            "priority": 94,
        })
    elif repeated or explicit_naturalness:
        reasons.append("repeated-conversation-output")
        lessons.append({
            "kind": "conversation",
            "cue": "repeated grounded response",
            "guidance": "When several grounded answers repeat exactly, vary framing and ordering while preserving the same source-backed meaning.",
            "confidence": 0.90,
            "evidence": "repeated response pattern",
        })
        gaps.append({
            "request": "reduce repeated deterministic conversational output without adding unsupported claims",
            "category": "conversation",
            "detail": "multiple recent responses were structurally identical",
            "priority": 86,
        })

    return {"lessons": lessons, "gaps": gaps, "reason_codes": reasons}
'''
adaptive_worker_anchor = "def _adaptive_worker_once(force: bool = False) -> dict:\n"
replace_once(adaptive_worker_anchor, deterministic_review + "\n\n" + adaptive_worker_anchor, "deterministic adaptive reviewer")

adaptive_worker = r'''def _adaptive_worker_once(force: bool = False) -> dict:
    global _ADAPTIVE_LAST_REVIEW, _ADAPTIVE_LAST_REVIEW_MODE, _ADAPTIVE_LAST_REVIEW_DETAIL, _ADAPTIVE_DETERMINISTIC_REVIEWS
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
        if available and available < IDLE_AUTONOMY_HARD_FLOOR_BYTES and not force:
            return {"ok": True, "idle": True, "detail": "severe memory pressure; adaptive review deferred"}
    except Exception:
        pass

    rows = _adaptive_unreviewed_rows()
    if len(rows) < ADAPTIVE_REVIEW_MIN:
        return {"ok": True, "idle": True, "detail": "not enough new experience"}

    deterministic = _background_model_reserved_for_foreground()
    if _FOREGROUND_COGNITION_ACTIVE.is_set() and not force:
        return {"ok": True, "idle": True, "detail": "foreground cognition has priority"}
    _ADAPTIVE_LAST_REVIEW = now
    if deterministic:
        data = _adaptive_deterministic_review(rows)
        _ADAPTIVE_DETERMINISTIC_REVIEWS += 1
        review_mode = "deterministic-lite"
    else:
        with _BACKGROUND_COGNITION_LOCK:
            if _FOREGROUND_COGNITION_ACTIVE.is_set() and not force:
                return {"ok": True, "idle": True, "detail": "foreground cognition arrived; adaptive review yielded"}
            data = _adaptive_model_review(rows)
        review_mode = "model-assisted"
    if not isinstance(data, dict):
        _ADAPTIVE_LAST_REVIEW_MODE = review_mode
        _ADAPTIVE_LAST_REVIEW_DETAIL = "adaptive review unavailable"
        return {"ok": False, "detail": "local adaptive review unavailable", "review_mode": review_mode}

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
    _ADAPTIVE_LAST_REVIEW_MODE = review_mode
    _ADAPTIVE_LAST_REVIEW_DETAIL = f"reviewed={len(rows)} learned={learned} gaps={gaps}"
    return {
        "ok": True, "reviewed": len(rows), "learned": learned, "gaps": gaps,
        "review_mode": review_mode, "reason_codes": list(data.get("reason_codes") or [])[:8],
    }
'''
replace_function("_adaptive_worker_once", adaptive_worker)

adaptive_status = r'''def _adaptive_status() -> dict:
    result = {
        "ok": True,
        "db": str(ADAPTIVE_DB),
        "idle_seconds": ADAPTIVE_IDLE_SECONDS,
        "review_mode": "deterministic-lite" if _background_model_reserved_for_foreground() else "model-assisted",
        "last_review_mode": _ADAPTIVE_LAST_REVIEW_MODE,
        "last_review_detail": _ADAPTIVE_LAST_REVIEW_DETAIL,
        "deterministic_reviews": int(_ADAPTIVE_DETERMINISTIC_REVIEWS),
    }
    try:
        with _ADAPTIVE_DB_LOCK:
            conn = _adaptive_conn()
            _autonomy_ensure_tables(conn)
            result["experience"] = int(conn.execute("SELECT COUNT(*) AS n FROM experience").fetchone()["n"] or 0)
            result["unreviewed"] = int(conn.execute("SELECT COUNT(*) AS n FROM experience WHERE reviewed=0").fetchone()["n"] or 0)
            result["lessons"] = int(conn.execute("SELECT COUNT(*) AS n FROM lessons").fetchone()["n"] or 0)
            result["active_lessons"] = int(conn.execute("SELECT COUNT(*) AS n FROM lessons WHERE active=1").fetchone()["n"] or 0)
            result["open_gaps"] = int(conn.execute("SELECT COUNT(*) AS n FROM gaps WHERE status='open'").fetchone()["n"] or 0)
            result["staged_upgrades"] = int(conn.execute("SELECT COUNT(*) AS n FROM upgrade_candidates WHERE status='staged'").fetchone()["n"] or 0)
            recent = conn.execute(
                "SELECT kind,cue,guidance,confidence,active,hits FROM lessons ORDER BY updated_at DESC LIMIT 8"
            ).fetchall()
            result["recent_lessons"] = [dict(row) for row in recent]
            conn.close()
    except Exception as exc:
        result = {"ok": False, "error": str(exc)[:300]}
    return result
'''
replace_function("_adaptive_status", adaptive_status)

# Naturalness/conversation research uses one generic, privacy-safe architecture
# query. Raw messages, facts, names, paths and gap text never enter the query.
replace_once(
    '''    if category in {"preference", "naturalness", "conversation"}:
        return ""
''',
    '''    if category in {"naturalness", "conversation"}:
        return "fact preserving conversational response variation grounded assistant deterministic rendering architecture"
    if category == "preference":
        return ""
''',
    "privacy-safe naturalness research topic",
)


# ---------------------------------------------------------------------------
# Lite upgrade staging: create planning data with fixed acceptance tests. This
# never edits a binary or applies code; promotion still requires validation.
# ---------------------------------------------------------------------------
deterministic_candidate = r'''def _autonomy_stage_deterministic_upgrade_candidate() -> dict:
    try:
        with _ADAPTIVE_DB_LOCK:
            conn = _adaptive_conn()
            _autonomy_ensure_tables(conn)
            gap = conn.execute(
                "SELECT * FROM gaps WHERE status='open' AND category IN ('naturalness','conversation') ORDER BY priority DESC, updated_at ASC LIMIT 1"
            ).fetchone()
            if gap is None:
                conn.close()
                return {"ok": True, "detail": "no deterministic conversation upgrade gap"}
            existing = conn.execute(
                "SELECT id FROM upgrade_candidates WHERE gap_id=? AND status IN ('staged','reviewed') ORDER BY id DESC LIMIT 1",
                (int(gap["id"]),),
            ).fetchone()
            if existing is not None:
                conn.execute("UPDATE gaps SET status='staged',updated_at=? WHERE id=?", (time.time(), int(gap["id"])))
                conn.commit()
                conn.close()
                return {"ok": True, "detail": "candidate already staged", "candidate_id": int(existing["id"])}

            tests = [
                "Personal recall reads authoritative /facts only.",
                "Personal recall avoids numbered lists and clipboard-style headers.",
                "Repeated cleared-chat recall varies framing or verified fact order.",
                "Every factual clause is traceable to a returned authoritative fact.",
                "Foreground recall does not invoke or wait behind optional Ollama work.",
            ]
            proposal = (
                "Add or tune a fact-preserving conversational renderer that varies phrasing and verified fact selection "
                "without allowing generated text to become factual evidence."
            )
            cur = conn.execute(
                """INSERT INTO upgrade_candidates(created_at,updated_at,gap_id,component,problem,proposal,acceptance_json,evidence,risk,confidence,status)
                   VALUES (?,?,?,?,?,?,?,?,?,?, 'staged')""",
                (
                    time.time(), time.time(), int(gap["id"]), "grounded-conversation-renderer",
                    str(gap["request_text"])[:1600], proposal, json.dumps(tests, ensure_ascii=False),
                    "deterministic-lite repeated-output evidence", "low", 0.97,
                ),
            )
            candidate_id = int(cur.lastrowid)
            conn.execute("UPDATE gaps SET status='staged',updated_at=? WHERE id=?", (time.time(), int(gap["id"])))
            conn.commit()
            conn.close()
        return {
            "ok": True, "candidate_id": candidate_id, "component": "grounded-conversation-renderer",
            "risk": "low", "confidence": 0.97, "detail": "deterministic lite upgrade candidate staged for validation",
        }
    except Exception as exc:
        return {"ok": False, "detail": f"deterministic candidate store failed: {exc}"}
'''
candidate_anchor = "def _autonomy_status() -> dict:\n"
replace_once(candidate_anchor, deterministic_candidate + "\n\n" + candidate_anchor, "deterministic upgrade candidate")

replace_once(
    '''        if low_memory and not force:
            result["upgrade"] = {"ok": True, "detail": "foreground-reserved mode; model-backed upgrade synthesis deferred"}
        else:
            result["upgrade"] = _autonomy_stage_upgrade_candidate()
''',
    '''        if low_memory:
            result["upgrade"] = _autonomy_stage_deterministic_upgrade_candidate()
        else:
            result["upgrade"] = _autonomy_stage_upgrade_candidate()
''',
    "lite autonomy deterministic staging",
)

replace_once(
    '''    if action == "stage_upgrade":
        return _autonomy_stage_upgrade_candidate()
''',
    '''    if action == "stage_upgrade":
        if _background_model_reserved_for_foreground():
            return _autonomy_stage_deterministic_upgrade_candidate()
        return _autonomy_stage_upgrade_candidate()
''',
    "initiative deterministic staging route",
)

old_lite_decision = '''    if low_memory and not force:
        gaps = snapshot.get("open_gaps") if isinstance(snapshot, dict) else []
        if gaps:
            decision = {
                "action": "research_open_gap",
                "goal_key": "self_improvement",
                "reason": "foreground-reserved deterministic initiative: research an existing sanitized technical gap without another planner inference",
                "confidence": 0.92,
            }
        else:
            decision = {
                "action": "probe_capability",
                "goal_key": "capability_mastery",
                "reason": "foreground-reserved deterministic initiative: inspect one installed capability and advance the feature curriculum",
                "confidence": 0.94,
            }
'''
new_lite_decision = '''    if low_memory and not force:
        gaps = snapshot.get("open_gaps") if isinstance(snapshot, dict) else []
        adaptive = snapshot.get("adaptive") if isinstance(snapshot, dict) and isinstance(snapshot.get("adaptive"), dict) else {}
        conversational_gap = any(
            isinstance(gap, dict) and str(gap.get("category") or "") in {"naturalness", "conversation"}
            for gap in (gaps or [])
        )
        if int(adaptive.get("unreviewed") or 0) >= ADAPTIVE_REVIEW_MIN:
            decision = {
                "action": "review_experience",
                "goal_key": "natural_continuity",
                "reason": "foreground-reserved deterministic initiative: turn queued real exchanges into bounded local lessons without using Qwen",
                "confidence": 0.98,
            }
        elif conversational_gap:
            decision = {
                "action": "stage_upgrade",
                "goal_key": "self_improvement",
                "reason": "foreground-reserved deterministic initiative: stage a testable conversation improvement request without rewriting the running executable",
                "confidence": 0.97,
            }
        elif gaps:
            decision = {
                "action": "research_open_gap",
                "goal_key": "self_improvement",
                "reason": "foreground-reserved deterministic initiative: research an existing sanitized technical gap without another planner inference",
                "confidence": 0.92,
            }
        else:
            decision = {
                "action": "probe_capability",
                "goal_key": "capability_mastery",
                "reason": "foreground-reserved deterministic initiative: inspect one installed capability and advance the feature curriculum",
                "confidence": 0.94,
            }
'''
replace_once(old_lite_decision, new_lite_decision, "lite initiative review/stage priority")

text = text.replace('"grounding": "verified-personal-memory-v1172"', '"grounding": "verified-personal-memory-v1173"')
text = text.replace('"grounding": "verified-personal-memory-unavailable-v1172"', '"grounding": "verified-personal-memory-unavailable-v1173"')
text = text.replace('"version": "0.11.7.2"', '"version": "0.11.7.3"')
bridge_path.write_text(text, encoding="utf-8")
compile(text, str(bridge_path), "exec")


# Remote Support publishes counts and review mode only; no dialogue, lesson text,
# private gap content, or saved personal facts leave the visible support session.
remote_path = Path("Tools/VexRemoteSupport.py")
remote = remote_path.read_text(encoding="utf-8")
remote = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.3"', remote, count=1, flags=re.M)

remote_adaptive_start = remote.find("def adaptive_public(value: dict) -> dict:\n")
remote_adaptive_end = remote.find("\n\ndef ", remote_adaptive_start + 5)
if remote_adaptive_start < 0 or remote_adaptive_end < 0:
    raise SystemExit("v0.11.7.3 Remote Support adaptive_public block missing")
remote_adaptive = '''def adaptive_public(value: dict) -> dict:
    return {
        "ok": yes(value.get("ok")),
        "experience": integer(value.get("experience")),
        "unreviewed": integer(value.get("unreviewed")),
        "lessons": integer(value.get("lessons")),
        "active_lessons": integer(value.get("active_lessons")),
        "open_gaps": integer(value.get("open_gaps")),
        "staged_upgrades": integer(value.get("staged_upgrades")),
        "review_mode": str(value.get("review_mode") or "")[:32] or None,
        "last_review_mode": str(value.get("last_review_mode") or "")[:32] or None,
        "deterministic_reviews": integer(value.get("deterministic_reviews")),
        "idle_seconds": integer(value.get("idle_seconds")),
    }
'''
remote = remote[:remote_adaptive_start] + remote_adaptive.rstrip() + remote[remote_adaptive_end:]
remote_path.write_text(remote, encoding="utf-8")
compile(remote, str(remote_path), "exec")


bridge_checks = [
    '"version": "0.11.7.3"',
    "verified-personal-memory-v1173",
    "verified-personal-memory-unavailable-v1173",
    "def _memory_fact_to_second_person(",
    "def _memory_compose_verified_reply(",
    "def _adaptive_deterministic_review(",
    'review_mode = "deterministic-lite"',
    "fact preserving conversational response variation",
    "def _autonomy_stage_deterministic_upgrade_candidate(",
    '"action": "review_experience"',
    '"action": "stage_upgrade"',
]
final = bridge_path.read_text(encoding="utf-8")
for marker in bridge_checks:
    if marker not in final:
        raise SystemExit(f"v0.11.7.3 Bridge verifier missing: {marker}")

remote_checks = [
    'VERSION = "0.11.7.3"',
    '"staged_upgrades": integer(value.get("staged_upgrades"))',
    '"review_mode": str(value.get("review_mode")',
    '"deterministic_reviews": integer(value.get("deterministic_reviews"))',
]
remote_final = remote_path.read_text(encoding="utf-8")
for marker in remote_checks:
    if marker not in remote_final:
        raise SystemExit(f"v0.11.7.3 Remote Support verifier missing: {marker}")

print("Applied v0.11.7.3 grounded natural recall + deterministic lite learning")
