#!/usr/bin/env python3
from pathlib import Path

path = Path("Bridge/vex_bridge.py")
text = path.read_text(encoding="utf-8")


def replace_function(source: str, name: str, replacement: str) -> str:
    start = source.find(f"def {name}(")
    if start < 0:
        raise SystemExit(f"v0.11.5: missing function {name}")
    end = source.find("\n\ndef ", start + 10)
    if end < 0:
        raise SystemExit(f"v0.11.5: could not find end of function {name}")
    return source[:start] + replacement.rstrip() + source[end:]


# ---------------------------------------------------------------------------
# 1) Stop using a growing keyword list as the normal personal-memory router.
# Explicit memory audits keep the verified fail-closed fast path; ordinary
# conversation flows through normal PC cognition, which already receives semantic
# personal-memory grounding plus adaptive learned context on every turn.
# ---------------------------------------------------------------------------
new_recall = r'''def _personal_memory_fact_question(message: str) -> bool:
    lower = " " + str(message or "").lower().replace("’", "'").strip() + " "
    if not lower.strip():
        return False
    recall_words = (" remember", " memory", " memories", " know about me", " know about us")
    personal_words = (" me ", " my ", " us ", " our ", " relationship", " girlfriend", " star")
    return any(word in lower for word in recall_words) and any(word in lower for word in personal_words)
'''
text = replace_function(text, "_personal_memory_fact_question", new_recall)


insert_marker = "def _vex_background_services() -> None:\n"
if insert_marker not in text:
    raise SystemExit("v0.11.5: background service marker missing")

self_improvement = r'''
# ---------------------------------------------------------------------------
# v0.11.5 Autonomous Self-Improvement Layer
#
# This layer turns the existing pieces into one idle learning loop:
# - introspect and rehearse known local capabilities without side effects
# - use private saved memory locally to improve behavior, never as a public query
# - send only sanitized technical topics to public-web research
# - trigger bounded existing repairs for unhealthy components
# - stage source-grounded upgrade candidates with acceptance tests
#
# Learned data/skills may promote automatically through existing validators.
# Code/binary upgrades are staged, not blindly installed into the running process.
# ---------------------------------------------------------------------------
AUTONOMY_IDLE_SECONDS = 150
AUTONOMY_FEATURE_INTERVAL = 180
AUTONOMY_SKILL_REHEARSAL_INTERVAL = 900
AUTONOMY_UPGRADE_INTERVAL = 1200
_AUTONOMY_LAST_FEATURE = 0.0
_AUTONOMY_LAST_SKILLS = 0.0
_AUTONOMY_LAST_UPGRADE = 0.0

AUTONOMY_CAPABILITIES = {
    "personal_memory": {
        "cue": "history continuity preferences personal facts previous conversations",
        "guidance": "Use persistent personal-memory retrieval as semantic working context during ordinary conversation. Current explicit input outranks stale memory; never invent a missing fact.",
        "research": "semantic personal memory retrieval ranking sqlite fts conversational assistant architecture",
    },
    "local_cognition": {
        "cue": "reason answer explain converse decide interpret intent",
        "guidance": "Use the strongest healthy local cognition model that fits current resource pressure; do not route ordinary conversation through rigid keyword handlers when cognition can interpret intent.",
        "research": "resource aware local llm routing windows ollama low memory inference reliability",
    },
    "web_research": {
        "cue": "research current documentation internet public sources learn investigate",
        "guidance": "Use source-grounded public research for changing or technical information, retain source/date/confidence, and keep private personal-memory text out of public search queries.",
        "research": "source grounded autonomous research agent provenance confidence stale knowledge refresh",
    },
    "learned_skills": {
        "cue": "open launch run workflow computer tool action automation",
        "guidance": "Prefer validated learned skills and compiled safe workflows for PC actions; reuse successful recipes and never claim execution unless the tool result confirms it.",
        "research": "safe tool use agent workflow validation allowlisted actions reliability",
    },
    "self_repair": {
        "cue": "failed timeout broken repair restart unhealthy service recover",
        "guidance": "When a known local component is unhealthy, use bounded self-repair first, respect circuit breakers, preserve personal data, then research recurring failures instead of repeatedly retrying blindly.",
        "research": "self healing local service supervisor circuit breaker repair observability windows application",
    },
    "art_worker": {
        "cue": "image art render picture visual generate edit",
        "guidance": "Route image work to the independent Art Worker so rendering cannot block conversation, memory, Bridge, or diagnostics; respect low-memory coordination.",
        "research": "comfyui cpu low memory worker process isolation windows image generation service",
    },
    "file_index": {
        "cue": "file folder document search index find local computer",
        "guidance": "Use the local file index for retrieval and refresh it when stale; do not fabricate file contents or paths that were not returned by a tool.",
        "research": "incremental local file indexing search reliability stale index refresh windows python",
    },
}


def _autonomy_ensure_tables(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS capabilities (
            name TEXT PRIMARY KEY,
            updated_at REAL NOT NULL,
            last_tested REAL NOT NULL DEFAULT 0,
            last_researched REAL NOT NULL DEFAULT 0,
            confidence REAL NOT NULL DEFAULT 0,
            successes INTEGER NOT NULL DEFAULT 0,
            failures INTEGER NOT NULL DEFAULT 0,
            healthy INTEGER NOT NULL DEFAULT 0,
            detail TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS upgrade_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            gap_id INTEGER NOT NULL DEFAULT 0,
            component TEXT NOT NULL,
            problem TEXT NOT NULL,
            proposal TEXT NOT NULL,
            acceptance_json TEXT NOT NULL DEFAULT '[]',
            evidence TEXT NOT NULL DEFAULT '',
            risk TEXT NOT NULL DEFAULT 'medium',
            confidence REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'staged'
        );
        CREATE INDEX IF NOT EXISTS idx_upgrade_status ON upgrade_candidates(status, confidence, updated_at);
        """
    )
    conn.commit()


def _autonomy_public_research_topic(category: str, request_text: str = "", detail: str = "") -> str:
    """Map a private/local gap to a generic public research topic.

    Raw conversation, saved-memory facts, paths, names, tokens, addresses and other
    private material are intentionally not sent to web search by this function.
    """
    category = str(category or "").lower()
    low = f"{request_text} {detail}".lower()
    if category in {"preference", "naturalness", "conversation"}:
        return ""
    if "memory" in category or "memory" in low or "sqlite" in low:
        return "semantic conversational memory retrieval ranking sqlite fts reliability"
    if "art" in low or "comfy" in low or "render" in low:
        return "ComfyUI Windows CPU low memory troubleshooting official documentation"
    if "ollama" in low or "cognition" in low or "model" in low:
        return "Ollama Windows local model service troubleshooting resource pressure documentation"
    if "index" in low or "file" in low:
        return "reliable incremental local file indexing refresh failure recovery Windows Python"
    if "skill" in low or "tool" in category or "workflow" in low:
        return "safe agent tool workflow validation retries idempotency capability routing"
    if "network" in low or "bridge" in low or "http" in low or "tls" in low:
        return "local HTTPS service bridge timeout recovery Windows Python requests TLS"
    if "repair" in category or "repair" in low or "crash" in low or "timeout" in low:
        return "self healing application supervisor circuit breaker diagnostics repair Windows service"
    if category in {"routing", "capability"}:
        return "adaptive agent intent routing capability selection semantic tool use local LLM"
    return ""


def _autonomy_probe_capability(name: str) -> tuple[bool, str]:
    try:
        if name == "personal_memory":
            health = _memory_worker_health(start_if_needed=True)
            return bool(health.get("ok")), f"worker={health.get('version') or 'unknown'}"
        if name == "local_cognition":
            model = _choose_ollama_model()
            return bool(model), f"model={model or 'none'}"
        if name == "web_research":
            return callable(globals().get("web_search")), "web_search available" if callable(globals().get("web_search")) else "web_search missing"
        if name == "learned_skills":
            data = _load_skills()
            skills = data.get("skills") if isinstance(data, dict) else []
            return isinstance(skills, list), f"saved_skills={len(skills or [])}"
        if name == "self_repair":
            status = _sr_status()
            return bool(status.get("ok")), "supervisor available"
        if name == "art_worker":
            installed = bool(globals().get("_sr_art_installed") and _sr_art_installed())
            if not installed:
                return True, "art worker not installed on this node"
            healthy = bool(_art_comfy_health(timeout=0.6)) if callable(globals().get("_art_comfy_health")) else False
            return healthy, "healthy" if healthy else "installed but not answering"
        if name == "file_index":
            index = getattr(STATE, "index", None) if STATE is not None else None
            if index is None:
                return False, "index unavailable"
            docs = len(getattr(index, "documents", []) or [])
            return docs > 0, f"indexed_files={docs}"
    except Exception as exc:
        return False, f"{exc.__class__.__name__}: {str(exc)[:180]}"
    return False, "unknown capability"


def _autonomy_update_capability(name: str, ok: bool, detail: str) -> None:
    now = time.time()
    try:
        with _ADAPTIVE_DB_LOCK:
            conn = _adaptive_conn()
            _autonomy_ensure_tables(conn)
            row = conn.execute("SELECT * FROM capabilities WHERE name=?", (name,)).fetchone()
            successes = int((row["successes"] if row else 0) or 0) + (1 if ok else 0)
            failures = int((row["failures"] if row else 0) or 0) + (0 if ok else 1)
            total = max(1, successes + failures)
            confidence = min(0.99, max(0.15, successes / total))
            conn.execute(
                """INSERT INTO capabilities(name,updated_at,last_tested,last_researched,confidence,successes,failures,healthy,detail)
                   VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(name) DO UPDATE SET updated_at=excluded.updated_at,last_tested=excluded.last_tested,
                     confidence=excluded.confidence,successes=excluded.successes,failures=excluded.failures,
                     healthy=excluded.healthy,detail=excluded.detail""",
                (name, now, now, float(row["last_researched"] or 0) if row else 0.0, confidence, successes, failures, 1 if ok else 0, str(detail)[:900]),
            )
            conn.commit()
            conn.close()
    except Exception as exc:
        print(f"[autonomy] capability update warning: {exc}", flush=True)


def _autonomy_mark_researched(name: str) -> None:
    try:
        with _ADAPTIVE_DB_LOCK:
            conn = _adaptive_conn()
            _autonomy_ensure_tables(conn)
            conn.execute("UPDATE capabilities SET last_researched=?, updated_at=? WHERE name=?", (time.time(), time.time(), name))
            conn.commit()
            conn.close()
    except Exception:
        pass


def _autonomy_seed_capability_lessons() -> None:
    for name, spec in AUTONOMY_CAPABILITIES.items():
        try:
            _adaptive_store_lesson("capability", spec["cue"], spec["guidance"], 0.96, f"installed capability: {name}")
        except Exception:
            pass


def _autonomy_next_capability() -> str | None:
    try:
        with _ADAPTIVE_DB_LOCK:
            conn = _adaptive_conn()
            _autonomy_ensure_tables(conn)
            for name in AUTONOMY_CAPABILITIES:
                conn.execute(
                    "INSERT OR IGNORE INTO capabilities(name,updated_at,last_tested,last_researched,confidence,successes,failures,healthy,detail) VALUES (?,?,?,?,?,?,?,?,?)",
                    (name, time.time(), 0.0, 0.0, 0.0, 0, 0, 0, "not tested"),
                )
            row = conn.execute("SELECT name FROM capabilities ORDER BY last_tested ASC, confidence ASC LIMIT 1").fetchone()
            conn.commit()
            conn.close()
            return str(row["name"]) if row else None
    except Exception:
        return None


def _autonomy_feature_curriculum_once() -> dict:
    _autonomy_seed_capability_lessons()
    name = _autonomy_next_capability()
    if not name:
        return {"ok": True, "detail": "no capability due"}
    ok, detail = _autonomy_probe_capability(name)
    _autonomy_update_capability(name, ok, detail)
    spec = AUTONOMY_CAPABILITIES.get(name) or {}

    # Research each installed feature occasionally, and research failures sooner.
    should_research = not ok
    try:
        with _ADAPTIVE_DB_LOCK:
            conn = _adaptive_conn()
            _autonomy_ensure_tables(conn)
            row = conn.execute("SELECT last_researched FROM capabilities WHERE name=?", (name,)).fetchone()
            last = float(row["last_researched"] or 0) if row else 0.0
            conn.close()
            if time.time() - last > 7 * 86400:
                should_research = True
    except Exception:
        pass
    if should_research and spec.get("research"):
        try:
            if _learning_queue_topic(spec["research"], reason="feature-curriculum", priority=76 if not ok else 36):
                _autonomy_mark_researched(name)
        except Exception:
            pass

    if not ok:
        _adaptive_open_gap(f"local capability {name} is unhealthy", "repair", detail, 84)
        # Existing repair supervisor is bounded and has its own circuit breakers.
        try:
            _sr_run_once(force=False, include_art=False)
        except Exception:
            pass
    return {"ok": ok, "capability": name, "detail": detail}


def _autonomy_recipe_valid(recipe: dict) -> bool:
    if not isinstance(recipe, dict):
        return False
    primitive = str(recipe.get("primitive") or "")
    if primitive == "workflow":
        steps = recipe.get("steps") or []
        return isinstance(steps, list) and bool(steps) and len(steps) <= 6 and all(_autonomy_recipe_valid(step) for step in steps)
    validator = globals().get("_recipe_is_valid")
    if callable(validator):
        try:
            return bool(validator(recipe))
        except Exception:
            return False
    return primitive in set(globals().get("SAFE_SKILL_PRIMITIVES") or [])


def _autonomy_rehearse_skills() -> dict:
    try:
        data = _load_skills()
        skills = data.get("skills") if isinstance(data, dict) else []
        if not isinstance(skills, list):
            return {"ok": False, "detail": "skill store invalid"}
        checked = 0
        invalid = 0
        for skill in skills[:80]:
            recipe = skill.get("recipe") if isinstance(skill, dict) else None
            checked += 1
            if not _autonomy_recipe_valid(recipe):
                invalid += 1
        if invalid:
            _adaptive_open_gap("validate and repair learned skill recipes", "tool", f"invalid_recipes={invalid} checked={checked}", 72)
        return {"ok": invalid == 0, "checked": checked, "invalid": invalid}
    except Exception as exc:
        return {"ok": False, "detail": str(exc)[:240]}


def _autonomy_private_memory_guidance() -> str:
    # Local loopback retrieval only. This text is for the local Ollama reviewer and
    # is never passed to web_search or written into public research queries.
    try:
        return _personal_memory_grounding(
            "communication preferences interaction style VexNative project goals corrections continuity"
        )[:6000]
    except Exception:
        return ""


def _autonomy_stage_upgrade_candidate() -> dict:
    """Create a local, testable improvement candidate from an unresolved gap.

    The candidate is planning data only. It can guide a later validated source-code
    patch/build, but it does not overwrite the running executable.
    """
    try:
        with _ADAPTIVE_DB_LOCK:
            conn = _adaptive_conn()
            _autonomy_ensure_tables(conn)
            gap = conn.execute(
                "SELECT * FROM gaps WHERE status='open' AND category NOT IN ('preference','naturalness','conversation') ORDER BY priority DESC, updated_at ASC LIMIT 1"
            ).fetchone()
            if gap is None:
                conn.close()
                return {"ok": True, "detail": "no upgrade gap"}
            existing = conn.execute(
                "SELECT id FROM upgrade_candidates WHERE gap_id=? AND status IN ('staged','reviewed') ORDER BY id DESC LIMIT 1",
                (int(gap["id"]),),
            ).fetchone()
            if existing is not None:
                conn.close()
                return {"ok": True, "detail": "candidate already staged", "candidate_id": int(existing["id"])}
            conn.close()
    except Exception as exc:
        return {"ok": False, "detail": f"gap read failed: {exc}"}

    evidence = ""
    try:
        evidence = _learning_context(str(gap["request_text"]), limit=3)[:7000]
    except Exception:
        pass
    caps = _adaptive_capability_snapshot()
    model = _choose_ollama_model()
    if not model:
        return {"ok": False, "detail": "no local model for upgrade candidate"}

    prompt = f"""Design a conservative VexNative self-improvement candidate from this LOCAL capability gap.
GAP CATEGORY: {gap['category']}
PROBLEM: {str(gap['request_text'])[:1200]}
DETAIL: {str(gap['detail'])[:1200]}
INSTALLED CAPABILITIES: {json.dumps(caps, ensure_ascii=False)}
RETAINED TECHNICAL RESEARCH: {evidence}

Return strict JSON only:
{{"component":"short component","proposal":"specific change in behavior/data/skill/code architecture","acceptance_tests":["test 1","test 2"],"risk":"low|medium|high","confidence":0.0}}

Use only evidence above and known installed capabilities. Prefer data/skill/config improvements over code changes. If code change is needed, describe it and its tests but do not claim it has been applied. Never include personal-memory facts, secrets, local paths, tokens, addresses, or private conversation text."""
    try:
        import requests
        with _BACKGROUND_COGNITION_LOCK:
            response = requests.post(
                f"{OLLAMA_BASE}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "Produce a source-grounded local software improvement candidate as strict JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "think": False,
                    "format": "json",
                    "keep_alive": "20m",
                    "options": {"temperature": 0.05, "top_p": 0.65, "num_ctx": 4096, "num_predict": 520},
                },
                timeout=150,
            )
        response.raise_for_status()
        payload = response.json()
        raw = _strip_reasoning_markup(str(((payload.get("message") or {}).get("content")) or "")).strip()
        data = json.loads(raw) if raw else {}
        if not isinstance(data, dict):
            raise ValueError("candidate JSON is not an object")
    except Exception as exc:
        return {"ok": False, "detail": f"candidate synthesis deferred: {exc}"}

    component = re.sub(r"[^a-zA-Z0-9_. -]", "", str(data.get("component") or gap["category"]))[:120]
    proposal = re.sub(r"\s+", " ", str(data.get("proposal") or "")).strip()[:4000]
    tests = [re.sub(r"\s+", " ", str(x)).strip()[:500] for x in (data.get("acceptance_tests") or []) if str(x).strip()][:8]
    risk = str(data.get("risk") or "medium").lower()
    if risk not in {"low", "medium", "high"}:
        risk = "medium"
    try:
        confidence = max(0.0, min(1.0, float(data.get("confidence") or 0)))
    except Exception:
        confidence = 0.0
    if len(proposal) < 20 or confidence < 0.55:
        return {"ok": False, "detail": "candidate too weak to stage"}

    try:
        with _ADAPTIVE_DB_LOCK:
            conn = _adaptive_conn()
            _autonomy_ensure_tables(conn)
            cur = conn.execute(
                """INSERT INTO upgrade_candidates(created_at,updated_at,gap_id,component,problem,proposal,acceptance_json,evidence,risk,confidence,status)
                   VALUES (?,?,?,?,?,?,?,?,?,?, 'staged')""",
                (time.time(), time.time(), int(gap["id"]), component, str(gap["request_text"])[:1600], proposal,
                 json.dumps(tests, ensure_ascii=False), "retained-source-grounded-learning" if evidence else "local-gap-evidence", risk, confidence),
            )
            candidate_id = int(cur.lastrowid)
            conn.commit()
            conn.close()
        return {"ok": True, "candidate_id": candidate_id, "component": component, "risk": risk, "confidence": confidence}
    except Exception as exc:
        return {"ok": False, "detail": f"candidate store failed: {exc}"}


def _autonomy_status() -> dict:
    result = {"ok": True, "privacy": "private memory stays local; public research receives sanitized technical topics only"}
    try:
        with _ADAPTIVE_DB_LOCK:
            conn = _adaptive_conn()
            _autonomy_ensure_tables(conn)
            result["capabilities"] = [dict(row) for row in conn.execute(
                "SELECT name,last_tested,last_researched,confidence,successes,failures,healthy,detail FROM capabilities ORDER BY name"
            ).fetchall()]
            result["upgrade_candidates"] = int(conn.execute(
                "SELECT COUNT(*) AS n FROM upgrade_candidates WHERE status='staged'"
            ).fetchone()["n"] or 0)
            result["recent_upgrades"] = [dict(row) for row in conn.execute(
                "SELECT id,component,proposal,risk,confidence,status FROM upgrade_candidates ORDER BY id DESC LIMIT 5"
            ).fetchall()]
            conn.close()
    except Exception as exc:
        result = {"ok": False, "error": str(exc)[:300]}
    return result


def _autonomy_worker_once(force: bool = False) -> dict:
    global _AUTONOMY_LAST_FEATURE, _AUTONOMY_LAST_SKILLS, _AUTONOMY_LAST_UPGRADE
    now = time.time()
    if not force and now - _ADAPTIVE_LAST_FOREGROUND < AUTONOMY_IDLE_SECONDS:
        return {"ok": True, "idle": False, "detail": "foreground activity is recent"}
    try:
        snap = _resource_snapshot()
        if bool(snap.get("art_running")) and not force:
            return {"ok": True, "idle": True, "detail": "art worker has priority"}
        available = int(snap.get("memory_available") or 0)
        if available and available < 1500 * 1024 * 1024 and not force:
            return {"ok": True, "idle": True, "detail": "memory pressure; autonomy deferred"}
    except Exception:
        pass

    result = {"ok": True, "feature": None, "skills": None, "upgrade": None}
    if force or now - _AUTONOMY_LAST_FEATURE >= AUTONOMY_FEATURE_INTERVAL:
        _AUTONOMY_LAST_FEATURE = now
        result["feature"] = _autonomy_feature_curriculum_once()
    if force or now - _AUTONOMY_LAST_SKILLS >= AUTONOMY_SKILL_REHEARSAL_INTERVAL:
        _AUTONOMY_LAST_SKILLS = now
        result["skills"] = _autonomy_rehearse_skills()
    if force or now - _AUTONOMY_LAST_UPGRADE >= AUTONOMY_UPGRADE_INTERVAL:
        _AUTONOMY_LAST_UPGRADE = now
        result["upgrade"] = _autonomy_stage_upgrade_candidate()
    return result


'''

if "def _autonomy_worker_once(" not in text:
    text = text.replace(insert_marker, self_improvement + insert_marker, 1)


# ---------------------------------------------------------------------------
# 2) Privacy-correct gap research. Adaptive lessons may use private memory locally,
# but public research gets a generic technical topic instead of raw user text.
# ---------------------------------------------------------------------------
old_gap_research = '''    # Existing source-grounded learning engine researches unresolved capability gaps.\n    try:\n        _learning_queue_topic(request_text, reason="adaptive-gap", priority=max(45, min(90, int(priority))))\n    except Exception:\n        pass\n'''
new_gap_research = '''    # Source-grounded learning researches only sanitized public technical topics.\n    # Preference/naturalness learning remains local and never becomes a web query.\n    try:\n        public_topic = _autonomy_public_research_topic(category, request_text, detail)\n        if public_topic:\n            _learning_queue_topic(public_topic, reason="adaptive-gap", priority=max(45, min(90, int(priority))))\n    except Exception:\n        pass\n'''
if old_gap_research not in text:
    raise SystemExit("v0.11.5: adaptive gap research marker missing")
text = text.replace(old_gap_research, new_gap_research, 1)


# ---------------------------------------------------------------------------
# 3) Let the local idle reviewer use saved personal memory as private guidance.
# The text stays inside local Ollama and is explicitly prohibited from becoming a
# public research query or a biographical adaptive lesson.
# ---------------------------------------------------------------------------
review_marker = '''    caps = _adaptive_capability_snapshot()\n    transcript = []\n'''
review_new = '''    caps = _adaptive_capability_snapshot()\n    private_memory_guidance = _autonomy_private_memory_guidance()\n    transcript = []\n'''
if review_marker not in text:
    raise SystemExit("v0.11.5: adaptive model review marker missing")
text = text.replace(review_marker, review_new, 1)

prompt_marker = '''AVAILABLE LOCAL CAPABILITIES:\n{json.dumps(caps, ensure_ascii=False)}\n\nRECENT REAL EXCHANGES:\n'''
prompt_new = '''AVAILABLE LOCAL CAPABILITIES:\n{json.dumps(caps, ensure_ascii=False)}\n\nLOCAL PRIVATE MEMORY GUIDANCE (local model only; never copy biography into lessons or web queries):\n{private_memory_guidance}\n\nRECENT REAL EXCHANGES:\n'''
if prompt_marker not in text:
    raise SystemExit("v0.11.5: adaptive reviewer prompt marker missing")
text = text.replace(prompt_marker, prompt_new, 1)


# ---------------------------------------------------------------------------
# 4) Run the feature curriculum/rehearsal/upgrade staging from the same idle
# adaptive thread. This avoids another competing background model worker.
# ---------------------------------------------------------------------------
loop_old = '''        try:\n            _adaptive_worker_once(force=False)\n        except Exception as exc:\n            print(f"[adaptive] worker warning: {exc}", flush=True)\n        time.sleep(ADAPTIVE_LOOP_SECONDS)\n'''
loop_new = '''        try:\n            _adaptive_worker_once(force=False)\n            _autonomy_worker_once(force=False)\n        except Exception as exc:\n            print(f"[adaptive] worker warning: {exc}", flush=True)\n        time.sleep(ADAPTIVE_LOOP_SECONDS)\n'''
if loop_old not in text:
    raise SystemExit("v0.11.5: adaptive loop marker missing")
text = text.replace(loop_old, loop_new, 1)


# Authenticated diagnostics and deliberate force-run hook.
get_marker = '        if parsed.path == "/adaptive/status":\n'
if get_marker not in text:
    raise SystemExit("v0.11.5: adaptive status route missing")
if 'parsed.path == "/autonomy/status"' not in text:
    text = text.replace(
        get_marker,
        '        if parsed.path == "/autonomy/status":\n            self._json(200, _autonomy_status())\n            return\n\n' + get_marker,
        1,
    )

post_marker = '        if parsed.path == "/adaptive/run":\n'
if post_marker not in text:
    raise SystemExit("v0.11.5: adaptive run route missing")
if 'parsed.path == "/autonomy/run"' not in text:
    text = text.replace(
        post_marker,
        '        if parsed.path == "/autonomy/run":\n            result = _autonomy_worker_once(force=True)\n            self._json(200 if result.get("ok") else 503, result)\n            return\n\n' + post_marker,
        1,
    )


# Bridge version for field verification.
for stale in [
    '"version": "0.10.8"', '"version": "0.10.9"', '"version": "0.11.0"',
    '"version": "0.11.2"', '"version": "0.11.3"', '"version": "0.11.3.1"',
    '"version": "0.11.3.2"', '"version": "0.11.3.3"', '"version": "0.11.4.0"'
]:
    text = text.replace(stale, '"version": "0.11.5.0"')

path.write_text(text, encoding="utf-8")
compile(text, str(path), "exec")

final = path.read_text(encoding="utf-8")
checks = [
    '"version": "0.11.5.0"',
    "def _autonomy_worker_once(",
    "AUTONOMY_CAPABILITIES",
    "def _autonomy_public_research_topic(",
    "def _autonomy_private_memory_guidance(",
    "def _autonomy_stage_upgrade_candidate(",
    "CREATE TABLE IF NOT EXISTS capabilities",
    "CREATE TABLE IF NOT EXISTS upgrade_candidates",
    'parsed.path == "/autonomy/status"',
    'parsed.path == "/autonomy/run"',
    "_autonomy_worker_once(force=False)",
    "private_memory_guidance = _autonomy_private_memory_guidance()",
    "public_topic = _autonomy_public_research_topic",
]
for marker in checks:
    if marker not in final:
        raise SystemExit(f"v0.11.5 verifier missing: {marker}")

print("Applied v0.11.5 autonomous feature curriculum + private-memory adaptation + staged self-improvement")
