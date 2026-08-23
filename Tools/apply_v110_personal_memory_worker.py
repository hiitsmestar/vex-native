#!/usr/bin/env python3
from pathlib import Path

path = Path("Bridge/vex_bridge.py")
text = path.read_text(encoding="utf-8")

# Insert the lightweight memory-service adapter after the verified runtime helpers
# have been applied. The worker is a separate process so a memory failure cannot
# take down Bridge, cognition, art, or Remote Support.
helper_marker = "\ndef _runtime_fact_question(message: str) -> bool:\n"
helpers = r'''

MEMORY_WORKER_PORT = 8766
MEMORY_WORKER_BASE = f"http://127.0.0.1:{MEMORY_WORKER_PORT}"
_MEMORY_WORKER_LOCK = threading.Lock()
_MEMORY_WORKER_LAST_START = 0.0


def _memory_worker_exe() -> Path:
    # In the packaged build VexMemoryWorker.exe sits beside VexBridge.exe.
    return Path(sys.executable).resolve().with_name("VexMemoryWorker.exe")


def _memory_worker_health(start_if_needed: bool = False) -> dict:
    global _MEMORY_WORKER_LAST_START
    try:
        import requests
        response = requests.get(f"{MEMORY_WORKER_BASE}/health", timeout=0.45)
        if response.status_code < 400:
            payload = response.json()
            if isinstance(payload, dict) and payload.get("ok"):
                return payload
    except Exception:
        pass

    if not start_if_needed:
        return {"ok": False}

    with _MEMORY_WORKER_LOCK:
        # Recheck after acquiring the lock so parallel Bridge requests do not spawn
        # a pile of memory workers at the same time.
        try:
            import requests
            response = requests.get(f"{MEMORY_WORKER_BASE}/health", timeout=0.35)
            if response.status_code < 400:
                payload = response.json()
                if isinstance(payload, dict) and payload.get("ok"):
                    return payload
        except Exception:
            pass

        exe = _memory_worker_exe()
        if not exe.exists():
            return {"ok": False, "error": "VexMemoryWorker.exe missing"}
        now = time.time()
        if now - _MEMORY_WORKER_LAST_START > 3.0:
            _MEMORY_WORKER_LAST_START = now
            try:
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
                subprocess.Popen(
                    [str(exe), "--serve", "--port", str(MEMORY_WORKER_PORT)],
                    cwd=str(exe.parent),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=flags,
                )
            except Exception as exc:
                return {"ok": False, "error": str(exc)}

        for _ in range(25):
            time.sleep(0.12)
            try:
                import requests
                response = requests.get(f"{MEMORY_WORKER_BASE}/health", timeout=0.35)
                if response.status_code < 400:
                    payload = response.json()
                    if isinstance(payload, dict) and payload.get("ok"):
                        return payload
            except Exception:
                pass
    return {"ok": False, "error": "memory worker did not become ready"}


def _memory_post(route: str, payload: dict, timeout: float = 1.4) -> dict | None:
    health = _memory_worker_health(start_if_needed=True)
    if not health.get("ok"):
        return None
    try:
        import requests
        response = requests.post(
            f"{MEMORY_WORKER_BASE}{route}",
            json=payload,
            timeout=timeout,
        )
        if response.status_code >= 400:
            return None
        data = response.json()
        return data if isinstance(data, dict) else None
    except Exception as exc:
        print(f"[memory] {route} failed: {exc}", flush=True)
        return None


def _personal_memory_retrieval(query: str) -> dict:
    data = _memory_post(
        "/search",
        {
            "query": str(query or "")[:5000],
            # Keep the tiny 1.7B brain's prompt lean. The PC may hold gigabytes of
            # history, but only the most relevant slice belongs in working context.
            "memory_limit": 8,
            "episode_limit": 4,
        },
        timeout=1.6,
    )
    return data if isinstance(data, dict) else {}


def _personal_memory_grounding(query: str) -> str:
    data = _personal_memory_retrieval(query)
    memories = data.get("memories") if isinstance(data.get("memories"), list) else []
    episodes = data.get("episodes") if isinstance(data.get("episodes"), list) else []
    if not memories and not episodes:
        return ""

    lines = [
        "PERSISTENT PERSONAL MEMORY RETRIEVAL",
        "These items came from Vex's local PC memory store. Use them as continuity context instead of inventing missing history.",
        "Explicit/current state supplied elsewhere in this request wins over stale historical details. Newer Star corrections outrank older conflicting memories.",
        "Raw conversation excerpts are historical context, not automatically factual claims; never promote a model-generated sentence to fact merely because it appears in an old chat.",
    ]
    for item in memories[:8]:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "memory")
        subject = str(item.get("subject") or "").strip()
        text_value = str(item.get("text") or "").strip().replace("\n", " ")[:1800]
        if not text_value:
            continue
        prefix = f"[{kind}{'/' + subject if subject else ''}]"
        lines.append(f"{prefix} {text_value}")
    if episodes:
        lines.append("HISTORICAL CONVERSATION EXCERPTS")
        for item in episodes[:4]:
            if not isinstance(item, dict):
                continue
            text_value = str(item.get("text") or "").strip()[:2200]
            if text_value:
                lines.append(text_value)
    return "\n".join(lines)[:14000]


def _memory_record_turn(message: str, reply: str) -> None:
    now = time.time()
    payload = {
        "thread_id": "vexnative-live",
        "source": "bridge-live",
        "messages": [
            {"role": "user", "content": str(message or "")[:50000], "created_at": now},
            {"role": "assistant", "content": str(reply or "")[:50000], "created_at": now + 0.001},
        ],
    }
    # Best effort only. Conversation must still work if memory is unavailable.
    _memory_post("/episode", payload, timeout=1.0)


def _memory_sync_payload(payload: dict) -> dict | None:
    if not isinstance(payload, dict):
        return None
    return _memory_post("/sync", payload, timeout=8.0)

'''

if "MEMORY_WORKER_BASE" not in text:
    if helper_marker not in text:
        raise SystemExit("v0.11 memory helper insertion marker missing")
    text = text.replace(helper_marker, helpers + helper_marker, 1)

# Inject retrieved personal memory into the PC cognition system prompt after the
# existing verified runtime facts. This keeps persona/current state and memory
# distinct instead of flattening everything into one giant prompt.
old_ground = '''    dynamic_system += runtime_grounding
'''
new_ground = '''    dynamic_system += runtime_grounding
    personal_memory = _personal_memory_grounding(message)
    if personal_memory:
        dynamic_system += "\\n\\n" + personal_memory
'''
if old_ground in text:
    text = text.replace(old_ground, new_ground, 1)
elif "personal_memory = _personal_memory_grounding(message)" not in text:
    raise SystemExit("v0.11 cognition memory grounding marker missing")

# Expose memory health through the authenticated Bridge. The worker itself stays
# loopback-only and is never directly reachable from the phone/LAN.
get_marker = '''        if parsed.path == "/llm/status":
'''
get_new = '''        if parsed.path == "/memory/status":
            health = _memory_worker_health(start_if_needed=True)
            self._json(200 if health.get("ok") else 503, health)
            return

        if parsed.path == "/llm/status":
'''
if get_marker in text:
    text = text.replace(get_marker, get_new, 1)
elif 'parsed.path == "/memory/status"' not in text:
    raise SystemExit("v0.11 memory GET route marker missing")

# Sync the iPhone's full native BrainProfile/chat history in batches. This route is
# authenticated by the same Bridge token/pinned-TLS path as every other phone tool.
post_marker = '''        if parsed.path == "/llm/chat":
'''
post_new = r'''        if parsed.path == "/memory/sync":
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length <= 0 or length > 16 * 1024 * 1024:
                    self._json(413, {"ok": False, "error": "memory sync payload too large"})
                    return
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(payload, dict):
                    self._json(400, {"ok": False, "error": "invalid memory sync payload"})
                    return
                result = _memory_sync_payload(payload)
                if result is None:
                    self._json(503, {"ok": False, "error": "personal memory worker unavailable"})
                    return
                self._json(200, result)
            except Exception as exc:
                self._json(500, {"ok": False, "error": f"memory sync failed: {exc}"})
            return

        if parsed.path == "/llm/chat":
'''
if post_marker in text:
    text = text.replace(post_marker, post_new, 1)
elif 'parsed.path == "/memory/sync"' not in text:
    raise SystemExit("v0.11 memory sync route marker missing")

# Record the completed live turn after cognition succeeds. Raw old Vex wording is
# stored only as an episode, not an authoritative memory/fact.
old_result = '''                reply, model = result
                self._json(200, {"ok": True, "reply": reply, "model": model})
'''
new_result = '''                reply, model = result
                _memory_record_turn(message, reply)
                self._json(200, {"ok": True, "reply": reply, "model": model, "memory": "persistent-pc"})
'''
if old_result in text:
    text = text.replace(old_result, new_result, 1)
elif '"memory": "persistent-pc"' not in text:
    raise SystemExit("v0.11 live memory recording marker missing")

# The verified runtime fast path returns before normal cognition. Record that turn
# too so the history is complete without treating the answer as a personal fact.
old_verified = '''                        self._json(200, {
                            "ok": True,
                            "reply": reply,
                            "model": model,
                            "grounding": "verified-runtime",
                        })
                        return
'''
new_verified = '''                        _memory_record_turn(message, reply)
                        self._json(200, {
                            "ok": True,
                            "reply": reply,
                            "model": model,
                            "grounding": "verified-runtime",
                            "memory": "persistent-pc",
                        })
                        return
'''
if old_verified in text:
    text = text.replace(old_verified, new_verified, 1)
elif '"grounding": "verified-runtime"' in text and '"memory": "persistent-pc"' not in text:
    raise SystemExit("v0.11 verified route memory marker missing")

path.write_text(text, encoding="utf-8")
final = path.read_text(encoding="utf-8")
for marker in [
    "MEMORY_WORKER_BASE",
    "def _personal_memory_grounding(",
    "PERSISTENT PERSONAL MEMORY RETRIEVAL",
    'parsed.path == "/memory/status"',
    'parsed.path == "/memory/sync"',
    '"memory": "persistent-pc"',
    "VexMemoryWorker.exe",
]:
    if marker not in final:
        raise SystemExit(f"missing v0.11 memory marker: {marker}")
compile(final, str(path), "exec")
print("Applied v0.11 persistent personal memory worker integration")
