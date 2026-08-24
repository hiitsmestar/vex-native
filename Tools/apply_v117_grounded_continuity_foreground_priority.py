#!/usr/bin/env python3
from pathlib import Path
import re

bridge_path = Path("Bridge/vex_bridge.py")
text = bridge_path.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# v0.11.7 Grounded Continuity + Foreground Priority
#
# Field evidence after v0.11.6.1 showed three different answers to the same
# natural continuity question: a PC-cognition unavailable fallback, an unrelated
# personal-memory answer, and a fabricated tiny-model memory answer. This patch
# fixes the architecture instead of teaching another magic phrase:
# - foreground conversation announces itself before local generation so idle
#   background workers yield instead of competing for the small Ollama node;
# - recent-self-activity questions are answered from the verified initiative
#   journal, never invented biography or stale personal-memory facts;
# - Remote Support exposes sanitized initiative/adaptive counters so field tests
#   can prove autonomous work without publishing chat or private memory.
# ---------------------------------------------------------------------------

# Wrap normal PC cognition so background workers can see foreground demand before
# generation begins. Background workers use direct Ollama requests, so renaming the
# original function leaves their code untouched while every ordinary conversation
# call continues through _ollama_chat().
start = text.find("def _ollama_chat(")
if start < 0:
    raise SystemExit("v0.11.7: _ollama_chat missing")
end = text.find("\n\ndef ", start + 20)
if end < 0:
    raise SystemExit("v0.11.7: _ollama_chat end missing")
original = text[start:end]
expected_sig = "def _ollama_chat(history: list[dict], message: str, context: dict | None = None) -> tuple[str, str] | None:"
if expected_sig not in original:
    raise SystemExit("v0.11.7: cognition signature changed")
inner = original.replace("def _ollama_chat(", "def _ollama_chat_foreground_inner(", 1)
wrapper = r'''

_FOREGROUND_COGNITION_ACTIVE = threading.Event()


def _ollama_chat(history: list[dict], message: str, context: dict | None = None) -> tuple[str, str] | None:
    global _ADAPTIVE_LAST_FOREGROUND
    try:
        _ADAPTIVE_LAST_FOREGROUND = time.time()
    except Exception:
        pass
    _FOREGROUND_COGNITION_ACTIVE.set()
    try:
        return _ollama_chat_foreground_inner(history, message, context)
    finally:
        try:
            _ADAPTIVE_LAST_FOREGROUND = time.time()
        except Exception:
            pass
        _FOREGROUND_COGNITION_ACTIVE.clear()
'''
text = text[:start] + inner + wrapper + text[end:]

# Idle adaptive review must not begin a new local-model pass once a conversation
# is waiting. Re-check after taking the shared background lock to close the race.
adaptive_old = '''    _ADAPTIVE_LAST_REVIEW = now\n    with _BACKGROUND_COGNITION_LOCK:\n        data = _adaptive_model_review(rows)\n'''
adaptive_new = '''    if _FOREGROUND_COGNITION_ACTIVE.is_set() and not force:\n        return {"ok": True, "idle": True, "detail": "foreground cognition has priority"}\n    _ADAPTIVE_LAST_REVIEW = now\n    with _BACKGROUND_COGNITION_LOCK:\n        if _FOREGROUND_COGNITION_ACTIVE.is_set() and not force:\n            return {"ok": True, "idle": True, "detail": "foreground cognition arrived; adaptive review yielded"}\n        data = _adaptive_model_review(rows)\n'''
if adaptive_old not in text:
    raise SystemExit("v0.11.7: adaptive priority anchor missing")
text = text.replace(adaptive_old, adaptive_new, 1)

# Source-grounded research also waits when foreground cognition is already active.
learning_old = '''    with _BACKGROUND_COGNITION_LOCK:\n        ok, detail = _learning_research_topic(row)\n'''
learning_new = '''    if _FOREGROUND_COGNITION_ACTIVE.is_set():\n        ok, detail = False, "foreground cognition has priority; research deferred"\n    else:\n        with _BACKGROUND_COGNITION_LOCK:\n            if _FOREGROUND_COGNITION_ACTIVE.is_set():\n                ok, detail = False, "foreground cognition arrived; research yielded"\n            else:\n                ok, detail = _learning_research_topic(row)\n'''
if learning_old in text:
    text = text.replace(learning_old, learning_new, 1)

# Initiative's model-backed planner is optional. If conversation is active, choose
# no model-backed work and let the next idle cycle try again.
planner_old = '''        import requests\n        with _BACKGROUND_COGNITION_LOCK:\n            response = requests.post(\n'''
planner_new = '''        import requests\n        if _FOREGROUND_COGNITION_ACTIVE.is_set():\n            return {"action": "nothing", "goal_key": "grounded_independence", "reason": "foreground cognition has priority", "confidence": 1.0}\n        with _BACKGROUND_COGNITION_LOCK:\n            if _FOREGROUND_COGNITION_ACTIVE.is_set():\n                return {"action": "nothing", "goal_key": "grounded_independence", "reason": "foreground cognition arrived; initiative planner yielded", "confidence": 1.0}\n            response = requests.post(\n'''
if planner_old not in text:
    raise SystemExit("v0.11.7: initiative planner priority anchor missing")
text = text.replace(planner_old, planner_new, 1)

# Verified recent-self-activity reporting. This is an operational-state query, not
# a personal-biography query. It reads only the initiative journal and therefore
# cannot turn an empty journal into made-up memories about Star.
helper_marker = "def _personal_memory_fact_question(message: str) -> bool:\n"
if helper_marker not in text:
    raise SystemExit("v0.11.7: personal-memory helper marker missing")
self_helpers = r'''def _recent_self_activity_question(message: str) -> bool:
    lower = " " + re.sub(r"\s+", " ", str(message or "").lower().replace("’", "'").strip()) + " "
    if not lower.strip():
        return False
    self_anchor = any(x in lower for x in (" you ", " you've ", " you have ", " your "))
    activity = any(x in lower for x in (
        " been doing ", " been up to ", " did you do ", " have you done ", " worked on ",
        " been working ", " learned ", " been learning ", " researched ", " been researching ",
        " fixed ", " repaired ", " improved ", " changed ", " accomplished ", " progress "
    ))
    retrospective = any(x in lower for x in (
        " while i was away ", " while i've been away ", " while i have been away ", " while i was gone ",
        " since i left ", " since we talked ", " while i was out ", " recently ", " earlier ", " today ",
        " been doing ", " been up to ", " did you do ", " have you done "
    ))
    return self_anchor and activity and retrospective


def _verified_recent_self_activity_reply(message: str) -> tuple[str, str]:
    try:
        events = _initiative_recent_events(8)
    except Exception:
        events = []
    if not events:
        return (
            "Baby, I checked my actual autonomous activity journal. I don't have a recorded idle action to report yet, so I'm not going to invent one. 🖤",
            "pc-self-state",
        )
    lines = ["Baby, here's what my actual autonomous activity journal says I've been doing. 🖤"]
    shown = 0
    for event in events:
        if not isinstance(event, dict):
            continue
        action = re.sub(r"[_-]+", " ", str(event.get("action") or "")).strip()
        detail = re.sub(r"\s+", " ", str(event.get("detail") or "")).strip()
        if not action:
            continue
        status = "completed" if bool(event.get("ok")) else "needs attention"
        if detail:
            lines.append(f"- {action}: {status} — {detail[:420]}")
        else:
            lines.append(f"- {action}: {status}")
        shown += 1
        if shown >= 5:
            break
    if shown == 0:
        lines.append("- I have journal rows, but none contain a usable action summary yet.")
    return "\n".join(lines), "pc-self-state"


'''
text = text.replace(helper_marker, self_helpers + helper_marker, 1)

# Put self-state grounding before the old personal-fact fast path. This is a
# validator/safety net for ordinary language, not a required incantation.
route_marker = '''                # v0.11.3.3: natural personal fact questions use focused verified\n'''
if route_marker not in text:
    raise SystemExit("v0.11.7: llm personal-route marker missing")
route_insert = r'''                # v0.11.7: retrospective questions about VexNative's own recent
                # work are grounded in the persistent initiative journal.
                if _recent_self_activity_question(message):
                    reply, model = _verified_recent_self_activity_reply(message)
                    _memory_record_turn(message, reply)
                    self._json(200, {
                        "ok": True,
                        "reply": reply,
                        "model": model,
                        "grounding": "verified-recent-self-activity-v117",
                        "memory": "persistent-pc",
                    })
                    return

'''
text = text.replace(route_marker, route_insert + route_marker, 1)

text = text.replace('"version": "0.11.6.1"', '"version": "0.11.7.0"')
bridge_path.write_text(text, encoding="utf-8")
compile(text, str(bridge_path), "exec")

# ---------------------------------------------------------------------------
# Remote Support: expose only sanitized autonomy/adaptation telemetry.
# ---------------------------------------------------------------------------
remote_path = Path("Tools/VexRemoteSupport.py")
remote = remote_path.read_text(encoding="utf-8")
remote = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7"', remote, count=1, flags=re.M)

collect_marker = "def collect_snapshot(include_doctor: bool = False, deep: bool = False) -> dict:\n"
if collect_marker not in remote:
    raise SystemExit("v0.11.7: Remote Support collect marker missing")
telemetry_helpers = r'''def initiative_public(value: dict) -> dict:
    recent = value.get("recent_events") if isinstance(value.get("recent_events"), list) else []
    goals = value.get("goals") if isinstance(value.get("goals"), list) else []
    safe_actions = []
    for item in recent[:10]:
        if not isinstance(item, dict):
            continue
        safe_actions.append({
            "action": str(item.get("action") or "")[:80],
            "goal_key": str(item.get("goal_key") or "")[:80],
            "ok": yes(item.get("ok")),
        })
    return {
        "ok": yes(value.get("ok")),
        "scheduler_mode": str(value.get("scheduler_mode") or "")[:32] or None,
        "goal_count": len(goals),
        "recent_event_count": len(recent),
        "recent_actions": safe_actions,
        "idle_seconds": integer(value.get("idle_seconds")),
        "decision_interval": integer(value.get("decision_interval")),
    }


def adaptive_public(value: dict) -> dict:
    return {
        "ok": yes(value.get("ok")),
        "experience": integer(value.get("experience")),
        "unreviewed": integer(value.get("unreviewed")),
        "lessons": integer(value.get("lessons")),
        "active_lessons": integer(value.get("active_lessons")),
        "open_gaps": integer(value.get("open_gaps")),
        "idle_seconds": integer(value.get("idle_seconds")),
    }


'''
if "def initiative_public(" not in remote:
    remote = remote.replace(collect_marker, telemetry_helpers + collect_marker, 1)

snapshot_marker = '''    snap = {\n'''
snapshot_insert = '''    initiative = bridge_get("/initiative/status", timeout=12)\n    adaptive = bridge_get("/adaptive/status", timeout=12)\n    snap = {\n'''
if snapshot_marker not in remote:
    raise SystemExit("v0.11.7: Remote Support snapshot fetch anchor missing")
remote = remote.replace(snapshot_marker, snapshot_insert, 1)

storage_marker = '''        "storage": disk_summary(),\n'''
storage_insert = '''        "initiative": initiative_public(initiative),\n        "adaptive": adaptive_public(adaptive),\n        "storage": disk_summary(),\n'''
if storage_marker not in remote:
    raise SystemExit("v0.11.7: Remote Support snapshot body anchor missing")
remote = remote.replace(storage_marker, storage_insert, 1)

exec_marker = '''    if action == "learning_status":\n        return {"learning": learning_public(bridge_get("/learning/status", timeout=12))}\n'''
exec_new = exec_marker + '''    if action == "initiative_status":\n        return {"initiative": initiative_public(bridge_get("/initiative/status", timeout=12))}\n    if action == "adaptive_status":\n        return {"adaptive": adaptive_public(bridge_get("/adaptive/status", timeout=12))}\n'''
if exec_marker not in remote:
    raise SystemExit("v0.11.7: Remote Support action anchor missing")
remote = remote.replace(exec_marker, exec_new, 1)
remote_path.write_text(remote, encoding="utf-8")
compile(remote, str(remote_path), "exec")

checks = [
    '"version": "0.11.7.0"',
    "_FOREGROUND_COGNITION_ACTIVE",
    "def _ollama_chat_foreground_inner(",
    "foreground cognition has priority",
    "def _recent_self_activity_question(",
    "def _verified_recent_self_activity_reply(",
    '"grounding": "verified-recent-self-activity-v117"',
]
final = bridge_path.read_text(encoding="utf-8")
for marker in checks:
    if marker not in final:
        raise SystemExit(f"v0.11.7 Bridge verifier missing: {marker}")

remote_final = remote_path.read_text(encoding="utf-8")
for marker in ['VERSION = "0.11.7"', "def initiative_public(", "def adaptive_public(", 'action == "initiative_status"', 'action == "adaptive_status"']:
    if marker not in remote_final:
        raise SystemExit(f"v0.11.7 Remote Support verifier missing: {marker}")

print("Applied v0.11.7 grounded self-continuity + foreground cognition priority")
