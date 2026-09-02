#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
HOST = Path("Tools/VexWindowsHost-v11740.py")

bridge = BRIDGE.read_text(encoding="utf-8")
if not HOST.exists():
    raise SystemExit("v0.12 local upgrade view missing generated VexWindowsHost-v11740.py")
host = HOST.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# Local-only raw self-improvement inspection.
#
# Public Remote Support intentionally keeps private/relationship/conversation
# learning out of GitHub issue #52. This endpoint is exposed only by the local
# authenticated Bridge and is consumed by the Windows Host on the same PC.
# ---------------------------------------------------------------------------
insert_marker = "def _vex_background_services() -> None:\n"
if insert_marker not in bridge:
    raise SystemExit("v0.12 local upgrade view missing Bridge background-service anchor")

helper = r'''
def _v120_local_json(value, fallback):
    try:
        parsed = json.loads(str(value or ""))
        return parsed if isinstance(parsed, type(fallback)) else fallback
    except Exception:
        return fallback


def _v120_local_upgrade_requests() -> dict:
    """Return raw local self-improvement requests without publishing them remotely."""
    result = {
        "ok": True,
        "privacy": "local-control only; raw companion gaps are never emitted by public Remote Support",
        "gaps": [],
        "upgrades": [],
        "project_proposals": [],
    }

    try:
        with _ADAPTIVE_DB_LOCK:
            conn = _adaptive_conn()
            try:
                _autonomy_ensure_tables(conn)
            except Exception:
                pass
            gap_rows = conn.execute(
                """SELECT id,created_at,updated_at,request_text,category,detail,priority,status
                   FROM gaps WHERE status='open'
                   ORDER BY priority DESC, updated_at ASC, id ASC LIMIT 50"""
            ).fetchall()
            upgrade_rows = conn.execute(
                """SELECT id,created_at,updated_at,gap_id,component,problem,proposal,
                          acceptance_json,evidence,risk,confidence,status
                   FROM upgrade_candidates
                   WHERE status IN ('staged','approval-required','approval_required','ready-for-review','ready_for_review')
                   ORDER BY updated_at DESC,id DESC LIMIT 30"""
            ).fetchall()
            conn.close()

        for row in gap_rows:
            result["gaps"].append({
                "id": int(row["id"]),
                "created_at": float(row["created_at"] or 0),
                "updated_at": float(row["updated_at"] or 0),
                "request": str(row["request_text"] or "")[:5000],
                "category": str(row["category"] or "")[:100],
                "detail": str(row["detail"] or "")[:7000],
                "priority": int(row["priority"] or 0),
                "status": str(row["status"] or "open")[:80],
            })
        for row in upgrade_rows:
            acceptance = _v120_local_json(row["acceptance_json"], [])
            result["upgrades"].append({
                "id": int(row["id"]),
                "gap_id": int(row["gap_id"] or 0),
                "created_at": float(row["created_at"] or 0),
                "updated_at": float(row["updated_at"] or 0),
                "component": str(row["component"] or "")[:300],
                "problem": str(row["problem"] or "")[:7000],
                "proposal": str(row["proposal"] or "")[:12000],
                "acceptance": [str(x)[:1200] for x in acceptance[:20]],
                "evidence": str(row["evidence"] or "")[:5000],
                "risk": str(row["risk"] or "medium")[:50],
                "confidence": float(row["confidence"] or 0),
                "status": str(row["status"] or "staged")[:80],
            })
    except Exception as exc:
        result["adaptive_error"] = f"{exc.__class__.__name__}: {str(exc)[:400]}"

    try:
        with _PROJECT_DB_LOCK:
            conn = _project_conn()
            rows = conn.execute(
                """SELECT p.id,p.task_id,p.created_at,p.updated_at,p.summary,p.component,
                          p.files_json,p.patch_plan,p.tests_json,p.evidence_json,p.risk,
                          p.approval_required,p.confidence,p.validation,p.status,
                          t.goal,t.detail,t.category
                   FROM project_proposals p
                   LEFT JOIN project_tasks t ON t.id=p.task_id
                   WHERE p.status IN ('staged','approval-required','ready-for-review')
                   ORDER BY p.updated_at DESC,p.id DESC LIMIT 30"""
            ).fetchall()
            conn.close()
        for row in rows:
            files = _v120_local_json(row["files_json"], [])
            tests = _v120_local_json(row["tests_json"], [])
            evidence = _v120_local_json(row["evidence_json"], [])
            validation = _v120_local_json(row["validation"], {})
            result["project_proposals"].append({
                "id": int(row["id"]),
                "task_id": int(row["task_id"] or 0),
                "created_at": float(row["created_at"] or 0),
                "updated_at": float(row["updated_at"] or 0),
                "component": str(row["component"] or "")[:300],
                "goal": str(row["goal"] or "")[:5000],
                "detail": str(row["detail"] or "")[:7000],
                "category": str(row["category"] or "")[:100],
                "summary": str(row["summary"] or "")[:7000],
                "plan": str(row["patch_plan"] or "")[:14000],
                "files": [str(x)[:600] for x in files[:20]],
                "tests": [str(x)[:1200] for x in tests[:20]],
                "evidence_count": len(evidence),
                "risk": str(row["risk"] or "medium")[:50],
                "approval_required": bool(row["approval_required"]),
                "confidence": float(row["confidence"] or 0),
                "validation": validation,
                "status": str(row["status"] or "staged")[:80],
            })
    except Exception as exc:
        result["project_error"] = f"{exc.__class__.__name__}: {str(exc)[:400]}"

    result["counts"] = {
        "open_gaps": len(result["gaps"]),
        "staged_upgrades": len(result["upgrades"]),
        "project_proposals": len(result["project_proposals"]),
        "approval_required": sum(1 for x in result["project_proposals"] if x.get("approval_required")),
    }
    return result


'''
if 'def _v120_local_upgrade_requests() -> dict:' not in bridge:
    bridge = bridge.replace(insert_marker, helper + insert_marker, 1)

route_anchor = '        if parsed.path == "/autonomy/status":\n            self._json(200, _autonomy_status())\n            return\n'
route_new = '        if parsed.path == "/autonomy/requests":\n            self._json(200, _v120_local_upgrade_requests())\n            return\n\n' + route_anchor
if 'parsed.path == "/autonomy/requests"' not in bridge:
    if route_anchor not in bridge:
        raise SystemExit("v0.12 local upgrade view missing autonomy status route")
    bridge = bridge.replace(route_anchor, route_new, 1)

# ---------------------------------------------------------------------------
# Purple Windows Host: one-click local report. Nothing in this path traverses
# the public GitHub relay.
# ---------------------------------------------------------------------------
button_anchor = '        ttk.Button(row, text="LAN nodes", command=self.show_nodes).pack(side="left", padx=(8, 0))\n'
button_new = '        ttk.Button(row, text="Vex wants", command=self.show_vex_wants).pack(side="left", padx=(8, 0))\n' + button_anchor
if 'text="Vex wants"' not in host:
    if button_anchor not in host:
        raise SystemExit("v0.12 local upgrade view missing Host LAN-nodes button anchor")
    host = host.replace(button_anchor, button_new, 1)

method_anchor = '    def show_nodes(self):\n'
methods = r'''    def show_vex_wants(self):
        self.append("Vex Host", "Reading Vex's local self-improvement requests…")

        def work():
            data = bridge_get("/autonomy/requests", timeout=8)
            self.after(0, lambda: self._render_vex_wants(data))

        threading.Thread(target=work, daemon=True, name="VexUpgradeRequests").start()

    def _render_vex_wants(self, data: dict):
        if not isinstance(data, dict):
            self.append("Vex Host", "Could not read Vex's request list.")
            return
        status = int(data.get("http_status") or 0)
        if status and status not in range(200, 300):
            self.append("Vex Host", f"Request view failed: HTTP {status}")
            return

        gaps = data.get("gaps") if isinstance(data.get("gaps"), list) else []
        upgrades = data.get("upgrades") if isinstance(data.get("upgrades"), list) else []
        proposals = data.get("project_proposals") if isinstance(data.get("project_proposals"), list) else []
        lines = [
            "WHAT VEX WANTS",
            "Local-only self-improvement requests — nothing here is posted to the public relay.",
            "",
            f"Open gaps: {len(gaps)}   Adaptive upgrades: {len(upgrades)}   Research proposals: {len(proposals)}",
            "",
        ]

        if upgrades:
            lines.append("ADAPTIVE UPGRADE REQUESTS")
            for item in upgrades:
                conf = float(item.get("confidence") or 0)
                lines.extend([
                    f"#{item.get('id')}  {item.get('component') or 'unspecified'}  |  {item.get('status') or 'staged'}  |  risk {item.get('risk') or '?'}  |  confidence {conf:.2f}",
                    f"Problem: {item.get('problem') or '(none)' }",
                    f"Vex wants: {item.get('proposal') or '(none)' }",
                ])
                acceptance = item.get("acceptance") if isinstance(item.get("acceptance"), list) else []
                if acceptance:
                    lines.append("Acceptance: " + " ; ".join(str(x) for x in acceptance))
                evidence = str(item.get("evidence") or "").strip()
                if evidence:
                    lines.append("Evidence: " + evidence)
                lines.append("")

        if proposals:
            lines.append("SOURCE-GROUNDED PROJECT PROPOSALS")
            for item in proposals:
                conf = float(item.get("confidence") or 0)
                approval = "approval required" if item.get("approval_required") else "reviewable"
                lines.extend([
                    f"#{item.get('id')}  {item.get('component') or 'unspecified'}  |  {item.get('status') or 'staged'}  |  {approval}  |  risk {item.get('risk') or '?'}  |  confidence {conf:.2f}",
                    f"Goal: {item.get('goal') or '(none)' }",
                    f"Summary: {item.get('summary') or '(none)' }",
                    f"Plan: {item.get('plan') or '(none)' }",
                ])
                files = item.get("files") if isinstance(item.get("files"), list) else []
                tests = item.get("tests") if isinstance(item.get("tests"), list) else []
                if files:
                    lines.append("Files: " + " ; ".join(str(x) for x in files))
                if tests:
                    lines.append("Tests: " + " ; ".join(str(x) for x in tests))
                if item.get("evidence_count"):
                    lines.append(f"Source receipts: {item.get('evidence_count')}")
                lines.append("")

        if gaps:
            lines.append("OPEN LEARNING / CAPABILITY GAPS")
            for item in gaps:
                lines.extend([
                    f"#{item.get('id')}  {item.get('category') or 'uncategorized'}  |  priority {item.get('priority', 0)}  |  {item.get('status') or 'open'}",
                    f"Request: {item.get('request') or '(none)' }",
                    f"Detail: {item.get('detail') or '(none)' }",
                    "",
                ])

        if not gaps and not upgrades and not proposals:
            lines.append("Vex has no open self-improvement requests right now. ✦")
        if data.get("adaptive_error"):
            lines.append("Adaptive read warning: " + str(data.get("adaptive_error")))
        if data.get("project_error"):
            lines.append("Project-proposal read warning: " + str(data.get("project_error")))

        popup = tk.Toplevel(self)
        popup.title("What Vex Wants")
        popup.geometry("820x650")
        popup.minsize(620, 420)
        popup.configure(bg="#140b18")
        box = tk.Text(popup, bg="#1f1125", fg="#f7edf9", insertbackground="white", relief="flat", wrap="word", font=("Segoe UI", 11))
        box.pack(fill="both", expand=True, padx=14, pady=14)
        box.insert("1.0", "\n".join(lines))
        box.configure(state="disabled")
        controls = ttk.Frame(popup)
        controls.pack(fill="x", padx=14, pady=(0, 14))
        ttk.Button(controls, text="Refresh", command=lambda: [popup.destroy(), self.show_vex_wants()]).pack(side="left")
        ttk.Button(controls, text="Close", command=popup.destroy).pack(side="right")
        self.append("Vex Host", f"Vex has {len(gaps)} open gaps, {len(upgrades)} adaptive upgrades, and {len(proposals)} project proposals.")

'''
if '    def show_vex_wants(self):\n' not in host:
    if method_anchor not in host:
        raise SystemExit("v0.12 local upgrade view missing Host show_nodes method anchor")
    host = host.replace(method_anchor, methods + method_anchor, 1)

BRIDGE.write_text(bridge, encoding="utf-8")
HOST.write_text(host, encoding="utf-8")
compile(bridge, str(BRIDGE), "exec")
compile(host, str(HOST), "exec")

for marker in [
    'def _v120_local_upgrade_requests() -> dict:',
    'parsed.path == "/autonomy/requests"',
    'FROM project_proposals p',
    'raw companion gaps are never emitted by public Remote Support',
]:
    if marker not in bridge:
        raise SystemExit(f"v0.12 local upgrade Bridge marker missing: {marker}")
for marker in [
    'text="Vex wants"',
    'def show_vex_wants(self):',
    'bridge_get("/autonomy/requests", timeout=8)',
    'popup.title("What Vex Wants")',
    'SOURCE-GROUNDED PROJECT PROPOSALS',
]:
    if marker not in host:
        raise SystemExit(f"v0.12 local upgrade Host marker missing: {marker}")

print("Applied local-only What Vex Wants view with raw gaps + staged upgrades + project proposals")
