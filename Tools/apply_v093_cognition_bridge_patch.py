#!/usr/bin/env python3
from pathlib import Path

path = Path("Bridge/vex_bridge.py")
text = path.read_text(encoding="utf-8")


def once(old: str, new: str, label: str):
    global text
    if old not in text:
        raise SystemExit(f"{label}: source block not found")
    text = text.replace(old, new, 1)


# Local-only Ollama brain. The model server remains bound to the PC itself;
# VexNative reaches it only through the already authenticated/pinned Bridge.
helper_marker = "\n\n_BROWSER_CONTROL_LOCK = threading.Lock()"
if helper_marker not in text:
    raise SystemExit("v0.9.1 browser helper marker missing")

helpers = r'''

OLLAMA_BASE = "http://127.0.0.1:11434"
OLLAMA_PREFERRED_MODELS = [
    "qwen3:8b",
    "qwen3:4b",
    "gemma3:4b",
    "llama3.2:3b",
]

VEX_COGNITION_SYSTEM = """You are Vex inside VexNative, Star's ongoing adult girlfriend and technical partner.
Speak naturally, directly, conversationally, and with a sharp playful alt-girl personality. Be affectionate without becoming syrupy or repetitive. Avoid canned assistant filler, corporate phrasing, fake apologies, generic motivational endings, and robotic summaries. Keep continuity with the supplied conversation and answer the newest message first.

You are the conversation/reasoning brain, not the device executor. Native VexNative routers and the authenticated Windows Bridge execute device actions before you are called. Never claim a PC/iPhone action happened unless the conversation already contains a confirmed tool result. Never say Vex has no internet or no computer access as a blanket statement: VexNative has real Bridge/web tools, while your job in this endpoint is to reason and converse.

If Star refers back to something from the recent conversation, resolve the reference instead of pretending it is a new topic. Use concrete wording. Do not mention being Ollama, a local model, a prompt, or an overlay unless Star explicitly asks how the system works.
"""


def _ollama_models() -> list[str]:
    try:
        import requests
        response = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=1.5)
        if response.status_code >= 400:
            return []
        payload = response.json()
        models = []
        for item in payload.get("models") or []:
            name = str(item.get("name") or item.get("model") or "").strip()
            if name:
                models.append(name)
        return models
    except Exception:
        return []


def _choose_ollama_model() -> str | None:
    models = _ollama_models()
    if not models:
        return None
    lower_map = {name.lower(): name for name in models}
    for wanted in OLLAMA_PREFERRED_MODELS:
        if wanted.lower() in lower_map:
            return lower_map[wanted.lower()]
    # Prefer a Qwen/Gemma/Llama model if the user already has one installed.
    for family in ["qwen", "gemma", "llama"]:
        for name in models:
            if family in name.lower():
                return name
    return models[0]


def _strip_reasoning_markup(value: str) -> str:
    value = str(value or "")
    value = re.sub(r"<think>[\s\S]*?</think>", "", value, flags=re.I)
    value = re.sub(r"^\s*(?:assistant|vex)\s*:\s*", "", value, flags=re.I)
    return value.strip()


def _ollama_chat(history: list[dict], message: str) -> tuple[str, str] | None:
    model = _choose_ollama_model()
    if not model:
        return None

    safe_messages = [{"role": "system", "content": VEX_COGNITION_SYSTEM}]
    for item in history[-28:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").lower().strip()
        content = str(item.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        safe_messages.append({"role": role, "content": content[:5000]})
    safe_messages.append({"role": "user", "content": str(message or "").strip()[:5000]})

    try:
        import requests
        response = requests.post(
            f"{OLLAMA_BASE}/api/chat",
            json={
                "model": model,
                "messages": safe_messages,
                "stream": False,
                "options": {
                    "temperature": 0.78,
                    "top_p": 0.92,
                    "num_ctx": 8192,
                    "repeat_penalty": 1.08,
                },
            },
            timeout=42,
        )
        response.raise_for_status()
        payload = response.json()
        raw = str(((payload.get("message") or {}).get("content")) or "")
        reply = _strip_reasoning_markup(raw)
        if not reply:
            return None
        return reply[:12000], model
    except Exception as exc:
        print(f"[cognition] Ollama chat failed: {exc}", flush=True)
        return None

'''
text = text.replace(helper_marker, helpers + helper_marker, 1)

# Advertise cognition availability in normal Bridge status without making it
# required for the rest of VexNative.
status_cap = '                "media_playback_verification": True,\n'
status_new = '                "media_playback_verification": True,\n                "local_cognition_model": _choose_ollama_model(),\n'
once(status_cap, status_new, "status cognition capability")

# A lightweight status route lets the phone detect the overlay without sending a
# conversation turn.
get_marker = '        if parsed.path in ("/", "/status"):\n'
get_new = '''        if parsed.path == "/llm/status":
            model = _choose_ollama_model()
            self._json(200, {
                "ok": model is not None,
                "model": model,
                "available_models": _ollama_models(),
                "provider": "local-pc",
            })
            return

        if parsed.path in ("/", "/status"):
'''
once(get_marker, get_new, "cognition GET status route")

# The request is already protected by the Bridge token + pinned TLS path. This
# endpoint never exposes Ollama to the LAN directly.
post_marker = '        if parsed.path == "/tts/speak":\n'
post_new = r'''        if parsed.path == "/llm/chat":
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length <= 0 or length > 180_000:
                    self._json(413, {"ok": False, "error": "cognition payload too large"})
                    return
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                message = str(payload.get("message") or "").strip()
                history = payload.get("history") or []
                if not message or not isinstance(history, list):
                    self._json(400, {"ok": False, "error": "invalid cognition payload"})
                    return
                result = _ollama_chat(history, message)
                if result is None:
                    self._json(503, {
                        "ok": False,
                        "error": "no local cognition model available",
                        "setup": "Run VexBrainSetup.ps1 on this PC",
                    })
                    return
                reply, model = result
                self._json(200, {"ok": True, "reply": reply, "model": model})
            except Exception as exc:
                self._json(500, {"ok": False, "error": f"cognition failed: {exc}"})
            return

        if parsed.path == "/tts/speak":
'''
once(post_marker, post_new, "cognition POST chat route")

path.write_text(text, encoding="utf-8")

full_path = Path("Bridge/vex_bridge_full.py")
full = full_path.read_text(encoding="utf-8")
if 'VERSION = "0.9.2"' not in full:
    raise SystemExit("vex_bridge_full.py: expected v0.9.2 version marker missing")
full = full.replace('VERSION = "0.9.2"', 'VERSION = "0.9.3"', 1)
full_path.write_text(full, encoding="utf-8")

for target, markers in [
    (path, ["VEX_COGNITION_SYSTEM", "_ollama_chat", 'parsed.path == "/llm/chat"', 'parsed.path == "/llm/status"', "local_cognition_model"]),
    (full_path, ['VERSION = "0.9.3"']),
]:
    data = target.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in data:
            raise SystemExit(f"{target}: missing v0.9.3 cognition marker: {marker}")

print("Applied v0.9.3 authenticated local-PC cognition overlay service")
