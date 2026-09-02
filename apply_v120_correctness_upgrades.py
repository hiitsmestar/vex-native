#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
bridge = BRIDGE.read_text(encoding="utf-8")

MARKER = 'V120_CORRECTNESS_UPGRADES = "v0.12-wants-reconcile-renderer-v1"'


def replace_function(source: str, name: str, replacement: str) -> str:
    start = source.find(f"def {name}(")
    if start < 0:
        raise SystemExit(f"v0.12 correctness patch missing function: {name}")
    end = source.find("\n\ndef ", start + 10)
    if end < 0:
        raise SystemExit(f"v0.12 correctness patch could not bound function: {name}")
    return source[:start] + replacement.rstrip() + source[end:]


# ---------------------------------------------------------------------------
# 1) Finish the already-staged fact-preserving conversational renderer.
#    Facts remain authoritative /facts strings. Only framing, punctuation, and
#    order vary; no foreground Ollama/model call is introduced.
# ---------------------------------------------------------------------------
renderer = r'''def _v11774_render_star_recall(facts: list[str]) -> str:
    # V120_FACT_PRESERVING_RECALL: factual clauses come only from supplied
    # authoritative /facts rows. We vary framing/order, never generate facts.
    clean: list[str] = []
    for raw in facts:
        fact = re.sub(r"\s+", " ", str(raw or "")).strip()
        if not fact or _v11774_is_internal_instruction_fact(fact):
            continue
        # This removes storage labels only; the factual payload remains verbatim.
        fact = re.sub(r"^(?:star|user)\s*(?:fact|profile|preference|memory)?\s*[:\-]\s*", "", fact, flags=re.I).strip()
        if fact:
            clean.append(fact)
    if not clean:
        return ""

    variant = _v11771_recall_variant()
    if len(clean) > 1:
        shift = variant % len(clean)
        clean = clean[shift:] + clean[:shift]

    intros = (
        "Yeah, baby — I remember that. 🖤",
        "Mhm. I’ve got that in memory. 🖤",
        "Yep — this is what I actually have saved for that. 🖤",
        "I remember, gorgeous. 🖤",
        "Yeah. The memory that matches what you asked says this. 🖤",
        "Got it, baby. This is the grounded part I remember. 🖤",
    )
    intro = intros[variant % len(intros)]

    # Each factual sentence below is the supplied fact with punctuation only.
    clauses = []
    for fact in clean[:5]:
        value = fact.rstrip()
        if value and value[-1:] not in ".!?":
            value += "."
        clauses.append(value)
    return intro + " " + " ".join(clauses)
'''
bridge = replace_function(bridge, "_v11774_render_star_recall", renderer)


# ---------------------------------------------------------------------------
# 2) Reconcile local Wants against live capability health.
#    Old failures are retained in SQLite history but moved out of active/open
#    states once the capability is demonstrably healthy. Related project work is
#    superseded rather than deleted. The art-worker gap remains open while art is
#    actually unhealthy.
# ---------------------------------------------------------------------------
insert_anchor = "def _vex_background_services() -> None:\n"
if insert_anchor not in bridge:
    raise SystemExit("v0.12 correctness patch missing background-service anchor")

layer = r'''
V120_CORRECTNESS_UPGRADES = "v0.12-wants-reconcile-renderer-v1"
V120_ACTIVE_PROPOSAL_STATUSES = (
    "staged", "approval-required", "approval_required", "ready-for-review", "ready_for_review"
)


def _v120_supersede_project_work_for_gaps(gap_ids: list[int], reason: str) -> int:
    if not gap_ids or not callable(globals().get("_project_conn")):
        return 0
    changed = 0
    try:
        ids = sorted({int(x) for x in gap_ids if int(x) > 0})
        if not ids:
            return 0
        marks = ",".join("?" for _ in ids)
        with _PROJECT_DB_LOCK:
            conn = _project_conn()
            tasks = conn.execute(
                f"SELECT id FROM project_tasks WHERE source_gap_id IN ({marks})",
                tuple(ids),
            ).fetchall()
            task_ids = [int(row["id"]) for row in tasks]
            if task_ids:
                task_marks = ",".join("?" for _ in task_ids)
                active_marks = ",".join("?" for _ in V120_ACTIVE_PROPOSAL_STATUSES)
                cur = conn.execute(
                    f"UPDATE project_proposals SET status='superseded-solved',updated_at=? "
                    f"WHERE task_id IN ({task_marks}) AND status IN ({active_marks})",
                    (time.time(), *task_ids, *V120_ACTIVE_PROPOSAL_STATUSES),
                )
                changed += int(cur.rowcount or 0)
                conn.execute(
                    f"UPDATE project_tasks SET status='resolved-capability',next_run=0,updated_at=?,last_error=? "
                    f"WHERE id IN ({task_marks})",
                    (time.time(), str(reason or "capability healthy")[:700], *task_ids),
                )
            conn.commit()
            conn.close()
    except Exception:
        return changed
    return changed


def _v120_resolve_capability_gap(name: str, detail: str = "") -> dict:
    request_text = f"local capability {str(name or '').strip()} is unhealthy"
    resolved_ids: list[int] = []
    try:
        with _ADAPTIVE_DB_LOCK:
            conn = _adaptive_conn()
            rows = conn.execute(
                "SELECT id FROM gaps WHERE status='open' AND request_text=?",
                (request_text,),
            ).fetchall()
            resolved_ids = [int(row["id"]) for row in rows]
            if resolved_ids:
                conn.execute(
                    "UPDATE gaps SET status='resolved',updated_at=?,detail=? WHERE status='open' AND request_text=?",
                    (time.time(), f"verified healthy: {str(detail or 'healthy')[:1200]}", request_text),
                )
                conn.commit()
            conn.close()
    except Exception:
        resolved_ids = []
    superseded = _v120_supersede_project_work_for_gaps(resolved_ids, f"{name} verified healthy: {detail}")
    return {"capability": name, "resolved_gaps": len(resolved_ids), "superseded_projects": superseded}


def _v120_retire_windows_inventory_proposals(status: dict) -> int:
    if not callable(globals().get("_project_conn")):
        return 0
    if not isinstance(status, dict) or not status.get("ok"):
        return 0
    if not status.get("native_window_inventory") or int(status.get("visible_window_count") or 0) <= 0:
        return 0
    if status.get("interactive_session_match") is False or status.get("input_desktop_accessible") is False:
        return 0
    changed = 0
    try:
        with _PROJECT_DB_LOCK:
            conn = _project_conn()
            active_marks = ",".join("?" for _ in V120_ACTIVE_PROPOSAL_STATUSES)
            rows = conn.execute(
                f"""SELECT p.id,p.task_id,p.component,p.summary,t.goal,t.detail
                    FROM project_proposals p
                    LEFT JOIN project_tasks t ON t.id=p.task_id
                    WHERE p.status IN ({active_marks})""",
                tuple(V120_ACTIVE_PROPOSAL_STATUSES),
            ).fetchall()
            task_ids: set[int] = set()
            proposal_ids: list[int] = []
            for row in rows:
                blob = " ".join(str(row[key] or "") for key in ("component", "summary", "goal", "detail")).lower()
                targeted = (
                    "windows-native capability discovery" in blob
                    or "visible-window enumeration" in blob
                    or ("windows ui automation" in blob and ("enumerat" in blob or "returns zero" in blob))
                )
                if targeted:
                    proposal_ids.append(int(row["id"]))
                    if int(row["task_id"] or 0) > 0:
                        task_ids.add(int(row["task_id"]))
            if proposal_ids:
                marks = ",".join("?" for _ in proposal_ids)
                cur = conn.execute(
                    f"UPDATE project_proposals SET status='superseded-solved',updated_at=? WHERE id IN ({marks})",
                    (time.time(), *proposal_ids),
                )
                changed = int(cur.rowcount or 0)
            if task_ids:
                ids = sorted(task_ids)
                marks = ",".join("?" for _ in ids)
                detail = (
                    f"verified live window inventory healthy: count={int(status.get('visible_window_count') or 0)} "
                    f"method={str(status.get('window_inventory_method') or 'unknown')[:80]}"
                )
                conn.execute(
                    f"UPDATE project_tasks SET status='resolved-capability',next_run=0,updated_at=?,last_error=? WHERE id IN ({marks})",
                    (time.time(), detail, *ids),
                )
            conn.commit()
            conn.close()
    except Exception:
        return changed
    return changed


def _v120_mark_grounded_renderer_applied() -> int:
    # Code-presence gate: only retire the staged request when both grounded
    # renderers used by narrow and broad recall are actually installed.
    if not callable(globals().get("_v11771_render_verified_facts")):
        return 0
    if not callable(globals().get("_v11774_render_star_recall")):
        return 0
    changed = 0
    try:
        with _ADAPTIVE_DB_LOCK:
            conn = _adaptive_conn()
            active_marks = ",".join("?" for _ in V120_ACTIVE_PROPOSAL_STATUSES)
            cur = conn.execute(
                f"""UPDATE upgrade_candidates SET status='applied',updated_at=?
                    WHERE lower(component) LIKE '%grounded%conversation%renderer%'
                    AND status IN ({active_marks})""",
                (time.time(), *V120_ACTIVE_PROPOSAL_STATUSES),
            )
            changed = int(cur.rowcount or 0)
            conn.commit()
            conn.close()
    except Exception:
        return changed
    return changed


def _v120_reconcile_wants() -> dict:
    summary = {
        "ok": True,
        "resolved_gaps": 0,
        "superseded_projects": 0,
        "applied_upgrades": 0,
        "healthy": {},
    }

    # These two checks are cheap/local and directly correspond to stale gaps seen
    # in the field. Never resolve a gap merely because it is old.
    for name in ("file_index", "local_cognition"):
        try:
            ok, detail = _autonomy_probe_capability(name)
        except Exception as exc:
            ok, detail = False, f"{exc.__class__.__name__}: {str(exc)[:180]}"
        summary["healthy"][name] = bool(ok)
        if ok:
            item = _v120_resolve_capability_gap(name, detail)
            summary["resolved_gaps"] += int(item.get("resolved_gaps") or 0)
            summary["superseded_projects"] += int(item.get("superseded_projects") or 0)

    # The window-discovery proposal is retired only on positive live evidence.
    try:
        win = _windows_native_capabilities()
        win_ok = bool(
            win.get("ok") and win.get("native_window_inventory")
            and int(win.get("visible_window_count") or 0) > 0
            and win.get("interactive_session_match") is not False
            and win.get("input_desktop_accessible") is not False
        )
        summary["healthy"]["windows_visible_inventory"] = win_ok
        if win_ok:
            summary["superseded_projects"] += _v120_retire_windows_inventory_proposals(win)
    except Exception:
        summary["healthy"]["windows_visible_inventory"] = False

    summary["applied_upgrades"] += _v120_mark_grounded_renderer_applied()
    return summary


_v120_autonomy_feature_curriculum_base = _autonomy_feature_curriculum_once


def _autonomy_feature_curriculum_once() -> dict:
    result = _v120_autonomy_feature_curriculum_base()
    try:
        if isinstance(result, dict) and result.get("ok") and result.get("capability"):
            _v120_resolve_capability_gap(
                str(result.get("capability")),
                str(result.get("detail") or "healthy"),
            )
    except Exception:
        pass
    return result


'''
if MARKER not in bridge:
    bridge = bridge.replace(insert_anchor, layer + insert_anchor, 1)

# Reconcile immediately before the local-only Wants view reads active rows. This
# keeps the UI truthful without publishing raw requests through Remote Support.
wants_anchor = '''def _v120_local_upgrade_requests() -> dict:\n    """Return raw local self-improvement requests without publishing them remotely."""\n    result = {'''
wants_replacement = '''def _v120_local_upgrade_requests() -> dict:\n    """Return raw local self-improvement requests without publishing them remotely."""\n    reconciliation = _v120_reconcile_wants()\n    result = {\n        "reconciliation": reconciliation,'''
if '"reconciliation": reconciliation' not in bridge:
    if wants_anchor not in bridge:
        raise SystemExit("v0.12 correctness patch missing local Wants function anchor")
    bridge = bridge.replace(wants_anchor, wants_replacement, 1)

BRIDGE.write_text(bridge, encoding="utf-8")
compile(bridge, str(BRIDGE), "exec")

for required in [
    MARKER,
    "V120_FACT_PRESERVING_RECALL",
    "def _v120_reconcile_wants() -> dict:",
    "def _v120_resolve_capability_gap(",
    "superseded-solved",
    "grounded%conversation%renderer",
    '"reconciliation": reconciliation',
    "_v120_autonomy_feature_curriculum_base = _autonomy_feature_curriculum_once",
]:
    if required not in bridge:
        raise SystemExit(f"v0.12 correctness verifier missing: {required}")

# Foreground verified recall must remain model-free.
start = bridge.find("def _v11774_render_star_recall(")
end = bridge.find("\n\ndef ", start + 10)
renderer_text = bridge[start:end]
for forbidden in ("_choose_ollama_model", "_ollama_generate", "requests.post", "session.post"):
    if forbidden in renderer_text:
        raise SystemExit(f"v0.12 grounded renderer unexpectedly invokes model/transport: {forbidden}")

print("Applied v0.12 stale-Wants reconciliation + fact-preserving conversational renderer completion")
