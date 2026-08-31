#!/usr/bin/env python3
from pathlib import Path

path = Path("Tools/VexRemoteSupport.py")
text = path.read_text(encoding="utf-8")

if 'VERSION = "0.11.7.68"' not in text:
    raise SystemExit("v0.11.7.69 expected .68 Remote Support source")
text = text.replace('VERSION = "0.11.7.68"', 'VERSION = "0.11.7.69"', 1)

anchor = "def execute_command(command: dict, allow_maintenance: bool) -> dict:\n"
if anchor not in text:
    raise SystemExit("v0.11.7.69 execute_command anchor missing")

helpers = r'''
# v0.11.7.69 read-only self-improvement inspection.
# Issue #52 is public, so only technical/non-personal gap text is eligible and
# obvious URLs, e-mail addresses, Windows paths and token-like strings are redacted.
def _self_improvement_scrub(value: object, limit: int = 900) -> str:
    raw = str(value or "")
    raw = re.sub(r"https?://\S+", "[url]", raw, flags=re.I)
    raw = re.sub(r"\b[A-Z]:\\[^\s]+", "[path]", raw, flags=re.I)
    raw = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[email]", raw)
    raw = re.sub(r"\b[A-Za-z0-9_-]{32,}\b", "[redacted]", raw)
    return re.sub(r"\s+", " ", raw).strip()[:limit]


def _technical_gap_text(value: object) -> str | None:
    clean = _self_improvement_scrub(value)
    if not clean or not technical_topic(clean):
        return None
    return clean


def self_improvement_public() -> dict:
    result = {
        "ok": True,
        "privacy": "public relay exposes only sanitized technical gaps and staged upgrade planning data",
        "open_gap_count": 0,
        "technical_gaps": [],
        "private_or_nontechnical_gap_count": 0,
        "staged_upgrade_count": 0,
        "recent_upgrades": [],
    }

    # Upgrade candidates are already planning-only data exposed by the authenticated
    # local Bridge. Keep only the conservative proposal fields needed for review.
    autonomy = bridge_get("/autonomy/status", timeout=15)
    if yes(autonomy.get("ok")):
        result["staged_upgrade_count"] = integer(autonomy.get("upgrade_candidates"))
        rows = autonomy.get("recent_upgrades") if isinstance(autonomy.get("recent_upgrades"), list) else []
        for row in rows[:5]:
            if not isinstance(row, dict):
                continue
            proposal = _technical_gap_text(row.get("proposal"))
            component = _self_improvement_scrub(row.get("component"), 120)
            if not proposal:
                continue
            result["recent_upgrades"].append({
                "id": integer(row.get("id")),
                "component": component,
                "proposal": proposal,
                "risk": _self_improvement_scrub(row.get("risk"), 30) or None,
                "confidence": number(row.get("confidence")),
                "status": _self_improvement_scrub(row.get("status"), 30) or None,
            })

    # Read the same local adaptive DB used by the Bridge. Read-only query only.
    try:
        import os
        import sqlite3
        from pathlib import Path as _Path
        db = _Path(os.environ.get("APPDATA") or _Path.home()) / "VexBridge" / "adaptive" / "vex-adaptive.sqlite3"
        if db.exists():
            uri = db.resolve().as_uri() + "?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=5)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id,request_text,category,detail,priority,status FROM gaps WHERE status='open' ORDER BY priority DESC,updated_at ASC LIMIT 20"
            ).fetchall()
            conn.close()
            result["open_gap_count"] = len(rows)
            hidden = 0
            for row in rows:
                category = str(row["category"] or "").lower()
                if category in {"preference", "naturalness", "conversation"}:
                    hidden += 1
                    continue
                request = _technical_gap_text(row["request_text"])
                detail = _technical_gap_text(row["detail"])
                if not request and not detail:
                    hidden += 1
                    continue
                result["technical_gaps"].append({
                    "id": int(row["id"] or 0),
                    "category": re.sub(r"[^a-z0-9_-]", "", category)[:40],
                    "priority": int(row["priority"] or 0),
                    "request": request,
                    "detail": detail,
                    "status": "open",
                })
            result["private_or_nontechnical_gap_count"] = hidden
        else:
            result["db_available"] = False
    except Exception as exc:
        result["ok"] = False
        result["gap_error_class"] = exc.__class__.__name__
    return result


'''
if "def self_improvement_public(" not in text:
    text = text.replace(anchor, helpers + anchor, 1)

action_anchor = '    if action == "adaptive_status":\n'
if action_anchor not in text:
    # Older reconstructed source inserts adaptive_status before coordination/status helpers.
    action_anchor = '    if action == "maintenance_status":\n'
if action_anchor not in text:
    raise SystemExit("v0.11.7.69 action insertion anchor missing")

action = '''    if action == "self_improvement_status":\n        return {"self_improvement": self_improvement_public()}\n'''
if 'action == "self_improvement_status"' not in text:
    text = text.replace(action_anchor, action + action_anchor, 1)

path.write_text(text, encoding="utf-8")
compile(text, str(path), "exec")
final = path.read_text(encoding="utf-8")
for marker in [
    'VERSION = "0.11.7.69"',
    'def self_improvement_public(',
    'action == "self_improvement_status"',
    'bridge_get("/autonomy/status"',
    'vex-adaptive.sqlite3',
    'category in {"preference", "naturalness", "conversation"}',
]:
    if marker not in final:
        raise SystemExit(f"v0.11.7.69 verifier missing: {marker}")
print("Applied v0.11.7.69 read-only self-improvement inspection")
