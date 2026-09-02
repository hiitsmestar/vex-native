#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
text = BRIDGE.read_text(encoding="utf-8")

MARKER = 'V120_LEARNING_LIFECYCLE = "v0.12-active-state-learning-v1"'


def replace_function(source: str, name: str, replacement: str) -> str:
    start = source.find(f"def {name}(")
    if start < 0:
        raise SystemExit(f"v0.12 learning lifecycle missing function: {name}")
    end = source.find("\n\ndef ", start + 10)
    if end < 0:
        raise SystemExit(f"v0.12 learning lifecycle could not bound function: {name}")
    return source[:start] + replacement.rstrip() + source[end:]


if MARKER not in text:
    resolve_replacement = r'''V120_LEARNING_LIFECYCLE = "v0.12-active-state-learning-v1"


def _v120_record_resolution_lesson(subject: str, detail: str, evidence: str = "") -> None:
    """Feed successful repair/upgrade outcomes back into adaptive learning once."""
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


def _v120_sync_capability_state(name: str, ok: bool, detail: str) -> None:
    """Refresh current capability truth without inflating success/failure counters on UI refresh."""
    try:
        now = time.time()
        with _ADAPTIVE_DB_LOCK:
            conn = _adaptive_conn()
            _autonomy_ensure_tables(conn)
            conn.execute(
                """INSERT OR IGNORE INTO capabilities
                   (name,updated_at,last_tested,last_researched,confidence,successes,failures,healthy,detail)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (str(name), now, now, 0.0, 0.0, 0, 0, 1 if ok else 0, str(detail)[:900]),
            )
            conn.execute(
                "UPDATE capabilities SET updated_at=?,last_tested=?,healthy=?,detail=? WHERE name=?",
                (now, now, 1 if ok else 0, str(detail)[:900], str(name)),
            )
            conn.commit()
            conn.close()
    except Exception:
        pass


def _v120_retire_orphaned_adaptive_upgrades() -> int:
    """Hide active upgrades whose source gap is already closed or gone."""
    changed = 0
    try:
        with _ADAPTIVE_DB_LOCK:
            conn = _adaptive_conn()
            _autonomy_ensure_tables(conn)
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
    """Supersede project proposals when their originating learning gap is no longer open."""
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

    reconcile_replacement = r'''def _v120_reconcile_wants() -> dict:
    summary = {
        "ok": True,
        "resolved_gaps": 0,
        "retired_upgrades": 0,
        "superseded_projects": 0,
        "applied_upgrades": 0,
        "healthy": {},
    }

    # Reconcile every installed autonomy capability, not a hard-coded pair.
    registry = globals().get("AUTONOMY_CAPABILITIES")
    names = list(registry.keys()) if isinstance(registry, dict) else []
    if not names:
        names = ["personal_memory", "local_cognition", "web_research", "learned_skills", "self_repair", "art_worker", "file_index"]

    for name in names:
        try:
            ok, detail = _autonomy_probe_capability(str(name))
        except Exception as exc:
            ok, detail = False, f"{exc.__class__.__name__}: {str(exc)[:180]}"
        summary["healthy"][str(name)] = bool(ok)
        _v120_sync_capability_state(str(name), bool(ok), str(detail))
        if ok:
            item = _v120_resolve_capability_gap(str(name), str(detail))
            summary["resolved_gaps"] += int(item.get("resolved_gaps") or 0)
            summary["retired_upgrades"] += int(item.get("retired_upgrades") or 0)
            summary["superseded_projects"] += int(item.get("superseded_projects") or 0)

    # Catch rows left behind by older builds even if their gap was resolved long ago.
    orphaned = _v120_retire_orphaned_adaptive_upgrades()
    linked_projects = _v120_retire_projects_for_closed_gaps()
    summary["retired_upgrades"] += orphaned
    summary["superseded_projects"] += linked_projects
    if orphaned or linked_projects:
        _v120_record_resolution_lesson(
            "self-improvement lifecycle",
            "stale active work was retired because its source learning gap is already closed",
            f"retired_upgrades={orphaned} superseded_projects={linked_projects}",
        )

    try:
        win = _windows_native_capabilities()
        win_ok = bool(
            win.get("ok")
            and win.get("native_window_inventory")
            and int(win.get("visible_window_count") or 0) > 0
            and win.get("interactive_session_match") is not False
            and win.get("input_desktop_accessible") is not False
        )
        summary["healthy"]["windows_visible_inventory"] = win_ok
        if win_ok:
            changed = _v120_retire_windows_inventory_proposals(win)
            summary["superseded_projects"] += changed
            if changed:
                _v120_record_resolution_lesson(
                    "Windows visible-window inventory",
                    f"live native enumeration verified {int(win.get('visible_window_count') or 0)} visible windows",
                    f"retired_project_proposals={changed}",
                )
    except Exception:
        summary["healthy"]["windows_visible_inventory"] = False

    applied = _v120_mark_grounded_renderer_applied()
    summary["applied_upgrades"] += applied
    if applied:
        _v120_record_resolution_lesson(
            "grounded conversation renderer",
            "fact-preserving renderer is implemented and verified in the shipped Bridge",
            f"applied_upgrade_rows={applied}",
        )
    return summary
'''
    text = replace_function(text, "_v120_reconcile_wants", reconcile_replacement)

BRIDGE.write_text(text, encoding="utf-8")
compile(text, str(BRIDGE), "exec")

for required in [
    MARKER,
    "def _v120_record_resolution_lesson(",
    "def _v120_sync_capability_state(",
    "def _v120_retire_orphaned_adaptive_upgrades(",
    "def _v120_retire_projects_for_closed_gaps(",
    "registry = globals().get(\"AUTONOMY_CAPABILITIES\")",
    "status='superseded-solved'",
    "Only reopen the problem when a new live capability check or acceptance test fails.",
]:
    if required not in text:
        raise SystemExit(f"v0.12 learning lifecycle verifier missing: {required}")

print("Applied v0.12 active-state Wants cleanup + self-learning outcome feedback")
