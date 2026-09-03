#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
text = BRIDGE.read_text(encoding="utf-8")

MARKER = 'V120_LEARNING_LIFECYCLE = "v0.12-active-state-learning-v2"'
CORRECTNESS_MARKER = 'V120_WANTS_BACKGROUND_RECONCILIATION = "v0.12-wants-background-v1"'


def replace_function(source: str, name: str, replacement: str) -> str:
    start = source.find(f"def {name}(")
    if start < 0:
        raise SystemExit(f"v0.12 learning lifecycle missing function: {name}")
    end = source.find("\n\ndef ", start + 10)
    if end < 0:
        raise SystemExit(f"v0.12 learning lifecycle could not bound function: {name}")
    return source[:start] + replacement.rstrip() + source[end:]


if CORRECTNESS_MARKER not in text:
    raise SystemExit("v0.12 learning lifecycle requires background Wants reconciliation first")

if MARKER not in text:
    resolve_replacement = r'''V120_LEARNING_LIFECYCLE = "v0.12-active-state-learning-v2"


def _v120_record_resolution_lesson(subject: str, detail: str, evidence: str = "") -> None:
    """Feed a verified repair/upgrade closure back into adaptive learning once."""
    store = globals().get("_adaptive_store_lesson")
    if not callable(store):
        return
    subject = str(subject or "local capability").strip()[:180]
    detail = str(detail or "verified healthy").strip()[:1200]
    evidence = str(evidence or "v0.12 active-state reconciliation").strip()[:900]
    try:
        store(
            "capability",
            f"{subject} repair resolved upgrade completed current state",
            (
                f"{subject} is currently verified healthy or implemented: {detail}. "
                "Treat older repair gaps and upgrade proposals for this same solved condition as historical. "
                "Only reopen the problem when a new live capability check or acceptance test fails."
            ),
            0.99,
            evidence,
        )
    except Exception:
        pass


def _v120_retire_orphaned_adaptive_upgrades() -> int:
    """Hide active upgrades whose source gap is already closed or gone; DB-only."""
    changed = 0
    try:
        with _ADAPTIVE_DB_LOCK:
            conn = _adaptive_conn()
            active_marks = ",".join("?" for _ in V120_ACTIVE_PROPOSAL_STATUSES)
            cur = conn.execute(
                f"""UPDATE upgrade_candidates
                    SET status='superseded-solved',updated_at=?
                    WHERE gap_id > 0
                      AND status IN ({active_marks})
                      AND NOT EXISTS (
                          SELECT 1 FROM gaps g
                          WHERE g.id=upgrade_candidates.gap_id AND g.status='open'
                      )""",
                (time.time(), *V120_ACTIVE_PROPOSAL_STATUSES),
            )
            changed = int(cur.rowcount or 0)
            conn.commit()
            conn.close()
    except Exception:
        return changed
    return changed


def _v120_retire_projects_for_closed_gaps() -> int:
    """Supersede project proposals whose source gap is no longer open; no probes."""
    source_ids: set[int] = set()
    try:
        with _PROJECT_DB_LOCK:
            conn = _project_conn()
            rows = conn.execute(
                "SELECT DISTINCT source_gap_id FROM project_tasks WHERE source_gap_id > 0"
            ).fetchall()
            source_ids = {int(row["source_gap_id"]) for row in rows if int(row["source_gap_id"] or 0) > 0}
            conn.close()
    except Exception:
        return 0
    if not source_ids:
        return 0

    open_ids: set[int] = set()
    try:
        ids = sorted(source_ids)
        marks = ",".join("?" for _ in ids)
        with _ADAPTIVE_DB_LOCK:
            conn = _adaptive_conn()
            rows = conn.execute(
                f"SELECT id FROM gaps WHERE id IN ({marks}) AND status='open'",
                tuple(ids),
            ).fetchall()
            open_ids = {int(row["id"]) for row in rows}
            conn.close()
    except Exception:
        return 0

    closed_ids = sorted(source_ids - open_ids)
    if not closed_ids:
        return 0
    return _v120_supersede_project_work_for_gaps(
        closed_ids,
        "source learning gap is no longer open; proposal retained only as history",
    )


def _v120_resolve_capability_gap(name: str, detail: str = "") -> dict:
    """Close stale work only after caller has independently verified capability health."""
    request_text = f"local capability {str(name or '').strip()} is unhealthy"
    resolved_ids: list[int] = []
    retired_upgrades = 0
    try:
        with _ADAPTIVE_DB_LOCK:
            conn = _adaptive_conn()
            rows = conn.execute(
                "SELECT id FROM gaps WHERE status='open' AND request_text=?",
                (request_text,),
            ).fetchall()
            resolved_ids = [int(row["id"]) for row in rows]
            if resolved_ids:
                now = time.time()
                conn.execute(
                    "UPDATE gaps SET status='resolved',updated_at=?,detail=? WHERE status='open' AND request_text=?",
                    (now, f"verified healthy: {str(detail or 'healthy')[:1200]}", request_text),
                )
                marks = ",".join("?" for _ in resolved_ids)
                active_marks = ",".join("?" for _ in V120_ACTIVE_PROPOSAL_STATUSES)
                cur = conn.execute(
                    f"""UPDATE upgrade_candidates SET status='superseded-solved',updated_at=?
                        WHERE gap_id IN ({marks}) AND status IN ({active_marks})""",
                    (now, *resolved_ids, *V120_ACTIVE_PROPOSAL_STATUSES),
                )
                retired_upgrades = int(cur.rowcount or 0)
                conn.commit()
            conn.close()
    except Exception:
        resolved_ids = []
        retired_upgrades = 0

    superseded = _v120_supersede_project_work_for_gaps(
        resolved_ids, f"{name} verified healthy: {detail}"
    )
    if resolved_ids or retired_upgrades or superseded:
        _v120_record_resolution_lesson(
            str(name),
            str(detail or "healthy"),
            f"resolved_gaps={len(resolved_ids)} retired_upgrades={retired_upgrades} superseded_projects={superseded}",
        )
    return {
        "capability": name,
        "resolved_gaps": len(resolved_ids),
        "retired_upgrades": retired_upgrades,
        "superseded_projects": superseded,
    }
'''
    text = replace_function(text, "_v120_resolve_capability_gap", resolve_replacement)

    cached_anchor = "def _v120_reconcile_wants_cached() -> dict:\n"
    if cached_anchor not in text:
        raise SystemExit("v0.12 lifecycle could not find cached Wants reconciler")

    wrapper = r'''
V120_LIFECYCLE_CLEANUP_LOCK = threading.Lock()
V120_LIFECYCLE_CLEANUP_STATE = {"running": False, "last_run": 0.0}
_v120_reconcile_wants_lifecycle_base = _v120_reconcile_wants


def _v120_lifecycle_cleanup_async() -> None:
    """Retire stale DB work away from the Wants HTTP/readiness path."""
    now = time.time()
    with V120_LIFECYCLE_CLEANUP_LOCK:
        if V120_LIFECYCLE_CLEANUP_STATE.get("running"):
            return
        if now - float(V120_LIFECYCLE_CLEANUP_STATE.get("last_run") or 0.0) < 15.0:
            return
        V120_LIFECYCLE_CLEANUP_STATE["running"] = True

    def _worker() -> None:
        try:
            # Cold-start proof and foreground Wants reads get first claim on the
            # SQLite locks. Lifecycle cleanup deliberately waits and never gates
            # local-control readiness.
            time.sleep(5.0)
            orphaned = _v120_retire_orphaned_adaptive_upgrades()
            linked_projects = _v120_retire_projects_for_closed_gaps()
            if orphaned or linked_projects:
                _v120_record_resolution_lesson(
                    "self-improvement lifecycle",
                    "stale active work was retired because its source learning gap is already closed",
                    f"retired_upgrades={orphaned} superseded_projects={linked_projects}",
                )
        finally:
            with V120_LIFECYCLE_CLEANUP_LOCK:
                V120_LIFECYCLE_CLEANUP_STATE["last_run"] = time.time()
                V120_LIFECYCLE_CLEANUP_STATE["running"] = False

    thread = threading.Thread(target=_worker, daemon=True, name="VexLifecycleCleanup")
    thread.start()


def _v120_reconcile_wants() -> dict:
    # Preserve the already-proven nonblocking correctness reconciler. The
    # lifecycle bookkeeping is scheduled separately so /autonomy/requests can
    # never be held hostage by project/adaptive DB housekeeping during startup.
    summary = dict(_v120_reconcile_wants_lifecycle_base() or {})
    summary.setdefault("ok", True)
    summary.setdefault("resolved_gaps", 0)
    summary.setdefault("retired_upgrades", 0)
    summary.setdefault("superseded_projects", 0)
    summary.setdefault("applied_upgrades", 0)
    summary.setdefault("healthy", {})
    summary["lifecycle"] = "reconciled-active-state-v2"
    _v120_lifecycle_cleanup_async()
    return summary


'''
    text = text.replace(cached_anchor, wrapper + cached_anchor, 1)

BRIDGE.write_text(text, encoding="utf-8")
compile(text, str(BRIDGE), "exec")

for required in [
    MARKER,
    "def _v120_record_resolution_lesson(",
    "def _v120_retire_orphaned_adaptive_upgrades(",
    "def _v120_retire_projects_for_closed_gaps(",
    "_v120_reconcile_wants_lifecycle_base = _v120_reconcile_wants",
    'summary["lifecycle"] = "reconciled-active-state-v2"',
    "status='superseded-solved'",
    "Only reopen the problem when a new live capability check or acceptance test fails.",
    "def _v120_lifecycle_cleanup_async() -> None:",
]:
    if required not in text:
        raise SystemExit(f"v0.12 learning lifecycle verifier missing: {required}")

if 'registry = globals().get("AUTONOMY_CAPABILITIES")' in text[text.find(MARKER):text.find("def _v120_reconcile_wants_cached")]:
    raise SystemExit("v0.12 lifecycle verifier found synchronous all-capability Wants probing")

print("Applied v0.12 nonblocking active-state cleanup + learning outcome feedback v2")
