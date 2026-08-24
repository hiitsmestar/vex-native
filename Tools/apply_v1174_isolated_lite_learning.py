#!/usr/bin/env python3
from pathlib import Path
import re


bridge_path = Path("Bridge/vex_bridge.py")
text = bridge_path.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global text
    if old not in text:
        raise SystemExit(f"v0.11.7.4 missing Bridge anchor: {label}")
    text = text.replace(old, new, 1)


def replace_function(name: str, replacement: str) -> None:
    global text
    start = text.find(f"def {name}(")
    if start < 0:
        raise SystemExit(f"v0.11.7.4 missing Bridge function: {name}")
    end = text.find("\n\ndef ", start + 5)
    if end < 0:
        raise SystemExit(f"v0.11.7.4 could not bound Bridge function: {name}")
    text = text[:start] + replacement.rstrip() + text[end:]


# Adaptive review, autonomous improvement, and initiative used to share one
# sequential scheduler thread. A slow autonomy/initiative pass could therefore
# prevent later adaptive reviews from ever running. Give each subsystem its own
# bounded loop and publish only sanitized liveness telemetry for adaptive review.
adaptive_telemetry_old = '''_ADAPTIVE_LAST_REVIEW_DETAIL = "no adaptive review has completed this process"
_ADAPTIVE_DETERMINISTIC_REVIEWS = 0
'''
adaptive_telemetry_new = '''_ADAPTIVE_LAST_REVIEW_DETAIL = "no adaptive review has completed this process"
_ADAPTIVE_DETERMINISTIC_REVIEWS = 0
_ADAPTIVE_WORKER_INITIAL_DELAY_SECONDS = 15
_ADAPTIVE_WORKER_INTERVAL_SECONDS = 30
_ADAPTIVE_WORKER_STARTED_AT = 0.0
_ADAPTIVE_WORKER_HEARTBEAT_AT = 0.0
_ADAPTIVE_WORKER_LAST_OK = None
_ADAPTIVE_WORKER_LAST_ERROR_CLASS = ""
_ADAPTIVE_WORKER_CYCLES = 0
'''
replace_once(adaptive_telemetry_old, adaptive_telemetry_new, "adaptive worker telemetry globals")


adaptive_status = r'''def _adaptive_status() -> dict:
    now = time.time()
    heartbeat_age = None
    if _ADAPTIVE_WORKER_HEARTBEAT_AT > 0:
        heartbeat_age = max(0, int(now - _ADAPTIVE_WORKER_HEARTBEAT_AT))
    worker_alive = bool(
        _ADAPTIVE_WORKER_STARTED_AT > 0
        and heartbeat_age is not None
        and heartbeat_age <= max(120, _ADAPTIVE_WORKER_INTERVAL_SECONDS * 4)
    )
    result = {
        "ok": True,
        "db": str(ADAPTIVE_DB),
        "idle_seconds": ADAPTIVE_IDLE_SECONDS,
        "review_mode": "deterministic-lite" if _background_model_reserved_for_foreground() else "model-assisted",
        "last_review_mode": _ADAPTIVE_LAST_REVIEW_MODE,
        "last_review_detail": _ADAPTIVE_LAST_REVIEW_DETAIL,
        "deterministic_reviews": int(_ADAPTIVE_DETERMINISTIC_REVIEWS),
        "worker_started": bool(_ADAPTIVE_WORKER_STARTED_AT > 0),
        "worker_alive": worker_alive,
        "worker_heartbeat_age_seconds": heartbeat_age,
        "worker_last_ok": _ADAPTIVE_WORKER_LAST_OK,
        "worker_last_error_class": str(_ADAPTIVE_WORKER_LAST_ERROR_CLASS or "")[:80],
        "worker_cycles": int(_ADAPTIVE_WORKER_CYCLES),
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
        result["ok"] = False
        result["error"] = str(exc)[:300]
    return result
'''
replace_function("_adaptive_status", adaptive_status)


old_combined_loop = '''def _adaptive_worker_loop() -> None:
    time.sleep(90)
    while True:
        try:
            _adaptive_worker_once(force=False)
            _autonomy_worker_once(force=False)
            _initiative_worker_once(force=False)
        except Exception as exc:
            print(f"[adaptive] worker warning: {exc}", flush=True)
        time.sleep(ADAPTIVE_LOOP_SECONDS)
'''
isolated_loops = r'''def _adaptive_worker_cycle(force: bool = False) -> dict:
    global _ADAPTIVE_WORKER_HEARTBEAT_AT, _ADAPTIVE_WORKER_LAST_OK
    global _ADAPTIVE_WORKER_LAST_ERROR_CLASS, _ADAPTIVE_WORKER_CYCLES
    _ADAPTIVE_WORKER_HEARTBEAT_AT = time.time()
    _ADAPTIVE_WORKER_CYCLES += 1
    try:
        result = _adaptive_worker_once(force=force)
        if not isinstance(result, dict):
            result = {"ok": False, "detail": "adaptive worker returned an invalid result"}
        _ADAPTIVE_WORKER_LAST_OK = bool(result.get("ok"))
        _ADAPTIVE_WORKER_LAST_ERROR_CLASS = ""
        return result
    except Exception as exc:
        _ADAPTIVE_WORKER_LAST_OK = False
        _ADAPTIVE_WORKER_LAST_ERROR_CLASS = exc.__class__.__name__
        print(f"[adaptive] cycle warning: {exc.__class__.__name__}", flush=True)
        return {"ok": False, "detail": "adaptive cycle failed", "error_class": exc.__class__.__name__}
    finally:
        _ADAPTIVE_WORKER_HEARTBEAT_AT = time.time()


def _adaptive_worker_loop() -> None:
    global _ADAPTIVE_WORKER_STARTED_AT, _ADAPTIVE_WORKER_HEARTBEAT_AT
    _ADAPTIVE_WORKER_STARTED_AT = time.time()
    _ADAPTIVE_WORKER_HEARTBEAT_AT = _ADAPTIVE_WORKER_STARTED_AT
    time.sleep(_ADAPTIVE_WORKER_INITIAL_DELAY_SECONDS)
    while True:
        _adaptive_worker_cycle(force=False)
        time.sleep(_ADAPTIVE_WORKER_INTERVAL_SECONDS)


def _autonomy_worker_loop() -> None:
    time.sleep(45)
    while True:
        try:
            _autonomy_worker_once(force=False)
        except Exception as exc:
            print(f"[autonomy] worker warning: {exc.__class__.__name__}", flush=True)
        time.sleep(ADAPTIVE_LOOP_SECONDS)


def _initiative_scheduler_loop() -> None:
    time.sleep(60)
    while True:
        try:
            _initiative_worker_once(force=False)
        except Exception as exc:
            print(f"[initiative] worker warning: {exc.__class__.__name__}", flush=True)
        time.sleep(ADAPTIVE_LOOP_SECONDS)
'''
replace_once(old_combined_loop, isolated_loops, "combined adaptive/autonomy/initiative loop")

replace_once(
    '    threading.Thread(target=_adaptive_worker_loop, daemon=True, name="VexAdaptiveLearning").start()\n',
    '    threading.Thread(target=_adaptive_worker_loop, daemon=True, name="VexAdaptiveLearning").start()\n'
    '    threading.Thread(target=_autonomy_worker_loop, daemon=True, name="VexAutonomousImprovement").start()\n'
    '    threading.Thread(target=_initiative_scheduler_loop, daemon=True, name="VexInitiativeScheduler").start()\n',
    "isolated background scheduler threads",
)

replace_once(
    '            result = _adaptive_worker_once(force=True)\n',
    '            result = _adaptive_worker_cycle(force=True)\n',
    "adaptive run heartbeat cycle",
)

text = text.replace('"grounding": "verified-personal-memory-v1173"', '"grounding": "verified-personal-memory-v1174"')
text = text.replace('"grounding": "verified-personal-memory-unavailable-v1173"', '"grounding": "verified-personal-memory-unavailable-v1174"')
text = text.replace('"version": "0.11.7.3"', '"version": "0.11.7.4"')
bridge_path.write_text(text, encoding="utf-8")
compile(text, str(bridge_path), "exec")


# Remote Support can now prove that the adaptive worker is alive and deliberately
# run one bounded adaptive pass. Returned data is counts/mode/liveness only.
remote_path = Path("Tools/VexRemoteSupport.py")
remote = remote_path.read_text(encoding="utf-8")
remote = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.4"', remote, count=1, flags=re.M)


def replace_remote_function(name: str, replacement: str) -> None:
    global remote
    start = remote.find(f"def {name}(")
    if start < 0:
        raise SystemExit(f"v0.11.7.4 missing Remote Support function: {name}")
    end = remote.find("\n\ndef ", start + 5)
    if end < 0:
        raise SystemExit(f"v0.11.7.4 could not bound Remote Support function: {name}")
    remote = remote[:start] + replacement.rstrip() + remote[end:]


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
        "worker_started": yes(value.get("worker_started")),
        "worker_alive": yes(value.get("worker_alive")),
        "worker_heartbeat_age_seconds": integer(value.get("worker_heartbeat_age_seconds")),
        "worker_last_ok": yes(value.get("worker_last_ok")),
        "worker_last_error_class": str(value.get("worker_last_error_class") or "")[:80] or None,
        "worker_cycles": integer(value.get("worker_cycles")),
    }
'''
replace_remote_function("adaptive_public", remote_adaptive)

remote_anchor = '''    if action == "adaptive_status":
        return {"adaptive": adaptive_public(bridge_get("/adaptive/status", timeout=12))}
'''
remote_run = '''    if action == "adaptive_status":
        return {"adaptive": adaptive_public(bridge_get("/adaptive/status", timeout=12))}
    if action == "adaptive_run":
        result = bridge_post("/adaptive/run", {}, timeout=45)
        return {"adaptive_run": {
            "ok": yes(result.get("ok")),
            "reviewed": integer(result.get("reviewed")),
            "learned": integer(result.get("learned")),
            "gaps": integer(result.get("gaps")),
            "review_mode": str(result.get("review_mode") or "")[:32] or None,
            "http_status": integer(result.get("http_status")),
            "error_class": str(result.get("error_class") or result.get("error") or "")[:80] or None,
        }}
'''
if remote_anchor not in remote:
    raise SystemExit("v0.11.7.4 Remote Support adaptive command anchor missing")
remote = remote.replace(remote_anchor, remote_run, 1)
remote_path.write_text(remote, encoding="utf-8")
compile(remote, str(remote_path), "exec")


bridge_checks = [
    '"version": "0.11.7.4"',
    "verified-personal-memory-v1174",
    "verified-personal-memory-unavailable-v1174",
    "def _adaptive_worker_cycle(",
    "def _autonomy_worker_loop(",
    "def _initiative_scheduler_loop(",
    'name="VexAutonomousImprovement"',
    'name="VexInitiativeScheduler"',
    'result = _adaptive_worker_cycle(force=True)',
    '"worker_alive": worker_alive',
]
final = bridge_path.read_text(encoding="utf-8")
for marker in bridge_checks:
    if marker not in final:
        raise SystemExit(f"v0.11.7.4 Bridge verifier missing: {marker}")

remote_checks = [
    'VERSION = "0.11.7.4"',
    'action == "adaptive_run"',
    '"worker_alive": yes(value.get("worker_alive"))',
    '"worker_heartbeat_age_seconds": integer(value.get("worker_heartbeat_age_seconds"))',
]
remote_final = remote_path.read_text(encoding="utf-8")
for marker in remote_checks:
    if marker not in remote_final:
        raise SystemExit(f"v0.11.7.4 Remote Support verifier missing: {marker}")

print("Applied v0.11.7.4 isolated lite learning + live worker verification")
