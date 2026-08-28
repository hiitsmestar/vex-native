#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
INSTALLER = Path("Tools/VexAgentRuntimeInstall.py")

bridge = BRIDGE.read_text(encoding="utf-8")
installer = INSTALLER.read_text(encoding="utf-8")

if '"version": "0.11.7.39"' not in bridge:
    raise SystemExit("v0.11.7.53 expected proven Bridge v0.11.7.39 identity")
if '"agent_runtime_bundle": "0.11.7.52"' not in bridge:
    raise SystemExit("v0.11.7.53 expected Agent Runtime bundle v0.11.7.52")
if 'BUNDLE_VERSION = "0.11.7.52"' not in installer:
    raise SystemExit("v0.11.7.53 expected installer v0.11.7.52")
for marker in [
    "LEARNING_DB",
    "def _learning_queue_topic(",
    "def _learning_context(",
    "ADAPTIVE_DB",
    "def _adaptive_open_gap(",
    "def _autonomy_public_research_topic(",
    "_BACKGROUND_COGNITION_LOCK",
    'name="VexAutonomousImprovement"',
]:
    if marker not in bridge:
        raise SystemExit(f"v0.11.7.53 required learning/autonomy foundation missing: {marker}")

insert_marker = "def _vex_background_services() -> None:\n"
if insert_marker not in bridge:
    raise SystemExit("v0.11.7.53 background-service anchor missing")

supervisor = r'''
# ---------------------------------------------------------------------------
# v0.11.7.53 Autonomous Learning Supervisor
#
# Turns the existing source-aware Learning Engine + adaptive gap detector into a
# persistent project-improvement loop. Internet evidence is technical evidence,
# never identity/persona/personal memory. Proposals are local artifacts only;
# installs, deletion, security changes, deployment and protected runtime changes
# always remain approval-gated.
# ---------------------------------------------------------------------------
PROJECT_LEARNING_ROOT = CONFIG_PATH.parent / "project-learning"
PROJECT_LEARNING_DB = PROJECT_LEARNING_ROOT / "vex-project-learning.sqlite3"
PROJECT_PROPOSAL_ROOT = PROJECT_LEARNING_ROOT / "proposals"
PROJECT_SUPERVISOR_IDLE_SECONDS = 180
PROJECT_SUPERVISOR_LOOP_SECONDS = 75
PROJECT_SUPERVISOR_RETRY_BASE = 300
PROJECT_SUPERVISOR_MAX_ATTEMPTS = 6
_PROJECT_DB_LOCK = threading.RLock()
_PROJECT_LAST_FOREGROUND = time.time()


def _project_conn():
    import sqlite3
    PROJECT_LEARNING_ROOT.mkdir(parents=True, exist_ok=True)
    PROJECT_PROPOSAL_ROOT.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(PROJECT_LEARNING_DB), timeout=12, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS project_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            source_gap_id INTEGER NOT NULL DEFAULT 0,
            goal TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT 'capability',
            public_topic TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'queued',
            attempts INTEGER NOT NULL DEFAULT 0,
            next_run REAL NOT NULL DEFAULT 0,
            last_error TEXT NOT NULL DEFAULT '',
            UNIQUE(source_gap_id, goal)
        );
        CREATE TABLE IF NOT EXISTS evidence_receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            retrieved_at REAL NOT NULL,
            source_url TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            snippet TEXT NOT NULL DEFAULT '',
            confidence REAL NOT NULL DEFAULT 0,
            source_count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(task_id, source_url)
        );
        CREATE TABLE IF NOT EXISTS project_proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            summary TEXT NOT NULL,
            component TEXT NOT NULL,
            files_json TEXT NOT NULL DEFAULT '[]',
            patch_plan TEXT NOT NULL DEFAULT '',
            tests_json TEXT NOT NULL DEFAULT '[]',
            evidence_json TEXT NOT NULL DEFAULT '[]',
            risk TEXT NOT NULL DEFAULT 'medium',
            approval_required INTEGER NOT NULL DEFAULT 1,
            confidence REAL NOT NULL DEFAULT 0,
            artifact_path TEXT NOT NULL DEFAULT '',
            validation TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'staged'
        );
        CREATE INDEX IF NOT EXISTS idx_project_tasks_status ON project_tasks(status, next_run, updated_at);
        CREATE INDEX IF NOT EXISTS idx_project_evidence_task ON evidence_receipts(task_id, retrieved_at);
        CREATE INDEX IF NOT EXISTS idx_project_proposals_status ON project_proposals(status, updated_at);
        """
    )
    conn.commit()
    return conn


def _project_redact_for_artifact(value: str) -> str:
    """Redact secrets/private network and user-path material before artifact output."""
    text = str(value or "")
    patterns = [
        (r"(?i)(token|pin|password|secret|authorization)\s*[=:]\s*[^\s&;,]+", r"\1=[redacted]"),
        (r"(?i)([?&](?:token|pin|key|secret)=)[^&\s]+", r"\1[redacted]"),
        (r"\b(?:10\.|127\.|169\.254\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.)\d{1,3}\.\d{1,3}\b", "[private-ip]"),
        (r"(?i)\b[A-Z]:\\Users\\[^\\\s]+\\[^\s\"']+", "[private-user-path]"),
        (r"(?i)\b/Users/[^/\s]+/[^\s\"']+", "[private-user-path]"),
    ]
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text)
    return text[:16000]


def _project_risk_classification(value: str) -> tuple[str, bool]:
    low = str(value or "").lower()
    protected = [
        "install", "uninstall", "delete", "remove files", "format", "registry", "firewall",
        "certificate", "token", "password", "security setting", "permission", "deploy", "release",
        "merge", "main branch", "master branch", "stable branch", "production", "running runtime",
        "field runtime", "self-update", "overwrite executable", "force push", "git push --force",
    ]
    medium = ["dependency", "workflow", "github actions", "network", "bridge", "memory schema", "database migration"]
    if any(term in low for term in protected):
        return "high", True
    if any(term in low for term in medium):
        return "medium", True
    return "low", False


def _project_safe_test_command(value: str) -> bool:
    """Only non-mutating local validation commands may be suggested as auto-runnable."""
    cmd = re.sub(r"\s+", " ", str(value or "")).strip()
    if not cmd or len(cmd) > 500:
        return False
    if any(x in cmd for x in ["&&", "||", ";", "|", ">", "<", "`", "$(`"]):
        return False
    allowed_prefixes = (
        "python -m py_compile ",
        "python Tools/test_",
        "python Tools/ci_",
        "git diff --check",
        "git status --short",
    )
    return cmd.startswith(allowed_prefixes)


def _project_public_topic(category: str, goal: str, detail: str) -> str:
    """Generate only a generic technical public-web topic; raw private text stays local."""
    try:
        topic = _autonomy_public_research_topic(category, goal, detail)
    except Exception:
        topic = ""
    topic = re.sub(r"\s+", " ", str(topic or "")).strip()[:700]
    if not topic:
        return ""
    # Fail closed if a supposedly-public topic still contains obvious private material.
    scrubbed = _project_redact_for_artifact(topic)
    if scrubbed != topic or "[private-" in scrubbed or "[redacted]" in scrubbed:
        return ""
    return topic


def _project_queue_task(goal: str, category: str = "capability", detail: str = "", source_gap_id: int = 0) -> dict:
    goal = re.sub(r"\s+", " ", str(goal or "")).strip()[:1600]
    detail = re.sub(r"\s+", " ", str(detail or "")).strip()[:2400]
    category = re.sub(r"[^a-z0-9_-]", "", str(category or "capability").lower())[:50] or "capability"
    if len(goal) < 8:
        return {"ok": False, "detail": "project goal is too short"}
    if category in {"preference", "naturalness", "conversation", "identity", "relationship"}:
        return {"ok": False, "detail": "personal/identity learning stays local and outside project internet learning"}
    public_topic = _project_public_topic(category, goal, detail)
    now = time.time()
    try:
        with _PROJECT_DB_LOCK:
            conn = _project_conn()
            row = conn.execute(
                "SELECT id,status FROM project_tasks WHERE source_gap_id=? AND goal=? ORDER BY id DESC LIMIT 1",
                (int(source_gap_id or 0), goal),
            ).fetchone()
            if row is None:
                cur = conn.execute(
                    """INSERT INTO project_tasks(created_at,updated_at,source_gap_id,goal,detail,category,public_topic,status,attempts,next_run,last_error)
                       VALUES (?,?,?,?,?,?,?,?,0,0,'')""",
                    (now, now, int(source_gap_id or 0), goal, detail, category, public_topic, "research" if public_topic else "queued"),
                )
                task_id = int(cur.lastrowid)
            else:
                task_id = int(row["id"])
                conn.execute(
                    "UPDATE project_tasks SET updated_at=?,detail=?,category=?,public_topic=?,status=CASE WHEN status IN ('done','ready-for-review') THEN status ELSE ? END WHERE id=?",
                    (now, detail, category, public_topic, "research" if public_topic else "queued", task_id),
                )
            conn.commit()
            conn.close()
        if public_topic:
            try:
                _learning_queue_topic(public_topic, reason="project-autolearn", priority=82)
            except Exception:
                pass
        return {"ok": True, "task_id": task_id, "public_topic": public_topic}
    except Exception as exc:
        return {"ok": False, "detail": f"project queue failed: {exc}"}


def _project_seed_from_adaptive_gap() -> dict:
    try:
        with _ADAPTIVE_DB_LOCK:
            conn = _adaptive_conn()
            gap = conn.execute(
                """SELECT * FROM gaps
                   WHERE status='open' AND category NOT IN ('preference','naturalness','conversation','identity','relationship')
                   ORDER BY priority DESC, updated_at ASC LIMIT 1"""
            ).fetchone()
            conn.close()
    except Exception as exc:
        return {"ok": False, "detail": f"adaptive gap read failed: {exc}"}
    if gap is None:
        return {"ok": True, "detail": "no project-capability gap waiting"}
    return _project_queue_task(
        str(gap["request_text"] or ""),
        str(gap["category"] or "capability"),
        str(gap["detail"] or ""),
        int(gap["id"]),
    )


def _project_learning_evidence(public_topic: str, task_id: int) -> dict:
    """Read source-backed Learning Engine notes; never read personal Memory Worker rows."""
    topic_tokens = set(re.findall(r"[a-z0-9][a-z0-9_+-]{2,}", str(public_topic or "").lower()))
    best = None
    best_score = -1
    try:
        with _LEARNING_DB_LOCK:
            conn = _learning_conn()
            rows = conn.execute(
                "SELECT topic,summary,confidence,source_count,sources_json,refreshed_at,expires_at FROM notes ORDER BY refreshed_at DESC LIMIT 80"
            ).fetchall()
            conn.close()
        for row in rows:
            if int(row["source_count"] or 0) < 1:
                continue
            row_tokens = set(re.findall(r"[a-z0-9][a-z0-9_+-]{2,}", (str(row["topic"] or "") + " " + str(row["summary"] or "")).lower()))
            overlap = len(topic_tokens & row_tokens)
            score = overlap * 10 + float(row["confidence"] or 0)
            if score > best_score and (overlap > 0 or not topic_tokens):
                best = row
                best_score = score
    except Exception as exc:
        return {"ok": False, "detail": f"learning evidence read failed: {exc}"}
    if best is None:
        return {"ok": False, "detail": "source-backed technical evidence is not ready yet"}
    try:
        sources = json.loads(str(best["sources_json"] or "[]"))
    except Exception:
        sources = []
    if not isinstance(sources, list) or not sources:
        return {"ok": False, "detail": "learning note has no source receipts"}

    receipts = []
    now = time.time()
    try:
        with _PROJECT_DB_LOCK:
            conn = _project_conn()
            for item in sources[:8]:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url") or "").strip()[:1500]
                if not url.startswith("https://"):
                    continue
                title = _project_redact_for_artifact(str(item.get("title") or ""))[:400]
                snippet = _project_redact_for_artifact(str(item.get("snippet") or ""))[:2600]
                conn.execute(
                    """INSERT INTO evidence_receipts(task_id,retrieved_at,source_url,title,snippet,confidence,source_count)
                       VALUES (?,?,?,?,?,?,?) ON CONFLICT(task_id,source_url) DO UPDATE SET
                       retrieved_at=excluded.retrieved_at,title=excluded.title,snippet=excluded.snippet,
                       confidence=excluded.confidence,source_count=excluded.source_count""",
                    (int(task_id), float(best["refreshed_at"] or now), url, title, snippet, float(best["confidence"] or 0), int(best["source_count"] or 0)),
                )
                receipts.append({"url": url, "title": title, "retrieved_at": float(best["refreshed_at"] or now)})
            conn.commit()
            conn.close()
    except Exception as exc:
        return {"ok": False, "detail": f"evidence receipt store failed: {exc}"}
    if not receipts:
        return {"ok": False, "detail": "no HTTPS evidence receipts survived validation"}
    return {
        "ok": True,
        "summary": str(best["summary"] or "")[:9000],
        "confidence": float(best["confidence"] or 0),
        "source_count": int(best["source_count"] or 0),
        "receipts": receipts,
    }


def _project_local_proposal(task, evidence: dict) -> dict:
    model = _choose_ollama_model()
    if not model:
        return {"ok": False, "detail": "no local Ollama model available for project planning"}
    prompt = f"""You are VexNative's local autonomous software-learning supervisor.

LOCAL PROJECT GAP (never send this raw text to public web search):
CATEGORY: {str(task['category'])[:80]}
GOAL: {str(task['goal'])[:1600]}
DETAIL: {str(task['detail'])[:2400]}

SOURCE-GROUNDED PUBLIC TECHNICAL EVIDENCE:
{str(evidence.get('summary') or '')[:9000]}
SOURCES: {json.dumps(evidence.get('receipts') or [], ensure_ascii=False)[:7000]}

Design a conservative improvement proposal for VexNative. This is a proposal artifact, not permission to modify the running system. Do not invent test results. Do not include tokens, IPs, private user paths, private biography, relationship facts, or raw conversations.

Return strict JSON only:
{{
  "component": "short component",
  "summary": "what should improve and why",
  "files": ["likely repo/path.py"],
  "patch_plan": "specific implementation plan; code-like detail is fine but do not claim applied",
  "tests": ["python -m py_compile path.py", "python Tools/test_name.py"],
  "risk": "low|medium|high",
  "confidence": 0.0
}}
"""
    try:
        import requests
        with _BACKGROUND_COGNITION_LOCK:
            response = requests.post(
                f"{OLLAMA_BASE}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "Use only supplied evidence and installed-project context. Return strict JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "think": False,
                    "format": "json",
                    "keep_alive": "20m",
                    "options": {"temperature": 0.06, "top_p": 0.68, "num_ctx": 4096, "num_predict": 850},
                },
                timeout=165,
            )
        response.raise_for_status()
        payload = response.json()
        raw = _strip_reasoning_markup(str(((payload.get("message") or {}).get("content")) or "")).strip()
        data = json.loads(raw) if raw else {}
        if not isinstance(data, dict):
            raise ValueError("proposal JSON is not an object")
        return {"ok": True, "proposal": data}
    except Exception as exc:
        return {"ok": False, "detail": f"local project proposal deferred: {exc}"}


def _project_store_proposal(task, evidence: dict, proposal: dict) -> dict:
    import hashlib
    component = _project_redact_for_artifact(str(proposal.get("component") or task["category"]))[:160]
    summary = _project_redact_for_artifact(str(proposal.get("summary") or "")).strip()[:5000]
    patch_plan = _project_redact_for_artifact(str(proposal.get("patch_plan") or "")).strip()[:12000]
    files = [_project_redact_for_artifact(str(x)).strip()[:500] for x in (proposal.get("files") or []) if str(x).strip()][:12]
    tests = [_project_redact_for_artifact(str(x)).strip()[:600] for x in (proposal.get("tests") or []) if str(x).strip()][:12]
    if len(summary) < 20 or len(patch_plan) < 20:
        return {"ok": False, "detail": "proposal is too weak to stage"}
    try:
        model_confidence = max(0.0, min(1.0, float(proposal.get("confidence") or 0)))
    except Exception:
        model_confidence = 0.0
    evidence_confidence = max(0.0, min(1.0, float(evidence.get("confidence") or 0)))
    confidence = min(model_confidence, evidence_confidence if evidence_confidence else model_confidence)
    combined = " ".join([component, summary, patch_plan] + files + tests)
    risk, approval_required = _project_risk_classification(combined)
    declared = str(proposal.get("risk") or "").lower()
    if declared == "high":
        risk, approval_required = "high", True
    elif declared == "medium" and risk == "low":
        risk, approval_required = "medium", True
    safe_tests = [cmd for cmd in tests if _project_safe_test_command(cmd)]
    validation = {
        "source_backed": bool(evidence.get("receipts")),
        "source_count": int(evidence.get("source_count") or 0),
        "privacy_scrubbed": True,
        "safe_test_count": len(safe_tests),
        "all_tests_allowlisted": len(safe_tests) == len(tests),
        "executable_changes_applied": False,
        "remote_push_performed": False,
    }
    status = "ready-for-review" if confidence >= 0.62 and validation["source_backed"] else "staged"
    if approval_required:
        status = "approval-required"

    artifact = {
        "schema": "vex-project-proposal-v1",
        "created_at": time.time(),
        "task_id": int(task["id"]),
        "component": component,
        "summary": summary,
        "files": files,
        "patch_plan": patch_plan,
        "tests": tests,
        "safe_tests": safe_tests,
        "risk": risk,
        "approval_required": bool(approval_required),
        "confidence": confidence,
        "evidence": evidence.get("receipts") or [],
        "validation": validation,
        "boundaries": {
            "personal_memory_mutated": False,
            "running_runtime_modified": False,
            "install_delete_security_deploy_require_approval": True,
        },
    }
    serialized = json.dumps(artifact, ensure_ascii=False, indent=2)
    scrubbed = _project_redact_for_artifact(serialized)
    if "[redacted]" in scrubbed or "[private-ip]" in scrubbed or "[private-user-path]" in scrubbed:
        # Redaction is acceptable, but only the scrubbed form may leave the DB into an artifact.
        serialized = scrubbed
    digest = hashlib.sha256(serialized.encode("utf-8", "ignore")).hexdigest()[:16]
    PROJECT_PROPOSAL_ROOT.mkdir(parents=True, exist_ok=True)
    artifact_path = PROJECT_PROPOSAL_ROOT / f"proposal-{int(task['id']):05d}-{digest}.json"
    artifact_path.write_text(serialized, encoding="utf-8")

    try:
        with _PROJECT_DB_LOCK:
            conn = _project_conn()
            cur = conn.execute(
                """INSERT INTO project_proposals(task_id,created_at,updated_at,summary,component,files_json,patch_plan,tests_json,evidence_json,risk,approval_required,confidence,artifact_path,validation,status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    int(task["id"]), time.time(), time.time(), summary, component,
                    json.dumps(files, ensure_ascii=False), patch_plan, json.dumps(tests, ensure_ascii=False),
                    json.dumps(evidence.get("receipts") or [], ensure_ascii=False), risk, 1 if approval_required else 0,
                    confidence, str(artifact_path), json.dumps(validation, ensure_ascii=False), status,
                ),
            )
            proposal_id = int(cur.lastrowid)
            conn.execute("UPDATE project_tasks SET status=?,updated_at=?,last_error='' WHERE id=?", (status, time.time(), int(task["id"])))
            conn.commit()
            conn.close()
        return {"ok": True, "proposal_id": proposal_id, "status": status, "risk": risk, "confidence": confidence}
    except Exception as exc:
        return {"ok": False, "detail": f"proposal database store failed: {exc}"}


def _project_next_task():
    now = time.time()
    try:
        with _PROJECT_DB_LOCK:
            conn = _project_conn()
            row = conn.execute(
                "SELECT * FROM project_tasks WHERE status IN ('queued','research','retry') AND next_run<=? ORDER BY updated_at ASC LIMIT 1",
                (now,),
            ).fetchone()
            conn.close()
            return row
    except Exception:
        return None


def _project_retry(task, detail: str) -> dict:
    attempts = int(task["attempts"] or 0) + 1
    delay = min(12 * 3600, PROJECT_SUPERVISOR_RETRY_BASE * (2 ** min(attempts, 6)))
    status = "retry" if attempts < PROJECT_SUPERVISOR_MAX_ATTEMPTS else "blocked"
    try:
        with _PROJECT_DB_LOCK:
            conn = _project_conn()
            conn.execute(
                "UPDATE project_tasks SET status=?,attempts=?,next_run=?,updated_at=?,last_error=? WHERE id=?",
                (status, attempts, time.time() + delay, time.time(), str(detail)[:1600], int(task["id"])),
            )
            conn.commit()
            conn.close()
    except Exception:
        pass
    return {"ok": False, "task_id": int(task["id"]), "status": status, "detail": str(detail)[:500]}


def _project_supervisor_once(force: bool = False) -> dict:
    if not force and time.time() - _ADAPTIVE_LAST_FOREGROUND < PROJECT_SUPERVISOR_IDLE_SECONDS:
        return {"ok": True, "idle": False, "detail": "foreground activity is recent"}
    try:
        snap = _resource_snapshot()
        if bool(snap.get("art_running")) and not force:
            return {"ok": True, "idle": True, "detail": "art worker has priority"}
        available = int(snap.get("memory_available") or 0)
        if available and available < 1500 * 1024 * 1024 and not force:
            return {"ok": True, "idle": True, "detail": "memory pressure; project learning deferred"}
    except Exception:
        pass

    task = _project_next_task()
    if task is None:
        seeded = _project_seed_from_adaptive_gap()
        task = _project_next_task()
        if task is None:
            return {"ok": True, "idle": True, "detail": seeded.get("detail") or "project queue empty"}

    public_topic = str(task["public_topic"] or "").strip()
    if not public_topic:
        public_topic = _project_public_topic(str(task["category"]), str(task["goal"]), str(task["detail"]))
        if not public_topic:
            return _project_retry(task, "no privacy-safe public technical research topic")
        try:
            with _PROJECT_DB_LOCK:
                conn = _project_conn()
                conn.execute("UPDATE project_tasks SET public_topic=?,status='research',updated_at=? WHERE id=?", (public_topic, time.time(), int(task["id"])))
                conn.commit()
                conn.close()
            _learning_queue_topic(public_topic, reason="project-autolearn", priority=82)
        except Exception:
            pass
        return {"ok": True, "task_id": int(task["id"]), "detail": "queued source-grounded research"}

    evidence = _project_learning_evidence(public_topic, int(task["id"]))
    if not evidence.get("ok"):
        try:
            _learning_queue_topic(public_topic, reason="project-autolearn", priority=84)
        except Exception:
            pass
        return _project_retry(task, evidence.get("detail") or "technical evidence not ready")

    planned = _project_local_proposal(task, evidence)
    if not planned.get("ok"):
        return _project_retry(task, planned.get("detail") or "local proposal unavailable")
    stored = _project_store_proposal(task, evidence, planned.get("proposal") or {})
    if not stored.get("ok"):
        return _project_retry(task, stored.get("detail") or "proposal validation failed")
    return {"ok": True, "task_id": int(task["id"]), **stored}


def _project_supervisor_status() -> dict:
    result = {
        "ok": True,
        "version": "0.11.7.53",
        "mode": "autonomous-source-grounded-project-learning",
        "privacy": "internet evidence cannot mutate personal identity/relationship memory",
        "execution": "proposal-only; risky runtime/install/delete/security/deploy actions require approval",
        "worker_started": True,
        "worker_alive": True,
    }
    try:
        with _PROJECT_DB_LOCK:
            conn = _project_conn()
            result["tasks"] = int(conn.execute("SELECT COUNT(*) AS n FROM project_tasks").fetchone()["n"] or 0)
            result["pending"] = int(conn.execute("SELECT COUNT(*) AS n FROM project_tasks WHERE status IN ('queued','research','retry')").fetchone()["n"] or 0)
            result["proposals"] = int(conn.execute("SELECT COUNT(*) AS n FROM project_proposals").fetchone()["n"] or 0)
            result["ready_for_review"] = int(conn.execute("SELECT COUNT(*) AS n FROM project_proposals WHERE status='ready-for-review'").fetchone()["n"] or 0)
            result["approval_required"] = int(conn.execute("SELECT COUNT(*) AS n FROM project_proposals WHERE status='approval-required'").fetchone()["n"] or 0)
            recent = conn.execute(
                "SELECT id,task_id,component,risk,approval_required,confidence,status,updated_at FROM project_proposals ORDER BY id DESC LIMIT 8"
            ).fetchall()
            result["recent_proposals"] = [dict(row) for row in recent]
            conn.close()
    except Exception as exc:
        result = {"ok": False, "version": "0.11.7.53", "error": str(exc)[:300]}
    return result


def _project_supervisor_loop() -> None:
    time.sleep(120)
    while True:
        try:
            _project_supervisor_once(force=False)
        except Exception as exc:
            print(f"[project-learning] worker warning: {exc}", flush=True)
        time.sleep(PROJECT_SUPERVISOR_LOOP_SECONDS)


'''

if "def _project_supervisor_once(" not in bridge:
    bridge = bridge.replace(insert_marker, supervisor + insert_marker, 1)

# Start beside the proven background graph. The worker self-defers under foreground
# activity, art load and memory pressure, and shares the existing local-model lock.
service_anchor = "def _vex_background_services() -> None:\n"
thread_line = '    threading.Thread(target=_project_supervisor_loop, daemon=True, name="VexAutonomousLearningSupervisor").start()\n'
if thread_line not in bridge:
    if service_anchor not in bridge:
        raise SystemExit("v0.11.7.53 service startup anchor missing after supervisor insertion")
    bridge = bridge.replace(service_anchor, service_anchor + thread_line, 1)

# Authenticated Bridge diagnostics/control routes. Add before the existing adaptive
# routes so older diagnostics remain untouched.
get_anchor = '        if parsed.path == "/adaptive/status":\n'
get_route = '''        if parsed.path == "/autolearn/status":\n            status = _project_supervisor_status()\n            self._json(200 if status.get("ok") else 503, status)\n            return\n\n        if parsed.path == "/autolearn/proposals":\n            status = _project_supervisor_status()\n            self._json(200 if status.get("ok") else 503, status)\n            return\n\n'''
if 'parsed.path == "/autolearn/status"' not in bridge:
    if get_anchor not in bridge:
        raise SystemExit("v0.11.7.53 adaptive GET route anchor missing")
    bridge = bridge.replace(get_anchor, get_route + get_anchor)

post_anchor = '        if parsed.path == "/adaptive/run":\n'
post_route = r'''        if parsed.path == "/autolearn/run":
            result = _project_supervisor_once(force=True)
            self._json(200 if result.get("ok") else 503, result)
            return

        if parsed.path == "/autolearn/queue":
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length <= 0 or length > 80_000:
                    self._json(400, {"ok": False, "error": "invalid project-learning payload"})
                    return
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                result = _project_queue_task(
                    str(payload.get("goal") or ""),
                    str(payload.get("category") or "capability"),
                    str(payload.get("detail") or ""),
                    0,
                )
                self._json(200 if result.get("ok") else 400, result)
            except Exception as exc:
                self._json(500, {"ok": False, "error": f"project-learning queue failed: {exc}"})
            return

'''
if 'parsed.path == "/autolearn/run"' not in bridge:
    if post_anchor not in bridge:
        raise SystemExit("v0.11.7.53 adaptive POST route anchor missing")
    bridge = bridge.replace(post_anchor, post_route + post_anchor, 1)

# Bundle identity only. Protocol stays field-proven at Bridge 0.11.7.39.
bridge = bridge.replace('"agent_runtime_bundle": "0.11.7.52"', '"agent_runtime_bundle": "0.11.7.53"', 1)
installer = installer.replace('BUNDLE_VERSION = "0.11.7.52"', 'BUNDLE_VERSION = "0.11.7.53"', 1)
installer = installer.replace("Vex Agent Runtime v0.11.7.52 installed.", "Vex Agent Runtime v0.11.7.53 installed.", 1)

BRIDGE.write_text(bridge, encoding="utf-8")
INSTALLER.write_text(installer, encoding="utf-8")
compile(bridge, str(BRIDGE), "exec")
compile(installer, str(INSTALLER), "exec")

required = [
    "PROJECT_LEARNING_DB",
    "evidence_receipts",
    "project_proposals",
    "def _project_redact_for_artifact(",
    "def _project_risk_classification(",
    "def _project_safe_test_command(",
    "def _project_learning_evidence(",
    "def _project_supervisor_once(",
    'name="VexAutonomousLearningSupervisor"',
    'parsed.path == "/autolearn/status"',
    'parsed.path == "/autolearn/run"',
    'parsed.path == "/autolearn/queue"',
    '"agent_runtime_bundle": "0.11.7.53"',
    '"version": "0.11.7.39"',
]
for marker in required:
    if marker not in bridge:
        raise SystemExit(f"v0.11.7.53 Bridge marker missing: {marker}")
if 'BUNDLE_VERSION = "0.11.7.53"' not in installer:
    raise SystemExit("v0.11.7.53 installer marker missing")

# Internet/project learning must remain separate from authoritative personal-memory
# mutation. The .53 supervisor source itself must never call Memory Worker import/sync.
layer_start = bridge.find("# v0.11.7.53 Autonomous Learning Supervisor")
layer_end = bridge.find("def _vex_background_services() -> None:", layer_start)
layer = bridge[layer_start:layer_end]
for forbidden in ['_memory_post("/import"', '_memory_post("/sync"', 'api.openai.com', 'OPENAI_API_KEY']:
    if forbidden in layer:
        raise SystemExit(f"v0.11.7.53 privacy/no-cost boundary violated: {forbidden}")

print("Applied v0.11.7.53 autonomous source-grounded project-learning supervisor")
