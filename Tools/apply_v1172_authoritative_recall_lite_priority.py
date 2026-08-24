#!/usr/bin/env python3
from pathlib import Path
import re


bridge_path = Path("Bridge/vex_bridge.py")
text = bridge_path.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global text
    if old not in text:
        raise SystemExit(f"v0.11.7.2 missing Bridge anchor: {label}")
    text = text.replace(old, new, 1)


# Explicit personal recall is a verified-data route. Normalize punctuation before
# classification so natural questions ending in "me?" cannot fall into Qwen.
old_classifier = '''def _personal_memory_fact_question(message: str) -> bool:
    lower = " " + str(message or "").lower().replace("’", "'").strip() + " "
    if not lower.strip():
        return False
    recall_words = (" remember", " memory", " memories", " know about me", " know about us")
    personal_words = (" me ", " my ", " us ", " our ", " relationship", " girlfriend", " star")
    return any(word in lower for word in recall_words) and any(word in lower for word in personal_words)
'''
new_classifier = '''def _personal_memory_fact_question(message: str) -> bool:
    normalized = str(message or "").lower().replace("’", "'")
    lower = " " + re.sub(r"[^a-z0-9']+", " ", normalized).strip() + " "
    if not lower.strip():
        return False
    recall_words = (
        " remember ", " remembered ", " memory ", " memories ",
        " know about me ", " know about us ", " know me ",
        " tell me what you know ", " tell me about me ",
    )
    personal_words = (
        " me ", " my ", " us ", " our ", " relationship ",
        " girlfriend ", " star ",
    )
    return any(word in lower for word in recall_words) and any(word in lower for word in personal_words)
'''
replace_once(old_classifier, new_classifier, "punctuation-safe personal recall classifier")


# Raw model replies remain in the durable episode archive for audit/continuity,
# but they are not factual evidence. Only Star-authored lines from those episodes
# may enter a future cognition prompt; verified memories remain the fact source.
old_episodes = '''    if episodes:
        lines.append("HISTORICAL CONVERSATION EXCERPTS")
        for item in episodes[:4]:
            if not isinstance(item, dict):
                continue
            text_value = str(item.get("text") or "").strip()[:2200]
            if text_value:
                lines.append(text_value)
'''
new_episodes = '''    if episodes:
        lines.append("HISTORICAL STAR-SUPPLIED EXCERPTS (context only; verified memories remain the factual authority)")
        for item in episodes[:4]:
            if not isinstance(item, dict):
                continue
            raw_episode = str(item.get("text") or "").strip()
            star_lines = []
            current_role = ""
            for raw_line in raw_episode.splitlines():
                line = raw_line.strip()
                low = line.lower()
                if low.startswith("star:"):
                    current_role = "star"
                    line = line.split(":", 1)[1].strip()
                elif low.startswith("vex:"):
                    current_role = "vex"
                    continue
                if current_role == "star" and line:
                    star_lines.append(line)
            text_value = re.sub(r"\\s+", " ", " ".join(star_lines)).strip()[:2200]
            if text_value:
                lines.append("Star said: " + text_value)
'''
replace_once(old_episodes, new_episodes, "exclude generated assistant prose from factual grounding")


# If the verified fact store cannot answer, respond truthfully with HTTP 200 so
# the phone does not abandon the PC route and invoke startup-safe fallback logic.
old_unavailable = '''                        if verified_memory is None:
                            self._json(503, {
                                "ok": False,
                                "error": "verified personal memory unavailable",
                                "grounding": "verified-personal-memory-unavailable-v1133",
                                "timing_ms": recall_ms,
                            })
                            return
'''
new_unavailable = '''                        if verified_memory is None:
                            reply = "Baby, my verified memory store didn't return a trusted fact for that, so I'm not going to fill the gap with a guess. 🖤"
                            _memory_record_turn(message, reply)
                            self._json(200, {
                                "ok": True,
                                "reply": reply,
                                "model": "pc-memory",
                                "grounding": "verified-personal-memory-unavailable-v1172",
                                "memory": "persistent-pc",
                                "timing_ms": recall_ms,
                            })
                            return
'''
replace_once(old_unavailable, new_unavailable, "truthful verified-memory miss response")
text = text.replace('"grounding": "verified-personal-memory-v1133"', '"grounding": "verified-personal-memory-v1172"', 1)


# The field PC is a lite 8 GB node. Optional idle inference cannot reliably be
# cancelled inside Ollama during long prompt ingestion, so reserve the model for
# foreground work on lite/memory-pressure nodes. Two-token warmups remain allowed.
old_globals = '''_BACKGROUND_OLLAMA_RESPONSE_LOCK = threading.Lock()
_BACKGROUND_OLLAMA_RESPONSE = None


def _cancel_active_background_ollama() -> None:
'''
new_globals = '''_BACKGROUND_OLLAMA_RESPONSE_LOCK = threading.Lock()
_BACKGROUND_OLLAMA_RESPONSE = None
_BACKGROUND_OLLAMA_ACTIVE = False
_BACKGROUND_OLLAMA_DEFERRED = 0
_BACKGROUND_OLLAMA_PREEMPTIONS = 0
_FOREGROUND_COGNITION_ENTRIES = 0


def _background_warmup_payload(payload: dict | None) -> bool:
    value = payload if isinstance(payload, dict) else {}
    options = value.get("options") if isinstance(value.get("options"), dict) else {}
    try:
        num_predict = int(options.get("num_predict") or 0)
        num_ctx = int(options.get("num_ctx") or 0)
        return 0 < num_predict <= 2 and 0 < num_ctx <= 512
    except Exception:
        return False


def _background_model_reserved_for_foreground() -> bool:
    try:
        capacity = _cognition_capacity()
        return str(capacity.get("tier") or "").lower() == "lite" or str(capacity.get("pressure") or "").lower() in {"memory", "art"}
    except Exception:
        return True


def _background_model_policy_label() -> str:
    try:
        capacity = _cognition_capacity()
        tier = str(capacity.get("tier") or "").lower()
        pressure = str(capacity.get("pressure") or "").lower()
        if tier == "lite":
            return "foreground-reserved-lite"
        if pressure in {"memory", "art"}:
            return "foreground-reserved-pressure"
    except Exception:
        return "foreground-reserved-unknown"
    return "cancellable-idle-model"


def _cancel_active_background_ollama() -> None:
'''
replace_once(old_globals, new_globals, "lite-tier background reservation state")

old_cancel = '''def _cancel_active_background_ollama() -> None:
    with _BACKGROUND_OLLAMA_RESPONSE_LOCK:
        response = _BACKGROUND_OLLAMA_RESPONSE
    if response is not None:
'''
new_cancel = '''def _cancel_active_background_ollama() -> None:
    global _BACKGROUND_OLLAMA_PREEMPTIONS
    with _BACKGROUND_OLLAMA_RESPONSE_LOCK:
        response = _BACKGROUND_OLLAMA_RESPONSE
        if response is not None:
            _BACKGROUND_OLLAMA_PREEMPTIONS += 1
    if response is not None:
'''
replace_once(old_cancel, new_cancel, "background preemption counter")

old_enter_global = '''def _foreground_cognition_enter() -> None:
    global _ADAPTIVE_LAST_FOREGROUND, _FOREGROUND_COGNITION_COUNT, _FOREGROUND_COGNITION_LAST_ARRIVAL
'''
new_enter_global = '''def _foreground_cognition_enter() -> None:
    global _ADAPTIVE_LAST_FOREGROUND, _FOREGROUND_COGNITION_COUNT, _FOREGROUND_COGNITION_LAST_ARRIVAL, _FOREGROUND_COGNITION_ENTRIES
'''
replace_once(old_enter_global, new_enter_global, "foreground entry counter global")

old_enter_count = '''    with _FOREGROUND_COGNITION_STATE_LOCK:
        _FOREGROUND_COGNITION_COUNT += 1
        _FOREGROUND_COGNITION_LAST_ARRIVAL = now
'''
new_enter_count = '''    with _FOREGROUND_COGNITION_STATE_LOCK:
        _FOREGROUND_COGNITION_COUNT += 1
        _FOREGROUND_COGNITION_ENTRIES += 1
        _FOREGROUND_COGNITION_LAST_ARRIVAL = now
'''
replace_once(old_enter_count, new_enter_count, "foreground entry count")

old_background_start = '''def _background_ollama_post(payload: dict, timeout: int = 150) -> _BufferedOllamaResponse:
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
'''
new_background_start = '''def _background_ollama_post(payload: dict, timeout: int = 150) -> _BufferedOllamaResponse:
    """Run optional idle inference only when it cannot starve foreground chat."""
    global _BACKGROUND_OLLAMA_RESPONSE, _BACKGROUND_OLLAMA_ACTIVE, _BACKGROUND_OLLAMA_DEFERRED
    request_payload = dict(payload or {})
    request_payload["stream"] = True
    if _FOREGROUND_COGNITION_ACTIVE.is_set():
        with _BACKGROUND_OLLAMA_RESPONSE_LOCK:
            _BACKGROUND_OLLAMA_DEFERRED += 1
        raise _ForegroundCognitionPreempted("foreground cognition has priority")
    if _background_model_reserved_for_foreground() and not _background_warmup_payload(request_payload):
        with _BACKGROUND_OLLAMA_RESPONSE_LOCK:
            _BACKGROUND_OLLAMA_DEFERRED += 1
        raise _ForegroundCognitionPreempted("lite-tier model is reserved for foreground cognition")
    import requests
'''
replace_once(old_background_start, new_background_start, "foreground-reserved background Ollama policy")

old_register = '''            _BACKGROUND_OLLAMA_RESPONSE = response
        for raw in response.iter_lines():
'''
new_register = '''            _BACKGROUND_OLLAMA_RESPONSE = response
            _BACKGROUND_OLLAMA_ACTIVE = True
        for raw in response.iter_lines():
'''
replace_once(old_register, new_register, "background active marker")

old_finally = '''        with _BACKGROUND_OLLAMA_RESPONSE_LOCK:
            if _BACKGROUND_OLLAMA_RESPONSE is response:
                _BACKGROUND_OLLAMA_RESPONSE = None
        if response is not None:
'''
new_finally = '''        with _BACKGROUND_OLLAMA_RESPONSE_LOCK:
            if _BACKGROUND_OLLAMA_RESPONSE is response:
                _BACKGROUND_OLLAMA_RESPONSE = None
            _BACKGROUND_OLLAMA_ACTIVE = False
        if response is not None:
'''
replace_once(old_finally, new_finally, "background completion marker")

coordination_marker = '''

def _ollama_chat(history: list[dict], message: str, context: dict | None = None) -> tuple[str, str] | None:
'''
coordination_helpers = '''

def _cognition_coordination_status() -> dict:
    now = time.time()
    with _FOREGROUND_COGNITION_STATE_LOCK:
        foreground_active = _FOREGROUND_COGNITION_COUNT > 0
        entries = int(_FOREGROUND_COGNITION_ENTRIES)
        last_arrival = float(_FOREGROUND_COGNITION_LAST_ARRIVAL or 0.0)
    with _BACKGROUND_OLLAMA_RESPONSE_LOCK:
        background_active = bool(_BACKGROUND_OLLAMA_ACTIVE)
        deferred = int(_BACKGROUND_OLLAMA_DEFERRED)
        preemptions = int(_BACKGROUND_OLLAMA_PREEMPTIONS)
    return {
        "ok": True,
        "foreground_active": foreground_active,
        "foreground_entries": entries,
        "last_foreground_age_seconds": None if last_arrival <= 0 else max(0, int(now - last_arrival)),
        "background_model_active": background_active,
        "background_model_policy": _background_model_policy_label(),
        "background_deferred": deferred,
        "background_preemptions": preemptions,
    }
'''
if coordination_marker not in text:
    raise SystemExit("v0.11.7.2 missing Bridge anchor: coordination helper insertion")
text = text.replace(coordination_marker, coordination_helpers + coordination_marker, 1)


# Idle adaptive review and staged synthesis stay deterministic/deferred when the
# lite node reserves Qwen for chat. Capability probes and source collection remain.
adaptive_marker = '''    rows = _adaptive_unreviewed_rows()
'''
adaptive_insert = '''    if _background_model_reserved_for_foreground() and not force:
        return {"ok": True, "idle": True, "detail": "local model reserved for foreground; adaptive review deferred"}

    rows = _adaptive_unreviewed_rows()
'''
replace_once(adaptive_marker, adaptive_insert, "lite-tier adaptive deferral")

low_memory_old = '''    low_memory = bool(available and available < IDLE_AUTONOMY_PLANNER_FLOOR_BYTES)
'''
low_memory_new = '''    low_memory = _background_model_reserved_for_foreground() or bool(available and available < IDLE_AUTONOMY_PLANNER_FLOOR_BYTES)
'''
if text.count(low_memory_old) != 2:
    raise SystemExit(f"v0.11.7.2 expected two deterministic scheduler anchors, found {text.count(low_memory_old)}")
text = text.replace(low_memory_old, low_memory_new)
text = text.replace("low-memory deterministic initiative", "foreground-reserved deterministic initiative")
text = text.replace("low-memory mode; model-backed upgrade synthesis deferred", "foreground-reserved mode; model-backed upgrade synthesis deferred")

old_scheduler = '''    available = int((snapshot.get("resources") or {}).get("memory_available") or 0)
    snapshot["scheduler_mode"] = "low-memory" if available and available < IDLE_AUTONOMY_PLANNER_FLOOR_BYTES else "normal"
'''
new_scheduler = '''    available = int((snapshot.get("resources") or {}).get("memory_available") or 0)
    if _background_model_reserved_for_foreground():
        snapshot["scheduler_mode"] = _background_model_policy_label()
    elif available and available < IDLE_AUTONOMY_PLANNER_FLOOR_BYTES:
        snapshot["scheduler_mode"] = "low-memory"
    else:
        snapshot["scheduler_mode"] = "normal"
'''
replace_once(old_scheduler, new_scheduler, "truthful initiative scheduler telemetry")


# Art prompt enhancement is optional; skip its Qwen pass on the lite node. The
# deterministic cleaned prompt and independent Art Worker continue normally.
art_start = text.find("def _art_enhance_prompt(")
art_end = text.find("\n\ndef ", art_start + 20)
if art_start < 0 or art_end < 0:
    raise SystemExit("v0.11.7.2 art prompt enhancer missing")
art_function = text[art_start:art_end]
art_old = '''    model = _choose_ollama_model()
'''
art_new = '''    model = None if _background_model_reserved_for_foreground() else _choose_ollama_model()
'''
if art_old not in art_function:
    raise SystemExit("v0.11.7.2 art model reservation anchor missing")
art_function = art_function.replace(art_old, art_new, 1)
text = text[:art_start] + art_function + text[art_end:]


# Post-art warmup is tiny and useful, but it must remain cancellable if Star talks.
rewarm_start = text.find("def _cognition_rewarm_async(")
rewarm_end = text.find("\n\ndef ", rewarm_start + 20)
if rewarm_start < 0 or rewarm_end < 0:
    raise SystemExit("v0.11.7.2 cognition rewarm function missing")
rewarm = text[rewarm_start:rewarm_end]
rewarm_pattern = re.compile(
    r'response = requests\.post\(\n'
    r'(?P<indent>[ \t]*)f"\{OLLAMA_BASE\}/api/chat",\n'
    r'(?P=indent)json=\{'
)
rewarm, rewarm_count = rewarm_pattern.subn(
    lambda match: "response = _background_ollama_post(\n" + match.group("indent") + "{",
    rewarm,
    count=1,
)
if rewarm_count != 1:
    raise SystemExit("v0.11.7.2 cancellable post-art warmup anchor missing")
text = text[:rewarm_start] + rewarm + text[rewarm_end:]


# Expose sanitized coordination counters for live verification.
llm_status_marker = '''        if parsed.path == "/llm/status":
'''
coordination_route = '''        if parsed.path == "/cognition/coordination":
            self._json(200, _cognition_coordination_status())
            return

'''
replace_once(llm_status_marker, coordination_route + llm_status_marker, "coordination status route")

text = text.replace('"version": "0.11.7.1"', '"version": "0.11.7.2"')
bridge_path.write_text(text, encoding="utf-8")
compile(text, str(bridge_path), "exec")


# ---------------------------------------------------------------------------
# Remote Support: publish only sanitized coordination state and survive
# transient GitHub relay errors without silently ending the visible session.
# ---------------------------------------------------------------------------
remote_path = Path("Tools/VexRemoteSupport.py")
remote = remote_path.read_text(encoding="utf-8")
remote = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.2"', remote, count=1, flags=re.M)

collect_marker = "def collect_snapshot(include_doctor: bool = False, deep: bool = False) -> dict:\n"
coordination_public = '''def coordination_public(value: dict) -> dict:
    return {
        "ok": yes(value.get("ok")),
        "foreground_active": yes(value.get("foreground_active")),
        "foreground_entries": integer(value.get("foreground_entries")),
        "last_foreground_age_seconds": integer(value.get("last_foreground_age_seconds")),
        "background_model_active": yes(value.get("background_model_active")),
        "background_model_policy": str(value.get("background_model_policy") or "")[:48] or None,
        "background_deferred": integer(value.get("background_deferred")),
        "background_preemptions": integer(value.get("background_preemptions")),
    }


'''
if collect_marker not in remote:
    raise SystemExit("v0.11.7.2 Remote Support collect marker missing")
remote = remote.replace(collect_marker, coordination_public + collect_marker, 1)

remote_fetch_old = '''    adaptive = bridge_get("/adaptive/status", timeout=12)
    snap = {
'''
remote_fetch_new = '''    adaptive = bridge_get("/adaptive/status", timeout=12)
    coordination = bridge_get("/cognition/coordination", timeout=8)
    snap = {
'''
if remote_fetch_old not in remote:
    raise SystemExit("v0.11.7.2 Remote Support coordination fetch anchor missing")
remote = remote.replace(remote_fetch_old, remote_fetch_new, 1)

remote_body_old = '''        "adaptive": adaptive_public(adaptive),
        "storage": disk_summary(),
'''
remote_body_new = '''        "adaptive": adaptive_public(adaptive),
        "coordination": coordination_public(coordination),
        "storage": disk_summary(),
'''
if remote_body_old not in remote:
    raise SystemExit("v0.11.7.2 Remote Support coordination body anchor missing")
remote = remote.replace(remote_body_old, remote_body_new, 1)

remote_action_old = '''    if action == "adaptive_status":
        return {"adaptive": adaptive_public(bridge_get("/adaptive/status", timeout=12))}
'''
remote_action_new = remote_action_old + '''    if action == "coordination_status":
        return {"coordination": coordination_public(bridge_get("/cognition/coordination", timeout=8))}
'''
if remote_action_old not in remote:
    raise SystemExit("v0.11.7.2 Remote Support coordination action anchor missing")
remote = remote.replace(remote_action_old, remote_action_new, 1)

loop_start = remote.find("    def loop(self) -> None:\n")
loop_end = remote.find("\n\ndef main() -> int:\n", loop_start)
if loop_start < 0 or loop_end < 0:
    raise SystemExit("v0.11.7.2 Remote Support loop block missing")
resilient_loop = '''    def loop(self) -> None:
        session_announced = False
        end_reason = "timeout_or_error"
        try:
            ready, detail = gh_ready()
            if not ready:
                self.on_status(detail)
                end_reason = "setup_unavailable"
                return
            state = load_state()
            last_id = integer(state.get("last_comment_id"))
            post_comment("session_started", collect_snapshot(include_doctor=False))
            session_announced = True
            end_reason = "stopped"
            self.on_status("Support session is active")
            while not self.stop_event.wait(POLL_SECONDS):
                if time.time() - self.started_at >= SESSION_SECONDS:
                    end_reason = "two_hour_limit"
                    self.on_status("Support session ended after 2 hours")
                    break
                try:
                    comments = fetch_comments()
                    for comment in comments:
                        cid = integer(comment.get("id"))
                        if cid <= last_id:
                            continue
                        last_id = max(last_id, cid)
                        user = comment.get("user") if isinstance(comment.get("user"), dict) else {}
                        if str(user.get("login") or "").lower() != OWNER.lower():
                            continue
                        command = parse_command(str(comment.get("body") or ""))
                        if not command:
                            continue
                        target = str(command.get("node_id") or "").strip()
                        if target and target != node_id() and target != "all":
                            continue
                        command_id = str(command.get("id") or f"comment-{cid}")[:80]
                        self.on_status(f"Running {str(command.get('action') or 'command')}…")
                        result = execute_command(command, allow_maintenance=bool(self.allow_maintenance()))
                        post_comment("command_result", {"command_id": command_id, "action": str(command.get("action") or "")[:80], "result": result})
                        self.on_status("Support session is active")
                    state = load_state()
                    state["last_comment_id"] = last_id
                    save_state(state)
                except Exception as exc:
                    self.on_status(f"Support relay retrying after {exc.__class__.__name__}; session remains active")
                    continue
        except Exception as exc:
            end_reason = "startup_error"
            self.on_status(f"Support error: {exc.__class__.__name__}")
        finally:
            if session_announced:
                try:
                    post_comment("session_ended", {"reason": "stopped" if self.stop_event.is_set() else end_reason})
                except Exception:
                    pass
'''
remote = remote[:loop_start] + resilient_loop + remote[loop_end:]
remote_path.write_text(remote, encoding="utf-8")
compile(remote, str(remote_path), "exec")


bridge_checks = [
    '"version": "0.11.7.2"',
    "def _personal_memory_fact_question(",
    "verified-personal-memory-v1172",
    "verified-personal-memory-unavailable-v1172",
    "HISTORICAL STAR-SUPPLIED EXCERPTS",
    "def _background_model_reserved_for_foreground(",
    "foreground-reserved-lite",
    "def _cognition_coordination_status(",
    'parsed.path == "/cognition/coordination"',
]
final = bridge_path.read_text(encoding="utf-8")
for marker in bridge_checks:
    if marker not in final:
        raise SystemExit(f"v0.11.7.2 Bridge verifier missing: {marker}")

remote_checks = [
    'VERSION = "0.11.7.2"',
    "def coordination_public(",
    'action == "coordination_status"',
    "session remains active",
    'end_reason = "two_hour_limit"',
]
remote_final = remote_path.read_text(encoding="utf-8")
for marker in remote_checks:
    if marker not in remote_final:
        raise SystemExit(f"v0.11.7.2 Remote Support verifier missing: {marker}")

print("Applied v0.11.7.2 authoritative recall + lite foreground reservation + resilient relay")
