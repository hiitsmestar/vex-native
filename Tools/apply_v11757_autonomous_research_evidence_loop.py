#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
REMOTE = Path("Tools/VexRemoteSupport.py")
INSTALLER = Path("Tools/VexAgentRuntimeInstall.py")

bridge = BRIDGE.read_text(encoding="utf-8")
remote = REMOTE.read_text(encoding="utf-8")
installer = INSTALLER.read_text(encoding="utf-8")

for label, text, marker in [
    ("Bridge bundle", bridge, '"agent_runtime_bundle": "0.11.7.56"'),
    ("Autolearn guard", bridge, "PROJECT_PROPOSAL_PER_TASK_CAP = 6"),
    ("Evidence fingerprint", bridge, "def _project_v55_evidence_fingerprint_from_receipts("),
    ("Learning queue", bridge, "def _learning_queue_topic("),
    ("Learning research", bridge, "def _learning_research_topic("),
    ("Project supervisor", bridge, "def _project_supervisor_once("),
    ("Remote Support", remote, 'VERSION = "0.11.7.56"'),
    ("Installer", installer, 'BUNDLE_VERSION = "0.11.7.56"'),
]:
    if marker not in text:
        raise SystemExit(f"v0.11.7.57 expected {label} marker missing: {marker}")

bridge = bridge.replace('"agent_runtime_bundle": "0.11.7.56"', '"agent_runtime_bundle": "0.11.7.57"', 1)

anchor = "def _vex_background_services() -> None:\n"
if anchor not in bridge:
    raise SystemExit("v0.11.7.57 Bridge insertion anchor missing")

layer = r'''
# ---------------------------------------------------------------------------
# v0.11.7.57 Autonomous Research Evidence Loop
#
# Closes the observable handoff between an adaptive project gap and the existing
# source-grounded Learning Engine. The Learning Engine remains the only public-web
# researcher and already deduplicates normalized topics. This layer adds a local,
# project-linked research-job ledger, source-backed note receipts, material-evidence
# change tracking, and sanitized counters. Personal memory is never a research
# source and public evidence can never overwrite identity/relationship memory.
# ---------------------------------------------------------------------------
PROJECT_RESEARCH_REQUEUE_SECONDS = 30 * 60


def _project_v57_ensure_schema(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS project_research_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL UNIQUE,
            public_topic TEXT NOT NULL,
            norm TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            enqueued_count INTEGER NOT NULL DEFAULT 0,
            deduped_count INTEGER NOT NULL DEFAULT 0,
            completed_count INTEGER NOT NULL DEFAULT 0,
            evidence_changed_count INTEGER NOT NULL DEFAULT 0,
            evidence_unchanged_count INTEGER NOT NULL DEFAULT 0,
            evidence_fingerprint TEXT NOT NULL DEFAULT '',
            source_count INTEGER NOT NULL DEFAULT 0,
            note_id INTEGER NOT NULL DEFAULT 0,
            last_error TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            completed_at REAL NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS project_research_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            job_id INTEGER NOT NULL,
            evidence_fingerprint TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            sources_json TEXT NOT NULL DEFAULT '[]',
            confidence REAL NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            UNIQUE(task_id, evidence_fingerprint)
        );
        CREATE INDEX IF NOT EXISTS idx_project_research_jobs_status
            ON project_research_jobs(status, updated_at);
        CREATE INDEX IF NOT EXISTS idx_project_research_notes_task
            ON project_research_notes(task_id, created_at);
        """
    )


def _project_v57_find_task_for_topic(public_topic: str):
    topic = re.sub(r"\s+", " ", str(public_topic or "")).strip()[:700]
    if not topic:
        return None
    try:
        with _PROJECT_DB_LOCK:
            conn = _project_conn()
            row = conn.execute(
                "SELECT * FROM project_tasks WHERE public_topic=? ORDER BY id DESC LIMIT 1",
                (topic,),
            ).fetchone()
            if row is None:
                target_norm = _learning_norm(topic)
                rows = conn.execute(
                    "SELECT * FROM project_tasks WHERE public_topic<>'' ORDER BY id DESC LIMIT 80"
                ).fetchall()
                for candidate in rows:
                    if _learning_norm(str(candidate["public_topic"] or "")) == target_norm:
                        row = candidate
                        break
            conn.close()
            return row
    except Exception:
        return None


def _project_v57_upsert_job(task_id: int, public_topic: str):
    topic = re.sub(r"\s+", " ", str(public_topic or "")).strip()[:700]
    if int(task_id or 0) <= 0 or not topic:
        return None
    now = time.time()
    norm = _learning_norm(topic)
    try:
        with _PROJECT_DB_LOCK:
            conn = _project_conn()
            _project_v57_ensure_schema(conn)
            conn.execute(
                """INSERT OR IGNORE INTO project_research_jobs(
                       task_id,public_topic,norm,status,enqueued_count,deduped_count,completed_count,
                       evidence_changed_count,evidence_unchanged_count,evidence_fingerprint,source_count,
                       note_id,last_error,created_at,updated_at,completed_at
                   ) VALUES (?,?,?,'queued',0,0,0,0,0,'',0,0,'',?,?,0)""",
                (int(task_id), topic, norm, now, now),
            )
            conn.execute(
                "UPDATE project_research_jobs SET public_topic=?,norm=?,updated_at=? WHERE task_id=?",
                (topic, norm, now, int(task_id)),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM project_research_jobs WHERE task_id=?", (int(task_id),)).fetchone()
            conn.close()
            return row
    except Exception:
        return None


def _project_v57_note_payload(public_topic: str) -> dict | None:
    norm = _learning_norm(public_topic)
    if not norm:
        return None
    try:
        with _LEARNING_DB_LOCK:
            conn = _learning_conn()
            row = conn.execute(
                "SELECT topic,summary,confidence,source_count,sources_json,refreshed_at FROM notes WHERE norm=? LIMIT 1",
                (norm,),
            ).fetchone()
            conn.close()
    except Exception:
        return None
    if row is None or int(row["source_count"] or 0) < 1:
        return None
    try:
        raw_sources = json.loads(str(row["sources_json"] or "[]"))
    except Exception:
        raw_sources = []
    if not isinstance(raw_sources, list):
        return None
    receipts = []
    for item in raw_sources[:8]:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()[:1500]
        if not url.startswith("https://"):
            continue
        receipts.append({
            "url": url,
            "title": _project_redact_for_artifact(str(item.get("title") or ""))[:400],
            "retrieved_at": float(row["refreshed_at"] or time.time()),
        })
    if not receipts:
        return None
    try:
        fingerprint = _project_v55_evidence_fingerprint_from_receipts(receipts)
    except Exception:
        import hashlib
        normalized = sorted({
            (str(x.get("url") or "").lower().split("#", 1)[0], str(x.get("title") or "").lower())
            for x in receipts
        })
        fingerprint = hashlib.sha256(json.dumps(normalized, sort_keys=True).encode("utf-8", "ignore")).hexdigest()
    if not fingerprint:
        return None
    return {
        "fingerprint": fingerprint,
        "summary": _project_redact_for_artifact(str(row["summary"] or ""))[:9000],
        "confidence": max(0.0, min(1.0, float(row["confidence"] or 0))),
        "source_count": len(receipts),
        "receipts": receipts,
    }


def _project_v57_sync_learning_note(task_id: int, public_topic: str, observe_change: bool = False) -> dict:
    job = _project_v57_upsert_job(task_id, public_topic)
    if job is None:
        return {"ok": False, "detail": "research job unavailable"}
    payload = _project_v57_note_payload(public_topic)
    if not payload:
        return {"ok": False, "detail": "source-backed learning note is not ready"}
    now = time.time()
    fp = str(payload["fingerprint"])
    try:
        with _PROJECT_DB_LOCK:
            conn = _project_conn()
            _project_v57_ensure_schema(conn)
            current = conn.execute(
                "SELECT * FROM project_research_jobs WHERE task_id=?",
                (int(task_id),),
            ).fetchone()
            previous_fp = str(current["evidence_fingerprint"] or "") if current is not None else ""
            first_completion = not bool(int(current["completed_count"] or 0)) if current is not None else True
            existing = conn.execute(
                "SELECT id FROM project_research_notes WHERE task_id=? AND evidence_fingerprint=? LIMIT 1",
                (int(task_id), fp),
            ).fetchone()
            if existing is None:
                cur = conn.execute(
                    """INSERT INTO project_research_notes(
                           task_id,job_id,evidence_fingerprint,summary,sources_json,confidence,created_at
                       ) VALUES (?,?,?,?,?,?,?)""",
                    (
                        int(task_id), int(job["id"]), fp, str(payload["summary"]),
                        json.dumps(payload["receipts"], ensure_ascii=False),
                        float(payload["confidence"]), now,
                    ),
                )
                note_id = int(cur.lastrowid)
            else:
                note_id = int(existing["id"])

            changed_delta = 1 if fp != previous_fp and (observe_change or first_completion) else 0
            unchanged_delta = 1 if fp == previous_fp and bool(previous_fp) and observe_change else 0
            conn.execute(
                """UPDATE project_research_jobs SET
                       status='completed',completed_count=1,evidence_fingerprint=?,source_count=?,note_id=?,
                       evidence_changed_count=evidence_changed_count+?,
                       evidence_unchanged_count=evidence_unchanged_count+?,
                       last_error='',updated_at=?,completed_at=?
                   WHERE task_id=?""",
                (
                    fp, int(payload["source_count"]), note_id, changed_delta, unchanged_delta,
                    now, now, int(task_id),
                ),
            )
            conn.commit()
            conn.close()
        return {
            "ok": True,
            "task_id": int(task_id),
            "note_id": note_id,
            "evidence_fingerprint": fp,
            "evidence_changed": bool(changed_delta),
            "evidence_unchanged": bool(unchanged_delta),
            "source_count": int(payload["source_count"]),
        }
    except Exception as exc:
        return {"ok": False, "detail": f"research note sync failed: {exc}"}


def _project_v57_track_queue(public_topic: str, accepted: bool) -> None:
    task = _project_v57_find_task_for_topic(public_topic)
    if task is None:
        return
    task_id = int(task["id"])
    if _project_v57_upsert_job(task_id, public_topic) is None:
        return
    now = time.time()
    try:
        with _PROJECT_DB_LOCK:
            conn = _project_conn()
            _project_v57_ensure_schema(conn)
            if accepted:
                conn.execute(
                    """UPDATE project_research_jobs SET status='queued',enqueued_count=enqueued_count+1,
                       last_error='',updated_at=? WHERE task_id=?""",
                    (now, task_id),
                )
            else:
                conn.execute(
                    "UPDATE project_research_jobs SET deduped_count=deduped_count+1,updated_at=? WHERE task_id=?",
                    (now, task_id),
                )
            conn.commit()
            conn.close()
    except Exception:
        return
    if not accepted:
        _project_v57_sync_learning_note(task_id, public_topic, observe_change=False)


_v11757_learning_queue_topic_base = _learning_queue_topic


def _learning_queue_topic(topic: str, reason: str = "curiosity", priority: int = 30) -> bool:
    accepted = bool(_v11757_learning_queue_topic_base(topic, reason=reason, priority=priority))
    if str(reason or "") == "project-autolearn":
        _project_v57_track_queue(topic, accepted)
    return accepted


_v11757_learning_research_topic_base = _learning_research_topic


def _learning_research_topic(row) -> tuple[bool, str]:
    ok, detail = _v11757_learning_research_topic_base(row)
    topic = str(row["topic"] or "")
    if ok and topic:
        target_norm = _learning_norm(topic)
        try:
            with _PROJECT_DB_LOCK:
                conn = _project_conn()
                rows = conn.execute(
                    "SELECT id,public_topic FROM project_tasks WHERE public_topic<>'' ORDER BY id DESC LIMIT 120"
                ).fetchall()
                conn.close()
            for task in rows:
                if _learning_norm(str(task["public_topic"] or "")) == target_norm:
                    _project_v57_sync_learning_note(int(task["id"]), str(task["public_topic"]), observe_change=True)
        except Exception:
            pass
    return ok, detail


_v11757_project_queue_task_base = _project_queue_task


def _project_queue_task(goal: str, category: str = "capability", detail: str = "", source_gap_id: int = 0) -> dict:
    result = _v11757_project_queue_task_base(goal, category, detail, source_gap_id)
    if not result.get("ok") or not result.get("task_id"):
        return result
    task_id = int(result["task_id"])
    topic = str(result.get("public_topic") or "").strip()
    if not topic:
        try:
            with _PROJECT_DB_LOCK:
                conn = _project_conn()
                row = conn.execute("SELECT public_topic FROM project_tasks WHERE id=?", (task_id,)).fetchone()
                conn.close()
            topic = str(row["public_topic"] or "").strip() if row is not None else ""
        except Exception:
            topic = ""
    if topic:
        job = None
        try:
            with _PROJECT_DB_LOCK:
                conn = _project_conn()
                _project_v57_ensure_schema(conn)
                job = conn.execute("SELECT id FROM project_research_jobs WHERE task_id=?", (task_id,)).fetchone()
                conn.close()
        except Exception:
            job = None
        if job is None:
            _learning_queue_topic(topic, reason="project-autolearn", priority=86)
    return result


def _project_v57_backfill_jobs(limit: int = 12) -> int:
    queued = 0
    try:
        with _PROJECT_DB_LOCK:
            conn = _project_conn()
            _project_v57_ensure_schema(conn)
            rows = conn.execute(
                """SELECT t.id,t.public_topic FROM project_tasks t
                   LEFT JOIN project_research_jobs j ON j.task_id=t.id
                   WHERE j.id IS NULL AND t.public_topic<>''
                     AND t.status IN ('queued','research','retry','waiting-evidence','cooldown')
                   ORDER BY t.updated_at ASC LIMIT ?""",
                (max(1, min(int(limit or 12), 40)),),
            ).fetchall()
            conn.close()
        for row in rows:
            if _learning_queue_topic(str(row["public_topic"]), reason="project-autolearn", priority=86):
                queued += 1
    except Exception:
        return queued
    return queued


_v11757_project_learning_evidence_base = _project_learning_evidence


def _project_learning_evidence(public_topic: str, task_id: int) -> dict:
    evidence = _v11757_project_learning_evidence_base(public_topic, task_id)
    if evidence.get("ok"):
        _project_v57_sync_learning_note(int(task_id), public_topic, observe_change=False)
    return evidence


_v11757_project_supervisor_once_base = _project_supervisor_once


def _project_supervisor_once(force: bool = False) -> dict:
    _project_v57_backfill_jobs(limit=12)
    return _v11757_project_supervisor_once_base(force=force)


def _project_v57_metrics() -> dict:
    result = {
        "initiatives_seen": 0,
        "research_jobs": 0,
        "research_jobs_pending": 0,
        "research_jobs_enqueued": 0,
        "research_jobs_deduped": 0,
        "research_jobs_completed": 0,
        "research_notes_written": 0,
        "evidence_changed": 0,
        "evidence_unchanged": 0,
        "proposals_emitted": 0,
    }
    try:
        with _PROJECT_DB_LOCK:
            conn = _project_conn()
            _project_v57_ensure_schema(conn)
            result["initiatives_seen"] = int(conn.execute(
                "SELECT COUNT(*) AS n FROM project_tasks WHERE source_gap_id>0"
            ).fetchone()["n"] or 0)
            result["research_jobs"] = int(conn.execute(
                "SELECT COUNT(*) AS n FROM project_research_jobs"
            ).fetchone()["n"] or 0)
            result["research_jobs_pending"] = int(conn.execute(
                "SELECT COUNT(*) AS n FROM project_research_jobs WHERE status!='completed'"
            ).fetchone()["n"] or 0)
            sums = conn.execute(
                """SELECT COALESCE(SUM(enqueued_count),0) AS enqueued,
                          COALESCE(SUM(deduped_count),0) AS deduped,
                          COALESCE(SUM(completed_count),0) AS completed,
                          COALESCE(SUM(evidence_changed_count),0) AS changed,
                          COALESCE(SUM(evidence_unchanged_count),0) AS unchanged
                   FROM project_research_jobs"""
            ).fetchone()
            result["research_jobs_enqueued"] = int(sums["enqueued"] or 0)
            result["research_jobs_deduped"] = int(sums["deduped"] or 0)
            result["research_jobs_completed"] = int(sums["completed"] or 0)
            result["evidence_changed"] = int(sums["changed"] or 0)
            result["evidence_unchanged"] = int(sums["unchanged"] or 0)
            result["research_notes_written"] = int(conn.execute(
                "SELECT COUNT(*) AS n FROM project_research_notes"
            ).fetchone()["n"] or 0)
            result["proposals_emitted"] = int(conn.execute(
                "SELECT COUNT(*) AS n FROM project_proposals WHERE status!='superseded-duplicate'"
            ).fetchone()["n"] or 0)
            conn.close()
    except Exception:
        pass
    return result


_v11757_project_supervisor_status_base = _project_supervisor_status


def _project_supervisor_status() -> dict:
    result = _v11757_project_supervisor_status_base()
    result["version"] = "0.11.7.57"
    result["mode"] = "autonomous-source-grounded-project-learning-evidence-loop"
    result["research_job_dedupe"] = True
    result["source_backed_research_notes"] = True
    result["confidence_only_on_evidence_change"] = True
    result.update(_project_v57_metrics())
    return result


_v11757_windows_native_capabilities_base = _windows_native_capabilities


def _windows_native_capabilities() -> dict:
    result = _v11757_windows_native_capabilities_base()
    result["version"] = "0.11.7.57"
    return result


'''

if "# v0.11.7.57 Autonomous Research Evidence Loop" not in bridge:
    bridge = bridge.replace(anchor, layer + anchor, 1)

remote = re.sub(r'^VERSION = "0\.11\.7\.56"', 'VERSION = "0.11.7.57"', remote, count=1, flags=re.M)

remote_anchor = "def maintenance_public(value: dict) -> dict:\n"
remote_layer = r'''_v11757_autolearn_public_base = autolearn_public


def autolearn_public(value: dict) -> dict:
    result = _v11757_autolearn_public_base(value)
    result["version"] = str(value.get("version") or "")[:40] or None
    result["research_job_dedupe"] = yes(value.get("research_job_dedupe"))
    result["source_backed_research_notes"] = yes(value.get("source_backed_research_notes"))
    result["confidence_only_on_evidence_change"] = yes(value.get("confidence_only_on_evidence_change"))
    for key in [
        "initiatives_seen", "research_jobs", "research_jobs_pending", "research_jobs_enqueued",
        "research_jobs_deduped", "research_jobs_completed", "research_notes_written",
        "evidence_changed", "evidence_unchanged", "proposals_emitted",
    ]:
        result[key] = integer(value.get(key))
    return result


'''
if "_v11757_autolearn_public_base = autolearn_public" not in remote:
    if remote_anchor not in remote:
        raise SystemExit("v0.11.7.57 Remote Support helper anchor missing")
    remote = remote.replace(remote_anchor, remote_layer + remote_anchor, 1)

installer = installer.replace('BUNDLE_VERSION = "0.11.7.56"', 'BUNDLE_VERSION = "0.11.7.57"', 1)
installer = installer.replace('REMOTE_VERSION = "0.11.7.56"', 'REMOTE_VERSION = "0.11.7.57"', 1)
installer = installer.replace("Vex Agent Runtime v0.11.7.56 installed.", "Vex Agent Runtime v0.11.7.57 installed.", 1)

BRIDGE.write_text(bridge, encoding="utf-8")
REMOTE.write_text(remote, encoding="utf-8")
INSTALLER.write_text(installer, encoding="utf-8")

for path, text in [(BRIDGE, bridge), (REMOTE, remote), (INSTALLER, installer)]:
    compile(text, str(path), "exec")

for marker in [
    '"agent_runtime_bundle": "0.11.7.57"',
    "# v0.11.7.57 Autonomous Research Evidence Loop",
    "CREATE TABLE IF NOT EXISTS project_research_jobs",
    "CREATE TABLE IF NOT EXISTS project_research_notes",
    "_v11757_learning_queue_topic_base = _learning_queue_topic",
    'reason or "") == "project-autolearn"',
    "_v11757_learning_research_topic_base = _learning_research_topic",
    "observe_change=True",
    "_project_v57_backfill_jobs(limit=12)",
    'result["research_job_dedupe"] = True',
    'result["source_backed_research_notes"] = True',
    'result["confidence_only_on_evidence_change"] = True',
    'result["version"] = "0.11.7.57"',
]:
    if marker not in bridge:
        raise SystemExit(f"v0.11.7.57 Bridge marker missing: {marker}")

for marker in [
    'VERSION = "0.11.7.57"',
    "_v11757_autolearn_public_base = autolearn_public",
    '"research_jobs_enqueued"',
    '"research_notes_written"',
    '"evidence_changed"',
    '"proposals_emitted"',
]:
    if marker not in remote:
        raise SystemExit(f"v0.11.7.57 Remote marker missing: {marker}")

for marker in [
    'BUNDLE_VERSION = "0.11.7.57"',
    'REMOTE_VERSION = "0.11.7.57"',
    "Vex Agent Runtime v0.11.7.57 installed.",
]:
    if marker not in installer:
        raise SystemExit(f"v0.11.7.57 installer marker missing: {marker}")

# The public relay gets counters/booleans only. Research topics, source receipts,
# note text and local proposal artifacts stay behind the authenticated local Bridge.
for forbidden in [
    'bridge_get("/windows/windows"',
    '"recent_proposals":',
    '"source_url":',
    '"artifact_path":',
    '"project_research_notes":',
    '"research_note_summary":',
    '"research_sources":',
]:
    if forbidden in remote:
        raise SystemExit(f"v0.11.7.57 Remote privacy regression: {forbidden}")

for forbidden in ["api.openai.com", "OPENAI_API_KEY", "personal_memory_mutated\": True"]:
    if forbidden in layer:
        raise SystemExit(f"v0.11.7.57 autonomy boundary regression: {forbidden}")

print("Applied v0.11.7.57 autonomous research evidence loop: tracked jobs + source-backed notes + material-evidence counters")
