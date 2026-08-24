#!/usr/bin/env python3
from pathlib import Path

path = Path("Bridge/vex_bridge.py")
text = path.read_text(encoding="utf-8")

insert_marker = "def _vex_background_services() -> None:\n"
if insert_marker not in text:
    raise SystemExit("v0.11.6: background service marker missing")

initiative = r'''
# ---------------------------------------------------------------------------
# v0.11.6 Initiative + Operational Self-Model
#
# Goal: VexNative should not need a fresh command for every useful internal act.
# While idle she maintains an operational model of her own capabilities/state,
# keeps persistent long-running goals, chooses a useful next INTERNAL action, runs
# it through existing validated subsystems, records the outcome, and carries that
# continuity back into later conversation.
#
# "Self-model" here is concrete runtime state: capabilities, health, resources,
# goals, uncertainty, recent actions and outcomes. It does not fabricate tool
# success or unsupported capabilities.
# ---------------------------------------------------------------------------
INITIATIVE_IDLE_SECONDS = 180
INITIATIVE_DECISION_INTERVAL = 240
INITIATIVE_MAX_EVENTS = 500
_INITIATIVE_LAST_DECISION = 0.0

INITIATIVE_GOALS = [
    {
        "key": "natural_continuity",
        "goal": "Use persistent memory, adaptive lessons, and ordinary cognition together so conversation remains natural without magic trigger phrases.",
        "priority": 96,
    },
    {
        "key": "capability_mastery",
        "goal": "Continuously learn what local VexNative features exist, when each is useful, and how to use them reliably.",
        "priority": 92,
    },
    {
        "key": "system_health",
        "goal": "Keep memory, cognition, Bridge, indexing, learned skills, diagnostics, and available workers healthy with bounded repair.",
        "priority": 90,
    },
    {
        "key": "self_improvement",
        "goal": "Turn repeated failures and capability gaps into source-grounded lessons, research, tests, and staged improvements.",
        "priority": 88,
    },
    {
        "key": "grounded_independence",
        "goal": "Take useful low-risk internal initiative while idle, verify outcomes, preserve privacy, and avoid claiming actions that did not occur.",
        "priority": 86,
    },
]

INITIATIVE_ACTIONS = {
    "probe_capability",
    "rehearse_skills",
    "repair_known_components",
    "research_open_gap",
    "stage_upgrade",
    "refresh_index",
    "review_experience",
    "nothing",
}


def _initiative_ensure_tables(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS initiative_goals (
            goal_key TEXT PRIMARY KEY,
            goal TEXT NOT NULL,
            priority INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            last_progress REAL NOT NULL DEFAULT 0,
            progress_note TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS initiative_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at REAL NOT NULL,
            action TEXT NOT NULL,
            goal_key TEXT NOT NULL DEFAULT '',
            reason TEXT NOT NULL DEFAULT '',
            ok INTEGER NOT NULL DEFAULT 0,
            detail TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS self_state (
            state_key TEXT PRIMARY KEY,
            updated_at REAL NOT NULL,
            value_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_initiative_events_time ON initiative_events(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_initiative_goals_priority ON initiative_goals(active, priority DESC);
        """
    )
    now = time.time()
    for item in INITIATIVE_GOALS:
        conn.execute(
            """INSERT INTO initiative_goals(goal_key,goal,priority,active,created_at,updated_at,last_progress,progress_note)
               VALUES (?,?,?,?,?,?,0,'')
               ON CONFLICT(goal_key) DO UPDATE SET goal=excluded.goal,priority=excluded.priority,active=1,updated_at=excluded.updated_at""",
            (item["key"], item["goal"], int(item["priority"]), 1, now, now),
        )
    conn.commit()


def _initiative_record(action: str, goal_key: str, reason: str, ok: bool, detail: str, payload: dict | None = None) -> None:
    try:
        with _ADAPTIVE_DB_LOCK:
            conn = _adaptive_conn()
            _initiative_ensure_tables(conn)
            conn.execute(
                "INSERT INTO initiative_events(created_at,action,goal_key,reason,ok,detail,payload_json) VALUES (?,?,?,?,?,?,?)",
                (
                    time.time(), str(action)[:80], str(goal_key)[:80], str(reason)[:1200],
                    1 if ok else 0, str(detail)[:2400], json.dumps(payload or {}, ensure_ascii=False)[:8000],
                ),
            )
            conn.execute(
                "DELETE FROM initiative_events WHERE id NOT IN (SELECT id FROM initiative_events ORDER BY id DESC LIMIT ?)",
                (INITIATIVE_MAX_EVENTS,),
            )
            if goal_key:
                conn.execute(
                    "UPDATE initiative_goals SET last_progress=?,progress_note=?,updated_at=? WHERE goal_key=?",
                    (time.time(), str(detail)[:1200], time.time(), str(goal_key)[:80]),
                )
            conn.commit()
            conn.close()
    except Exception as exc:
        print(f"[initiative] record warning: {exc}", flush=True)


def _initiative_self_snapshot() -> dict:
    snap = {
        "self_model_kind": "operational-runtime",
        "time": time.time(),
        "capabilities": {},
        "resources": {},
        "memory": {},
        "adaptive": {},
        "learning": {},
        "open_gaps": [],
        "goals": [],
    }
    try:
        resources = _resource_snapshot()
        snap["resources"] = {
            "memory_available": int(resources.get("memory_available") or 0),
            "memory_total": int(resources.get("memory_total") or 0),
            "cpu_logical": int(resources.get("cpu_logical") or 0),
            "art_running": bool(resources.get("art_running")),
        }
    except Exception:
        pass
    try:
        mh = _memory_worker_health(start_if_needed=True)
        snap["memory"] = {
            "ok": bool(mh.get("ok")),
            "version": str(mh.get("version") or "")[:40],
            "memories": int(mh.get("memories") or 0),
            "messages": int(mh.get("messages") or 0),
            "episodes": int(mh.get("episodes") or 0),
        }
    except Exception:
        pass
    try:
        caps = _adaptive_capability_snapshot()
        snap["capabilities"] = caps
    except Exception:
        pass
    try:
        with _ADAPTIVE_DB_LOCK:
            conn = _adaptive_conn()
            _autonomy_ensure_tables(conn)
            _initiative_ensure_tables(conn)
            snap["goals"] = [dict(row) for row in conn.execute(
                "SELECT goal_key,goal,priority,last_progress,progress_note FROM initiative_goals WHERE active=1 ORDER BY priority DESC"
            ).fetchall()]
            snap["open_gaps"] = [dict(row) for row in conn.execute(
                "SELECT id,category,request_text,detail,priority FROM gaps WHERE status='open' ORDER BY priority DESC,updated_at ASC LIMIT 8"
            ).fetchall()]
            snap["adaptive"] = {
                "unreviewed": int(conn.execute("SELECT COUNT(*) AS n FROM experience WHERE reviewed=0").fetchone()["n"] or 0),
                "active_lessons": int(conn.execute("SELECT COUNT(*) AS n FROM lessons WHERE active=1").fetchone()["n"] or 0),
                "staged_upgrades": int(conn.execute("SELECT COUNT(*) AS n FROM upgrade_candidates WHERE status='staged'").fetchone()["n"] or 0),
            }
            conn.close()
    except Exception as exc:
        snap["db_error"] = str(exc)[:240]
    try:
        learning = _learning_status()
        if isinstance(learning, dict):
            snap["learning"] = {
                "notes": int(learning.get("notes") or 0),
                "queue_counts": learning.get("queue_counts") or {},
            }
    except Exception:
        pass
    return snap


def _initiative_store_self_state(snapshot: dict) -> None:
    try:
        with _ADAPTIVE_DB_LOCK:
            conn = _adaptive_conn()
            _initiative_ensure_tables(conn)
            conn.execute(
                """INSERT INTO self_state(state_key,updated_at,value_json) VALUES ('runtime',?,?)
                   ON CONFLICT(state_key) DO UPDATE SET updated_at=excluded.updated_at,value_json=excluded.value_json""",
                (time.time(), json.dumps(snapshot, ensure_ascii=False)[:30000]),
            )
            conn.commit()
            conn.close()
    except Exception:
        pass


def _initiative_recent_events(limit: int = 8) -> list[dict]:
    try:
        with _ADAPTIVE_DB_LOCK:
            conn = _adaptive_conn()
            _initiative_ensure_tables(conn)
            rows = conn.execute(
                "SELECT created_at,action,goal_key,reason,ok,detail FROM initiative_events ORDER BY id DESC LIMIT ?",
                (max(1, min(20, int(limit))),),
            ).fetchall()
            conn.close()
            return [dict(row) for row in rows]
    except Exception:
        return []


def _initiative_local_private_guidance() -> str:
    # Private memory is local input to the local planner only; it is never copied
    # into public web queries. Keep the slice compact on the low-memory node.
    try:
        return _autonomy_private_memory_guidance()[:4500]
    except Exception:
        return ""


def _initiative_choose_action(snapshot: dict) -> dict:
    """Use local cognition to choose one useful internal next action.

    The model chooses only from a fixed allowlist. Execution still goes through the
    corresponding validated subsystem, so a planner sentence cannot become shell
    access or an unsupported side effect.
    """
    model = _choose_ollama_model()
    if not model:
        return {"action": "probe_capability", "goal_key": "system_health", "reason": "local cognition unavailable for planning"}
    recent = _initiative_recent_events(6)
    private_guidance = _initiative_local_private_guidance()
    public_snapshot = json.loads(json.dumps(snapshot, ensure_ascii=False))
    # Goal descriptions are project/runtime goals, but raw private memory is kept
    # outside the serialized self-state evidence.
    prompt = f"""You are VexNative's local initiative planner. Choose ONE useful internal action to advance long-running goals without waiting for a user command.

OPERATIONAL SELF-STATE:
{json.dumps(public_snapshot, ensure_ascii=False)[:14000]}

RECENT AUTONOMOUS ACTIONS:
{json.dumps(recent, ensure_ascii=False)[:5000]}

LOCAL PRIVATE GUIDANCE (local model only; do not quote biography into the output):
{private_guidance}

Allowed actions only:
- probe_capability: inspect/test one installed capability and queue generic technical research if weak
- rehearse_skills: validate saved learned workflows without executing their side effects
- repair_known_components: run bounded existing repair supervisor with circuit breakers
- research_open_gap: convert one technical gap into a sanitized generic public research topic and queue it
- stage_upgrade: turn a researched unresolved technical gap into a testable staged improvement candidate
- refresh_index: refresh local file index only when needed
- review_experience: review recent real exchanges for reusable high-confidence behavior/routing lessons
- nothing: choose this when resources are busy or no useful work is due

Return strict JSON only:
{{"action":"one allowed action","goal_key":"one active goal key","reason":"short evidence-based reason","confidence":0.0}}
Do not invent failures, capabilities, personal facts, or completed actions. Prefer progress that is useful, low-risk, and not redundant with recent events."""
    try:
        import requests
        with _BACKGROUND_COGNITION_LOCK:
            response = requests.post(
                f"{OLLAMA_BASE}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "Choose one grounded internal VexNative action and return strict JSON only."},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "think": False,
                    "format": "json",
                    "keep_alive": "20m",
                    "options": {"temperature": 0.08, "top_p": 0.70, "num_ctx": 4096, "num_predict": 260},
                },
                timeout=120,
            )
        response.raise_for_status()
        payload = response.json()
        raw = _strip_reasoning_markup(str(((payload.get("message") or {}).get("content")) or "")).strip()
        data = json.loads(raw) if raw else {}
        if not isinstance(data, dict):
            raise ValueError("planner output is not object")
        action = str(data.get("action") or "nothing").strip().lower()
        if action not in INITIATIVE_ACTIONS:
            action = "nothing"
        goal_key = str(data.get("goal_key") or "grounded_independence").strip()[:80]
        reason = re.sub(r"\s+", " ", str(data.get("reason") or "")).strip()[:900]
        try:
            confidence = max(0.0, min(1.0, float(data.get("confidence") or 0)))
        except Exception:
            confidence = 0.0
        if confidence < 0.45:
            action = "nothing"
        return {"action": action, "goal_key": goal_key, "reason": reason, "confidence": confidence}
    except Exception as exc:
        return {"action": "probe_capability", "goal_key": "system_health", "reason": f"planner deferred: {exc.__class__.__name__}", "confidence": 0.50}


def _initiative_research_gap(snapshot: dict) -> dict:
    gaps = snapshot.get("open_gaps") if isinstance(snapshot, dict) else []
    for gap in gaps or []:
        if not isinstance(gap, dict):
            continue
        topic = _autonomy_public_research_topic(
            str(gap.get("category") or ""), str(gap.get("request_text") or ""), str(gap.get("detail") or "")
        )
        if topic:
            queued = _learning_queue_topic(topic, reason="initiative-gap", priority=max(50, min(90, int(gap.get("priority") or 60))))
            return {"ok": True, "queued": bool(queued), "topic": topic, "gap_id": int(gap.get("id") or 0)}
    return {"ok": True, "detail": "no public-safe technical gap due"}


def _initiative_execute(decision: dict, snapshot: dict) -> dict:
    action = str(decision.get("action") or "nothing")
    if action == "probe_capability":
        return _autonomy_feature_curriculum_once()
    if action == "rehearse_skills":
        return _autonomy_rehearse_skills()
    if action == "repair_known_components":
        return _sr_run_once(force=False, include_art=False)
    if action == "research_open_gap":
        return _initiative_research_gap(snapshot)
    if action == "stage_upgrade":
        return _autonomy_stage_upgrade_candidate()
    if action == "refresh_index":
        ok, detail = _sr_repair_index(force=False)
        return {"ok": bool(ok), "detail": detail}
    if action == "review_experience":
        return _adaptive_worker_once(force=True)
    return {"ok": True, "detail": "no internal action needed"}


def _initiative_context(message: str = "") -> str:
    """Carry autonomous continuity into later cognition naturally."""
    snapshot = _initiative_self_snapshot()
    events = _initiative_recent_events(5)
    goals = snapshot.get("goals") or []
    lines = [
        "OPERATIONAL SELF-MODEL / INITIATIVE CONTEXT",
        "This is verified local runtime/project state, not a claim of human consciousness. Use it to maintain continuity, initiative and accurate awareness of local capabilities.",
    ]
    if goals:
        lines.append("Active long-running goals: " + "; ".join(str(g.get("goal") or "")[:240] for g in goals[:5]))
    caps = snapshot.get("capabilities") or {}
    enabled = [k for k, v in caps.items() if v is True]
    if enabled:
        lines.append("Known available systems: " + ", ".join(enabled) + ".")
    if events:
        lines.append("Recent autonomous internal work:")
        for event in events[:4]:
            lines.append(f"- {event.get('action')}: {'ok' if event.get('ok') else 'attention'} — {str(event.get('detail') or '')[:360]}")
    return "\n".join(lines)[:4200]


def _initiative_status() -> dict:
    snapshot = _initiative_self_snapshot()
    snapshot["recent_events"] = _initiative_recent_events(10)
    snapshot["idle_seconds"] = INITIATIVE_IDLE_SECONDS
    snapshot["decision_interval"] = INITIATIVE_DECISION_INTERVAL
    return {"ok": True, **snapshot}


def _initiative_worker_once(force: bool = False) -> dict:
    global _INITIATIVE_LAST_DECISION
    now = time.time()
    if not force and now - _ADAPTIVE_LAST_FOREGROUND < INITIATIVE_IDLE_SECONDS:
        return {"ok": True, "idle": False, "detail": "foreground activity is recent"}
    if not force and now - _INITIATIVE_LAST_DECISION < INITIATIVE_DECISION_INTERVAL:
        return {"ok": True, "idle": True, "detail": "initiative decision cooldown"}
    try:
        rs = _resource_snapshot()
        if bool(rs.get("art_running")) and not force:
            return {"ok": True, "idle": True, "detail": "art worker has priority"}
        available = int(rs.get("memory_available") or 0)
        if available and available < 1600 * 1024 * 1024 and not force:
            return {"ok": True, "idle": True, "detail": "memory pressure; initiative deferred"}
    except Exception:
        pass

    _INITIATIVE_LAST_DECISION = now
    snapshot = _initiative_self_snapshot()
    _initiative_store_self_state(snapshot)
    decision = _initiative_choose_action(snapshot)
    result = _initiative_execute(decision, snapshot)
    ok = bool(result.get("ok")) if isinstance(result, dict) else False
    detail = str((result or {}).get("detail") or (result or {}).get("message") or decision.get("reason") or "completed")[:2200]
    _initiative_record(
        str(decision.get("action") or "nothing"), str(decision.get("goal_key") or ""),
        str(decision.get("reason") or ""), ok, detail, result if isinstance(result, dict) else {},
    )
    return {"ok": ok, "decision": decision, "result": result}


'''

if "def _initiative_worker_once(" not in text:
    text = text.replace(insert_marker, initiative + insert_marker, 1)

# Run initiative from the existing single adaptive background loop so this
# low-memory machine does not gain another competing local-model thread.
loop_old = '''        try:\n            _adaptive_worker_once(force=False)\n            _autonomy_worker_once(force=False)\n        except Exception as exc:\n            print(f"[adaptive] worker warning: {exc}", flush=True)\n        time.sleep(ADAPTIVE_LOOP_SECONDS)\n'''
loop_new = '''        try:\n            _adaptive_worker_once(force=False)\n            _autonomy_worker_once(force=False)\n            _initiative_worker_once(force=False)\n        except Exception as exc:\n            print(f"[adaptive] worker warning: {exc}", flush=True)\n        time.sleep(ADAPTIVE_LOOP_SECONDS)\n'''
if loop_old not in text:
    raise SystemExit("v0.11.6: v0.11.5 adaptive/autonomy loop marker missing")
text = text.replace(loop_old, loop_new, 1)

# Feed operational self-model and recent autonomous work into ordinary cognition.
personal_marker = '    if adaptive_context:\n        dynamic_system += "\\n\\n" + adaptive_context\n'
if personal_marker not in text:
    raise SystemExit("v0.11.6: adaptive cognition context marker missing")
if "initiative_context = _initiative_context(message)" not in text:
    text = text.replace(
        personal_marker,
        personal_marker + '    initiative_context = _initiative_context(message)\n    if initiative_context:\n        dynamic_system += "\\n\\n" + initiative_context\n',
        1,
    )

# Authenticated inspection/test hooks. Automatic initiative does not depend on
# these endpoints; they exist so field diagnostics can verify what Vex decided.
get_marker = '        if parsed.path == "/autonomy/status":\n'
if get_marker not in text:
    raise SystemExit("v0.11.6: autonomy status marker missing")
if 'parsed.path == "/initiative/status"' not in text:
    text = text.replace(
        get_marker,
        '        if parsed.path == "/initiative/status":\n            self._json(200, _initiative_status())\n            return\n\n' + get_marker,
        1,
    )

post_marker = '        if parsed.path == "/autonomy/run":\n'
if post_marker not in text:
    raise SystemExit("v0.11.6: autonomy run marker missing")
if 'parsed.path == "/initiative/run"' not in text:
    text = text.replace(
        post_marker,
        '        if parsed.path == "/initiative/run":\n            result = _initiative_worker_once(force=True)\n            self._json(200 if result.get("ok") else 503, result)\n            return\n\n' + post_marker,
        1,
    )

for stale in [
    '"version": "0.10.8"', '"version": "0.10.9"', '"version": "0.11.0"',
    '"version": "0.11.2"', '"version": "0.11.3"', '"version": "0.11.3.1"',
    '"version": "0.11.3.2"', '"version": "0.11.3.3"', '"version": "0.11.4.0"',
    '"version": "0.11.5.0"'
]:
    text = text.replace(stale, '"version": "0.11.6.0"')

path.write_text(text, encoding="utf-8")
compile(text, str(path), "exec")

final = path.read_text(encoding="utf-8")
checks = [
    '"version": "0.11.6.0"',
    "INITIATIVE_GOALS",
    "INITIATIVE_ACTIONS",
    "CREATE TABLE IF NOT EXISTS initiative_goals",
    "CREATE TABLE IF NOT EXISTS initiative_events",
    "CREATE TABLE IF NOT EXISTS self_state",
    "def _initiative_self_snapshot(",
    "def _initiative_choose_action(",
    "def _initiative_execute(",
    "def _initiative_worker_once(",
    "def _initiative_context(",
    "_initiative_worker_once(force=False)",
    "initiative_context = _initiative_context(message)",
    'parsed.path == "/initiative/status"',
    'parsed.path == "/initiative/run"',
]
for marker in checks:
    if marker not in final:
        raise SystemExit(f"v0.11.6 verifier missing: {marker}")

print("Applied v0.11.6 persistent initiative + operational self-model engine")
