#!/usr/bin/env python3
from pathlib import Path
import re
import textwrap

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

class _ForegroundCognitionPreempted(RuntimeError):
    pass


class _BufferedOllamaResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = int(status_code)
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"Ollama HTTP {self.status_code}")

    def json(self) -> dict:
        return self._payload


_FOREGROUND_COGNITION_ACTIVE = threading.Event()
_FOREGROUND_COGNITION_STATE_LOCK = threading.RLock()
_FOREGROUND_COGNITION_COUNT = 0
_FOREGROUND_COGNITION_LAST_ARRIVAL = 0.0
_BACKGROUND_OLLAMA_RESPONSE_LOCK = threading.Lock()
_BACKGROUND_OLLAMA_RESPONSE = None


def _cancel_active_background_ollama() -> None:
    with _BACKGROUND_OLLAMA_RESPONSE_LOCK:
        response = _BACKGROUND_OLLAMA_RESPONSE
    if response is not None:
        try:
            response.close()
        except Exception:
            pass


def _foreground_cognition_enter() -> None:
    global _ADAPTIVE_LAST_FOREGROUND, _FOREGROUND_COGNITION_COUNT, _FOREGROUND_COGNITION_LAST_ARRIVAL
    now = time.time()
    with _FOREGROUND_COGNITION_STATE_LOCK:
        _FOREGROUND_COGNITION_COUNT += 1
        _FOREGROUND_COGNITION_LAST_ARRIVAL = now
        _FOREGROUND_COGNITION_ACTIVE.set()
    try:
        _ADAPTIVE_LAST_FOREGROUND = now
    except Exception:
        pass
    _cancel_active_background_ollama()


def _foreground_cognition_exit() -> None:
    global _ADAPTIVE_LAST_FOREGROUND, _FOREGROUND_COGNITION_COUNT, _FOREGROUND_COGNITION_LAST_ARRIVAL
    now = time.time()
    with _FOREGROUND_COGNITION_STATE_LOCK:
        _FOREGROUND_COGNITION_COUNT = max(0, _FOREGROUND_COGNITION_COUNT - 1)
        _FOREGROUND_COGNITION_LAST_ARRIVAL = now
        if _FOREGROUND_COGNITION_COUNT == 0:
            _FOREGROUND_COGNITION_ACTIVE.clear()
    try:
        _ADAPTIVE_LAST_FOREGROUND = now
    except Exception:
        pass


def _background_ollama_post(payload: dict, timeout: int = 150) -> _BufferedOllamaResponse:
    """Run optional idle inference as a cancellable stream.

    Foreground arrival closes the active response. Ollama can then abandon the
    idle generation instead of making Star's conversation wait behind it.
    """
    global _BACKGROUND_OLLAMA_RESPONSE
    if _FOREGROUND_COGNITION_ACTIVE.is_set():
        raise _ForegroundCognitionPreempted("foreground cognition has priority")
    import requests
    request_payload = dict(payload or {})
    request_payload["stream"] = True
    response = None
    chunks = []
    final_payload = {}
    try:
        response = requests.post(
            f"{OLLAMA_BASE}/api/chat",
            json=request_payload,
            stream=True,
            timeout=(10, max(20, int(timeout))),
        )
        response.raise_for_status()
        with _BACKGROUND_OLLAMA_RESPONSE_LOCK:
            if _FOREGROUND_COGNITION_ACTIVE.is_set():
                response.close()
                raise _ForegroundCognitionPreempted("foreground cognition arrived before idle generation")
            _BACKGROUND_OLLAMA_RESPONSE = response
        for raw in response.iter_lines():
            if _FOREGROUND_COGNITION_ACTIVE.is_set():
                raise _ForegroundCognitionPreempted("foreground cognition interrupted idle generation")
            if not raw:
                continue
            value = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else str(raw))
            if not isinstance(value, dict):
                continue
            if value.get("error"):
                raise RuntimeError(str(value.get("error"))[:240])
            final_payload = value
            message = value.get("message") if isinstance(value.get("message"), dict) else {}
            content = str(message.get("content") or value.get("response") or "")
            if content:
                chunks.append(content)
            if value.get("done") is True:
                break
    except _ForegroundCognitionPreempted:
        raise
    except Exception as exc:
        if _FOREGROUND_COGNITION_ACTIVE.is_set():
            raise _ForegroundCognitionPreempted("foreground cognition closed idle generation") from exc
        raise
    finally:
        with _BACKGROUND_OLLAMA_RESPONSE_LOCK:
            if _BACKGROUND_OLLAMA_RESPONSE is response:
                _BACKGROUND_OLLAMA_RESPONSE = None
        if response is not None:
            try:
                response.close()
            except Exception:
                pass
    payload_out = dict(final_payload)
    message_out = dict(payload_out.get("message") or {})
    message_out["content"] = "".join(chunks)
    payload_out["message"] = message_out
    return _BufferedOllamaResponse(200, payload_out)


def _ollama_chat(history: list[dict], message: str, context: dict | None = None) -> tuple[str, str] | None:
    _foreground_cognition_enter()
    try:
        return _ollama_chat_foreground_inner(history, message, context)
    finally:
        _foreground_cognition_exit()
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

# Initiative's model-backed planner is optional. Target the actual planner
# function, not the earlier upgrade-candidate synthesizer with a similar request.
planner_start = text.find("def _initiative_choose_action(")
planner_end = text.find("\n\ndef ", planner_start + 20)
if planner_start < 0 or planner_end < 0:
    raise SystemExit("v0.11.7: initiative planner function missing")
planner = text[planner_start:planner_end]
planner_old = '''    try:\n        import requests\n        with _BACKGROUND_COGNITION_LOCK:\n            response = requests.post(\n'''
planner_new = '''    try:\n        import requests\n        if _FOREGROUND_COGNITION_ACTIVE.is_set():\n            return {"action": "nothing", "goal_key": "grounded_independence", "reason": "foreground cognition has priority", "confidence": 1.0}\n        with _BACKGROUND_COGNITION_LOCK:\n            if _FOREGROUND_COGNITION_ACTIVE.is_set():\n                return {"action": "nothing", "goal_key": "grounded_independence", "reason": "foreground cognition arrived; initiative planner yielded", "confidence": 1.0}\n            response = requests.post(\n'''
if planner_old not in planner:
    raise SystemExit("v0.11.7: actual initiative planner priority anchor missing")
planner = planner.replace(planner_old, planner_new, 1)
planner_except = '''    except Exception as exc:\n        return {"action": "probe_capability", "goal_key": "system_health", "reason": f"planner deferred: {exc.__class__.__name__}", "confidence": 0.50}\n'''
planner_except_new = '''    except _ForegroundCognitionPreempted:\n        return {"action": "nothing", "goal_key": "grounded_independence", "reason": "foreground cognition preempted idle planner", "confidence": 1.0}\n    except Exception as exc:\n        return {"action": "probe_capability", "goal_key": "system_health", "reason": f"planner deferred: {exc.__class__.__name__}", "confidence": 0.50}\n'''
if planner_except not in planner:
    raise SystemExit("v0.11.7: initiative planner exception anchor missing")
planner = planner.replace(planner_except, planner_except_new, 1)
text = text[:planner_start] + planner + text[planner_end:]

# Optional model-backed idle work uses streaming responses that foreground
# arrival can close. This avoids a conversation waiting behind a non-streaming
# 120-150 second background request on the four-thread field PC.
def replace_background_post(function_name: str) -> None:
    global text
    function_start = text.find(f"def {function_name}(")
    function_end = text.find("\n\ndef ", function_start + 20)
    if function_start < 0 or function_end < 0:
        raise SystemExit(f"v0.11.7: background function missing: {function_name}")
    function_text = text[function_start:function_end]
    pattern = re.compile(
        r'response = requests\.post\(\n'
        r'(?P<indent>[ \t]*)f"\{OLLAMA_BASE\}/api/chat",\n'
        r'(?P=indent)json=\{'
    )
    function_text, count = pattern.subn(
        lambda match: "response = _background_ollama_post(\n" + match.group("indent") + "{",
        function_text,
        count=1,
    )
    if count != 1:
        raise SystemExit(f"v0.11.7: cancellable background post anchor missing: {function_name}")
    text = text[:function_start] + function_text + text[function_end:]


for background_function in (
    "_learning_synthesize",
    "_adaptive_model_review",
    "_autonomy_stage_upgrade_candidate",
    "_initiative_choose_action",
    "_vex_background_services",
):
    replace_background_post(background_function)

# Verified recent-self-activity reporting. This is an operational-state query, not
# a personal-biography query. It reads only the initiative journal and therefore
# cannot turn an empty journal into made-up memories about Star.
helper_marker = "def _personal_memory_fact_question(message: str) -> bool:\n"
if helper_marker not in text:
    raise SystemExit("v0.11.7: personal-memory helper marker missing")
self_helpers = r'''def _recent_self_activity_question(message: str) -> bool:
    lower = " " + re.sub(r"\s+", " ", str(message or "").lower().replace("’", "'").strip()) + " "
    normalized = str(message or "").lower().replace("’", "'")
    lower = " " + re.sub(r"[^a-z0-9']+", " ", normalized).strip() + " "
    if not lower.strip():
        return False
    explicit_self = any(x in lower for x in (" you ", " you've ", " you have ", " your "))
    implicit_update = any(x in lower for x in (
        " catch me up ", " anything new ", " what happened ", " give me an update ", " any progress "
    ))
    self_anchor = explicit_self or implicit_update
    activity = any(x in lower for x in (
        " been doing ", " been up to ", " did you do ", " have you done ", " worked on ",
        " did you work ", " you did ", " what did you ", " what have you been ", " catch me up ",
        " anything new ", " what happened ", " give me an update ",
        " been working ", " learned ", " been learning ", " researched ", " been researching ",
        " fixed ", " repaired ", " improved ", " changed ", " accomplished ", " progress "
    ))
    retrospective = any(x in lower for x in (
        " while i was away ", " while i've been away ", " while i have been away ", " while i was gone ",
        " since i've been gone ", " since i have been gone ", " in my absence ", " since i left ",
        " since we talked ", " since my last message ", " since then ", " while i was out ",
        " recently ", " earlier ", " today ", " catch me up ", " give me an update ",
        " been doing ", " been up to ", " did you do ", " did you work ", " have you done "
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

# Mark foreground as soon as an authenticated /llm/chat request arrives, before
# memory routing or model selection. A finally block keeps the signal correct for
# every early return and error path.
llm_start_marker = '        if parsed.path == "/llm/chat":\n'
llm_end_marker = '        if parsed.path == "/tts/speak":\n'
llm_start = text.find(llm_start_marker)
llm_end = text.find(llm_end_marker, llm_start + len(llm_start_marker))
if llm_start < 0 or llm_end < 0:
    raise SystemExit("v0.11.7: llm handler block missing")
llm_block = text[llm_start:llm_end]
if "_foreground_cognition_enter()" in llm_block:
    raise SystemExit("v0.11.7: llm handler already wrapped")
llm_body = llm_block[len(llm_start_marker):].rstrip() + "\n"
llm_wrapped = (
    llm_start_marker
    + "            _foreground_cognition_enter()\n"
    + "            try:\n"
    + textwrap.indent(llm_body, "    ")
    + "            finally:\n"
    + "                _foreground_cognition_exit()\n\n"
)
text = text[:llm_start] + llm_wrapped + text[llm_end:]

text = text.replace('"version": "0.11.6.1"', '"version": "0.11.7.1"')
bridge_path.write_text(text, encoding="utf-8")
compile(text, str(bridge_path), "exec")

# ---------------------------------------------------------------------------
# Remote Support: expose only sanitized autonomy/adaptation telemetry.
# ---------------------------------------------------------------------------
remote_path = Path("Tools/VexRemoteSupport.py")
remote = remote_path.read_text(encoding="utf-8")
remote = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.1"', remote, count=1, flags=re.M)

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
    '"version": "0.11.7.1"',
    "_FOREGROUND_COGNITION_ACTIVE",
    "def _foreground_cognition_enter(",
    "def _background_ollama_post(",
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
for marker in ['VERSION = "0.11.7.1"', "def initiative_public(", "def adaptive_public(", 'action == "initiative_status"', 'action == "adaptive_status"']:
    if marker not in remote_final:
        raise SystemExit(f"v0.11.7 Remote Support verifier missing: {marker}")

planner_final_start = final.find("def _initiative_choose_action(")
planner_final_end = final.find("\n\ndef ", planner_final_start + 20)
planner_final = final[planner_final_start:planner_final_end]
for marker in ("foreground cognition arrived; initiative planner yielded", "_background_ollama_post(", "except _ForegroundCognitionPreempted:"):
    if marker not in planner_final:
        raise SystemExit(f"v0.11.7 actual initiative planner verifier missing: {marker}")

print("Applied v0.11.7 grounded self-continuity + foreground cognition priority")
