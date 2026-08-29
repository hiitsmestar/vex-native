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
    ("Bridge bundle", bridge, '"agent_runtime_bundle": "0.11.7.54"'),
    ("Autolearn", bridge, "def _project_store_proposal("),
    ("Windows native", bridge, "def _windows_native_visible_windows("),
    ("Remote Support", remote, 'VERSION = "0.11.7.54"'),
    ("Installer", installer, 'BUNDLE_VERSION = "0.11.7.54"'),
]:
    if marker not in text:
        raise SystemExit(f"v0.11.7.55 expected {label} marker missing: {marker}")

anchor = "def _vex_background_services() -> None:\n"
if anchor not in bridge:
    raise SystemExit("v0.11.7.55 Bridge insertion anchor missing")

layer = r'''
# ---------------------------------------------------------------------------
# v0.11.7.55 Cortana-inspired Windows access + autonomous learning guard
#
# Field findings from .54:
# - terminal project tasks could be re-seeded back to research, producing hundreds
#   of proposals from unchanged evidence;
# - EnumWindows could report zero despite an interactive desktop.
#
# .55 preserves the proposal-only safety model while adding terminal-state
# preservation, evidence fingerprints, cooldown/caps, duplicate compaction and a
# supported Windows process-window fallback with interactive-session diagnostics.
# ---------------------------------------------------------------------------
PROJECT_PROPOSAL_PER_TASK_CAP = 6
PROJECT_SAME_EVIDENCE_COOLDOWN_SECONDS = 6 * 3600
PROJECT_ACTIVE_REQUEUE_COOLDOWN_SECONDS = 30 * 60
PROJECT_TERMINAL_STATUSES = {
    "approval-required", "ready-for-review", "staged", "done", "blocked"
}
PROJECT_WAITING_STATUSES = {"waiting-evidence", "cooldown"}
_V11755_COMPACT_LOCK = threading.RLock()
_V11755_COMPACT_DONE = False
_V11755_WINDOW_INVENTORY_METHOD = "unknown"


def _project_v55_evidence_fingerprint_from_receipts(receipts) -> str:
    import hashlib
    normalized = []
    for item in receipts or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip().lower().split("#", 1)[0][:1500]
        title = re.sub(r"\s+", " ", str(item.get("title") or "").strip().lower())[:400]
        if url.startswith("https://"):
            normalized.append((url, title))
    normalized = sorted(set(normalized))
    if not normalized:
        return ""
    payload = json.dumps(normalized, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8", "ignore")).hexdigest()


def _project_v55_evidence_fingerprint(evidence: dict) -> str:
    return _project_v55_evidence_fingerprint_from_receipts((evidence or {}).get("receipts") or [])


def _project_v55_row_fingerprint(row) -> str:
    try:
        validation = json.loads(str(row["validation"] or "{}"))
        value = str(validation.get("evidence_fingerprint") or "").strip()
        if value:
            return value
    except Exception:
        pass
    try:
        receipts = json.loads(str(row["evidence_json"] or "[]"))
    except Exception:
        receipts = []
    return _project_v55_evidence_fingerprint_from_receipts(receipts)


def _project_v55_compact_duplicate_proposals() -> dict:
    """One-time non-destructive compaction: duplicate rows are superseded, not deleted."""
    global _V11755_COMPACT_DONE
    if _V11755_COMPACT_DONE:
        return {"ok": True, "already": True}
    with _V11755_COMPACT_LOCK:
        if _V11755_COMPACT_DONE:
            return {"ok": True, "already": True}
        suppressed = 0
        capped = 0
        try:
            with _PROJECT_DB_LOCK:
                conn = _project_conn()
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS project_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '', updated_at REAL NOT NULL)"
                )
                marker = conn.execute("SELECT value FROM project_meta WHERE key='v11755-compaction' LIMIT 1").fetchone()
                if marker is None:
                    rows = conn.execute(
                        "SELECT id,task_id,evidence_json,validation,status,updated_at FROM project_proposals ORDER BY task_id ASC,id DESC"
                    ).fetchall()
                    seen = set()
                    kept_by_task = {}
                    latest_status = {}
                    for row in rows:
                        task_id = int(row["task_id"] or 0)
                        fp = _project_v55_row_fingerprint(row)
                        if task_id not in latest_status and str(row["status"] or "") != "superseded-duplicate":
                            latest_status[task_id] = str(row["status"] or "staged")
                        key = (task_id, fp) if fp else (task_id, f"unique:{int(row['id'])}")
                        keep = key not in seen
                        if keep:
                            seen.add(key)
                            kept_by_task.setdefault(task_id, []).append(int(row["id"]))
                            if len(kept_by_task[task_id]) > PROJECT_PROPOSAL_PER_TASK_CAP:
                                keep = False
                                capped += 1
                        if not keep and str(row["status"] or "") != "superseded-duplicate":
                            conn.execute(
                                "UPDATE project_proposals SET status='superseded-duplicate',updated_at=? WHERE id=?",
                                (time.time(), int(row["id"])),
                            )
                            suppressed += 1
                    for task_id, status in latest_status.items():
                        if status in PROJECT_TERMINAL_STATUSES:
                            conn.execute(
                                "UPDATE project_tasks SET status=?,next_run=0,updated_at=? WHERE id=?",
                                (status, time.time(), task_id),
                            )
                    conn.execute(
                        "INSERT OR REPLACE INTO project_meta(key,value,updated_at) VALUES ('v11755-compaction',?,?)",
                        (json.dumps({"suppressed": suppressed, "capped": capped}), time.time()),
                    )
                    conn.commit()
                conn.close()
            _V11755_COMPACT_DONE = True
            return {"ok": True, "suppressed": suppressed, "capped": capped}
        except Exception as exc:
            return {"ok": False, "detail": f"v11755 proposal compaction deferred: {exc}"}


_v11755_project_queue_task_base = _project_queue_task


def _project_queue_task(goal: str, category: str = "capability", detail: str = "", source_gap_id: int = 0) -> dict:
    """Never resurrect an existing task simply because the adaptive gap is still open."""
    normalized_goal = re.sub(r"\s+", " ", str(goal or "")).strip()[:1600]
    if len(normalized_goal) < 8:
        return _v11755_project_queue_task_base(goal, category, detail, source_gap_id)
    try:
        with _PROJECT_DB_LOCK:
            conn = _project_conn()
            row = conn.execute(
                "SELECT id,status,public_topic,updated_at,next_run FROM project_tasks WHERE source_gap_id=? AND goal=? ORDER BY id DESC LIMIT 1",
                (int(source_gap_id or 0), normalized_goal),
            ).fetchone()
            conn.close()
        if row is not None:
            status = str(row["status"] or "")
            return {
                "ok": True,
                "task_id": int(row["id"]),
                "public_topic": str(row["public_topic"] or ""),
                "status": status,
                "deduplicated": True,
                "terminal_preserved": status in PROJECT_TERMINAL_STATUSES,
            }
    except Exception:
        pass
    return _v11755_project_queue_task_base(goal, category, detail, source_gap_id)


_v11755_project_next_task_base = _project_next_task


def _project_next_task():
    _project_v55_compact_duplicate_proposals()
    now = time.time()
    try:
        with _PROJECT_DB_LOCK:
            conn = _project_conn()
            row = conn.execute(
                "SELECT * FROM project_tasks WHERE status IN ('queued','research','retry','waiting-evidence','cooldown') AND next_run<=? ORDER BY updated_at ASC LIMIT 1",
                (now,),
            ).fetchone()
            conn.close()
            return row
    except Exception:
        return _v11755_project_next_task_base()


def _project_v55_gate_proposal(task, evidence: dict) -> dict:
    task_id = int(task["id"])
    fp = _project_v55_evidence_fingerprint(evidence)
    if not fp:
        return {"allow": False, "kind": "wait", "detail": "technical evidence fingerprint is empty"}
    now = time.time()
    try:
        with _PROJECT_DB_LOCK:
            conn = _project_conn()
            rows = conn.execute(
                "SELECT id,evidence_json,validation,status,confidence,created_at FROM project_proposals WHERE task_id=? AND status!='superseded-duplicate' ORDER BY id DESC LIMIT 12",
                (task_id,),
            ).fetchall()
            conn.close()
    except Exception as exc:
        return {"allow": False, "kind": "wait", "detail": f"proposal guard database read failed: {exc}"}
    if len(rows) >= PROJECT_PROPOSAL_PER_TASK_CAP:
        return {"allow": False, "kind": "block", "detail": "per-task proposal cap reached; review existing proposals before generating more"}
    for row in rows:
        if _project_v55_row_fingerprint(row) == fp:
            return {
                "allow": False,
                "kind": "wait",
                "detail": "evidence has not materially changed since the existing proposal",
                "existing_proposal_id": int(row["id"]),
            }
    if rows:
        latest_at = float(rows[0]["created_at"] or 0)
        if now - latest_at < PROJECT_SAME_EVIDENCE_COOLDOWN_SECONDS:
            return {"allow": False, "kind": "cooldown", "detail": "per-task proposal cooldown is active"}
        try:
            evidence_conf = float(evidence.get("confidence") or 0)
        except Exception:
            evidence_conf = 0.0
        if evidence_conf < 0.15:
            return {"allow": False, "kind": "wait", "detail": "new evidence confidence is below the repeat-proposal threshold"}
    return {"allow": True, "fingerprint": fp}


_v11755_project_local_proposal_base = _project_local_proposal


def _project_local_proposal(task, evidence: dict) -> dict:
    gate = _project_v55_gate_proposal(task, evidence)
    if not gate.get("allow"):
        prefix = "v11755-block:" if gate.get("kind") == "block" else "v11755-wait:"
        return {"ok": False, "detail": prefix + str(gate.get("detail") or "proposal guard deferred")}
    result = _v11755_project_local_proposal_base(task, evidence)
    if result.get("ok") and isinstance(result.get("proposal"), dict):
        result["proposal"]["_v11755_evidence_fingerprint"] = gate.get("fingerprint")
    return result


_v11755_project_retry_base = _project_retry


def _project_retry(task, detail: str) -> dict:
    text = str(detail or "")
    if text.startswith("v11755-wait:") or text.startswith("v11755-block:"):
        blocked = text.startswith("v11755-block:")
        status = "blocked" if blocked else "waiting-evidence"
        next_run = 0 if blocked else time.time() + PROJECT_SAME_EVIDENCE_COOLDOWN_SECONDS
        clean = text.split(":", 1)[1].strip()[:1600] if ":" in text else text[:1600]
        try:
            with _PROJECT_DB_LOCK:
                conn = _project_conn()
                conn.execute(
                    "UPDATE project_tasks SET status=?,next_run=?,updated_at=?,last_error=? WHERE id=?",
                    (status, next_run, time.time(), clean, int(task["id"])),
                )
                conn.commit()
                conn.close()
        except Exception:
            pass
        return {"ok": True, "task_id": int(task["id"]), "status": status, "detail": clean, "guarded": True}
    return _v11755_project_retry_base(task, detail)


_v11755_project_store_proposal_base = _project_store_proposal


def _project_store_proposal(task, evidence: dict, proposal: dict) -> dict:
    task_id = int(task["id"])
    fp = str((proposal or {}).get("_v11755_evidence_fingerprint") or _project_v55_evidence_fingerprint(evidence))
    try:
        with _PROJECT_DB_LOCK:
            conn = _project_conn()
            rows = conn.execute(
                "SELECT id,evidence_json,validation,status,risk,confidence FROM project_proposals WHERE task_id=? AND status!='superseded-duplicate' ORDER BY id DESC LIMIT 12",
                (task_id,),
            ).fetchall()
            conn.close()
        for row in rows:
            if fp and _project_v55_row_fingerprint(row) == fp:
                status = str(row["status"] or "staged")
                try:
                    with _PROJECT_DB_LOCK:
                        conn = _project_conn()
                        conn.execute("UPDATE project_tasks SET status=?,updated_at=?,last_error='' WHERE id=?", (status, time.time(), task_id))
                        conn.commit()
                        conn.close()
                except Exception:
                    pass
                return {
                    "ok": True,
                    "proposal_id": int(row["id"]),
                    "status": status,
                    "risk": str(row["risk"] or "medium"),
                    "confidence": float(row["confidence"] or 0),
                    "deduplicated": True,
                }
        if len(rows) >= PROJECT_PROPOSAL_PER_TASK_CAP:
            return {"ok": False, "detail": "v11755-block:per-task proposal cap reached"}
    except Exception:
        pass

    stored = _v11755_project_store_proposal_base(task, evidence, proposal)
    if stored.get("ok") and stored.get("proposal_id"):
        try:
            with _PROJECT_DB_LOCK:
                conn = _project_conn()
                row = conn.execute("SELECT validation FROM project_proposals WHERE id=?", (int(stored["proposal_id"]),)).fetchone()
                validation = json.loads(str(row["validation"] or "{}")) if row is not None else {}
                if not isinstance(validation, dict):
                    validation = {}
                validation["evidence_fingerprint"] = fp
                validation["proposal_guard_version"] = "0.11.7.55"
                validation["per_task_cap"] = PROJECT_PROPOSAL_PER_TASK_CAP
                conn.execute(
                    "UPDATE project_proposals SET validation=?,updated_at=? WHERE id=?",
                    (json.dumps(validation, ensure_ascii=False), time.time(), int(stored["proposal_id"])),
                )
                conn.commit()
                conn.close()
        except Exception:
            pass
    return stored


_v11755_project_supervisor_status_base = _project_supervisor_status


def _project_supervisor_status() -> dict:
    compact = _project_v55_compact_duplicate_proposals()
    result = _v11755_project_supervisor_status_base()
    result["version"] = "0.11.7.55"
    result["mode"] = "autonomous-source-grounded-project-learning-guarded"
    result["proposal_dedupe"] = True
    result["evidence_change_required"] = True
    result["per_task_proposal_cap"] = PROJECT_PROPOSAL_PER_TASK_CAP
    result["repeat_cooldown_seconds"] = PROJECT_SAME_EVIDENCE_COOLDOWN_SECONDS
    result["compaction_ok"] = bool(compact.get("ok"))
    try:
        with _PROJECT_DB_LOCK:
            conn = _project_conn()
            result["proposal_total_rows"] = int(conn.execute("SELECT COUNT(*) AS n FROM project_proposals").fetchone()["n"] or 0)
            result["suppressed_duplicates"] = int(conn.execute("SELECT COUNT(*) AS n FROM project_proposals WHERE status='superseded-duplicate'").fetchone()["n"] or 0)
            result["proposals"] = int(conn.execute("SELECT COUNT(*) AS n FROM project_proposals WHERE status!='superseded-duplicate'").fetchone()["n"] or 0)
            result["approval_required"] = int(conn.execute("SELECT COUNT(*) AS n FROM project_proposals WHERE status='approval-required'").fetchone()["n"] or 0)
            conn.close()
    except Exception:
        pass
    return result


# ----- Windows interactive-session and inventory recovery -----
_v11755_windows_native_visible_windows_base = _windows_native_visible_windows


def _windows_native_session_state() -> dict:
    state = {
        "process_session_id": None,
        "active_console_session_id": None,
        "interactive_session_match": False,
        "input_desktop_accessible": False,
    }
    if os.name != "nt":
        return state
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
        current_pid = int(kernel32.GetCurrentProcessId())
        sid = wintypes.DWORD(0)
        if kernel32.ProcessIdToSessionId(wintypes.DWORD(current_pid), ctypes.byref(sid)):
            state["process_session_id"] = int(sid.value)
        active = int(kernel32.WTSGetActiveConsoleSessionId())
        if active != 0xFFFFFFFF:
            state["active_console_session_id"] = active
        state["interactive_session_match"] = (
            state["process_session_id"] is not None
            and state["active_console_session_id"] is not None
            and state["process_session_id"] == state["active_console_session_id"]
        )
    except Exception:
        pass
    try:
        import ctypes
        user32 = ctypes.WinDLL("user32.dll", use_last_error=True)
        DESKTOP_READOBJECTS = 0x0001
        DESKTOP_SWITCHDESKTOP = 0x0100
        desktop = user32.OpenInputDesktop(0, False, DESKTOP_READOBJECTS | DESKTOP_SWITCHDESKTOP)
        if desktop:
            state["input_desktop_accessible"] = True
            user32.CloseDesktop(desktop)
    except Exception:
        pass
    return state


def _windows_native_powershell_windows(limit: int = 64) -> list[dict]:
    if os.name != "nt":
        return []
    try:
        import shutil
        import subprocess
        exe = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
        if not exe:
            return []
        cap = max(1, min(int(limit or 64), 128))
        script = (
            "$ErrorActionPreference='SilentlyContinue';"
            f"$r=Get-Process | Where-Object {{$_.MainWindowHandle -ne 0}} | Select-Object -First {cap} Id,MainWindowHandle,ProcessName,MainWindowTitle;"
            "if($null -eq $r){'[]'}else{$r | ConvertTo-Json -Compress}"
        )
        completed = subprocess.run(
            [exe, "-NoProfile", "-NonInteractive", "-Command", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        raw = str(completed.stdout or "").strip()
        if completed.returncode != 0 or not raw:
            return []
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        rows = []
        for item in data if isinstance(data, list) else []:
            if not isinstance(item, dict):
                continue
            title = str(item.get("MainWindowTitle") or "").strip()
            process_name = str(item.get("ProcessName") or "").strip()
            hwnd = int(item.get("MainWindowHandle") or 0)
            if hwnd <= 0:
                continue
            rows.append({
                "hwnd": hwnd,
                "pid": int(item.get("Id") or 0),
                "title": title[:700],
                "class_name": ("process:" + process_name)[:240],
            })
        return rows[:cap]
    except Exception:
        return []


def _windows_native_visible_windows(limit: int = 64) -> list[dict]:
    global _V11755_WINDOW_INVENTORY_METHOD
    rows = _v11755_windows_native_visible_windows_base(limit=limit)
    if rows:
        _V11755_WINDOW_INVENTORY_METHOD = "enumwindows"
        return rows
    rows = _windows_native_powershell_windows(limit=limit)
    if rows:
        _V11755_WINDOW_INVENTORY_METHOD = "powershell-mainwindow"
        return rows
    state = _windows_native_session_state()
    _V11755_WINDOW_INVENTORY_METHOD = "no-interactive-windows" if state.get("interactive_session_match") else "session-mismatch-or-headless"
    return []


_v11755_windows_native_capabilities_base = _windows_native_capabilities


def _windows_native_capabilities() -> dict:
    result = _v11755_windows_native_capabilities_base()
    session = _windows_native_session_state()
    windows = _windows_native_visible_windows(limit=64)
    result["version"] = "0.11.7.55"
    result.update(session)
    result["window_inventory_method"] = _V11755_WINDOW_INVENTORY_METHOD
    result["native_window_inventory"] = True
    result["visible_window_count"] = len(windows)
    result["cortana_private_api_dependency"] = False
    result["supported_windows_primitives"] = True
    return result


'''

if "# v0.11.7.55 Cortana-inspired Windows access + autonomous learning guard" not in bridge:
    bridge = bridge.replace(anchor, layer + anchor, 1)

# The authenticated local raw-window route remains local; only bump its response identity.
bridge = bridge.replace('"version": "0.11.7.54", "count": len(rows), "windows": rows', '"version": "0.11.7.55", "count": len(rows), "windows": rows', 1)
bridge = bridge.replace('"agent_runtime_bundle": "0.11.7.54"', '"agent_runtime_bundle": "0.11.7.55"', 1)

# Remote Support publishes only sanitized counts/booleans, never raw window titles.
remote = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.55"', remote, count=1, flags=re.M)
remote_anchor = "def maintenance_public(value: dict) -> dict:\n"
remote_layer = r'''_v11755_autolearn_public_base = autolearn_public


def autolearn_public(value: dict) -> dict:
    result = _v11755_autolearn_public_base(value)
    result["version"] = str(value.get("version") or "")[:40] or None
    result["proposal_dedupe"] = yes(value.get("proposal_dedupe"))
    result["evidence_change_required"] = yes(value.get("evidence_change_required"))
    result["per_task_proposal_cap"] = integer(value.get("per_task_proposal_cap"))
    result["repeat_cooldown_seconds"] = integer(value.get("repeat_cooldown_seconds"))
    result["proposal_total_rows"] = integer(value.get("proposal_total_rows"))
    result["suppressed_duplicates"] = integer(value.get("suppressed_duplicates"))
    return result


_v11755_windows_native_public_base = windows_native_public


def windows_native_public(value: dict) -> dict:
    result = _v11755_windows_native_public_base(value)
    result["version"] = str(value.get("version") or "")[:40] or None
    result["interactive_session_match"] = yes(value.get("interactive_session_match"))
    result["input_desktop_accessible"] = yes(value.get("input_desktop_accessible"))
    method = str(value.get("window_inventory_method") or "")[:60]
    result["window_inventory_method"] = method if method in {
        "enumwindows", "powershell-mainwindow", "no-interactive-windows", "session-mismatch-or-headless"
    } else None
    result["supported_windows_primitives"] = yes(value.get("supported_windows_primitives"))
    result["cortana_private_api_dependency"] = yes(value.get("cortana_private_api_dependency"))
    return result


'''
if "_v11755_autolearn_public_base = autolearn_public" not in remote:
    if remote_anchor not in remote:
        raise SystemExit("v0.11.7.55 Remote Support helper anchor missing")
    remote = remote.replace(remote_anchor, remote_layer + remote_anchor, 1)

installer = installer.replace('BUNDLE_VERSION = "0.11.7.54"', 'BUNDLE_VERSION = "0.11.7.55"', 1)
installer = installer.replace('REMOTE_VERSION = "0.11.7.54"', 'REMOTE_VERSION = "0.11.7.55"', 1)
installer = installer.replace("Vex Agent Runtime v0.11.7.54 installed.", "Vex Agent Runtime v0.11.7.55 installed.", 1)

BRIDGE.write_text(bridge, encoding="utf-8")
REMOTE.write_text(remote, encoding="utf-8")
INSTALLER.write_text(installer, encoding="utf-8")

for path, text in [(BRIDGE, bridge), (REMOTE, remote), (INSTALLER, installer)]:
    compile(text, str(path), "exec")

for marker in [
    '"agent_runtime_bundle": "0.11.7.55"',
    "PROJECT_PROPOSAL_PER_TASK_CAP = 6",
    "def _project_v55_compact_duplicate_proposals(",
    "def _project_v55_evidence_fingerprint(",
    "terminal_preserved",
    "evidence has not materially changed",
    "def _windows_native_session_state(",
    "def _windows_native_powershell_windows(",
    "ProcessIdToSessionId",
    "OpenInputDesktop",
    "powershell-mainwindow",
    '"version": "0.11.7.55", "count": len(rows), "windows": rows',
]:
    if marker not in bridge:
        raise SystemExit(f"v0.11.7.55 Bridge marker missing: {marker}")

for marker in [
    'VERSION = "0.11.7.55"',
    "proposal_dedupe",
    "suppressed_duplicates",
    "interactive_session_match",
    "window_inventory_method",
    "cortana_private_api_dependency",
]:
    if marker not in remote:
        raise SystemExit(f"v0.11.7.55 Remote Support marker missing: {marker}")

for marker in [
    'BUNDLE_VERSION = "0.11.7.55"',
    'REMOTE_VERSION = "0.11.7.55"',
    "Vex Agent Runtime v0.11.7.55 installed.",
    "Keep VexNative v0.11.7.49 on the iPhone",
]:
    if marker not in installer:
        raise SystemExit(f"v0.11.7.55 installer marker missing: {marker}")

# Public relay must still never expose raw window or proposal contents.
for forbidden in [
    'bridge_get("/windows/windows"',
    '"recent_proposals":',
    '"source_url":',
    '"artifact_path":',
    '"window_title":',
    '"process_session_id": integer',
    '"active_console_session_id": integer',
]:
    if forbidden in remote:
        raise SystemExit(f"v0.11.7.55 public privacy boundary violated: {forbidden}")

# No retired/private Cortana package dependency and no paid API introduced.
for forbidden in ["Cortana.exe", "Microsoft.Windows.Cortana", "api.openai.com", "OPENAI_API_KEY"]:
    if forbidden in layer:
        raise SystemExit(f"v0.11.7.55 unsupported/private dependency introduced: {forbidden}")

print("Applied v0.11.7.55 Cortana-inspired Windows access + autonomous learning guard")
