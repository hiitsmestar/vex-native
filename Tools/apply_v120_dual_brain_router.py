#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
text = BRIDGE.read_text(encoding="utf-8")
MARKER = 'V120_DUAL_BRAIN_ROUTER = "v0.12-dual-brain-v1"'
if MARKER in text:
    print("Dual-brain router already applied")
    raise SystemExit(0)

if "def _ollama_chat(" not in text:
    raise SystemExit("Ollama cognition function missing")
if "def _ollama_models()" not in text:
    raise SystemExit("Ollama model inventory function missing")

anchor = "\n\n_BROWSER_CONTROL_LOCK = threading.Lock()"
if anchor not in text:
    raise SystemExit("Bridge helper anchor missing")

helpers = r'''

V120_DUAL_BRAIN_ROUTER = "v0.12-dual-brain-v1"
V120_FAST_MODEL = "vex-qwen3-4b:latest"
V120_DEEP_MODEL = "vex-qwen35-a3b-text:latest"


def _v120_running_ollama_models() -> list[str]:
    try:
        import requests
        response = requests.get(f"{OLLAMA_BASE}/api/ps", timeout=1.5)
        if response.status_code >= 400:
            return []
        payload = response.json()
        names = []
        for item in payload.get("models") or []:
            name = str(item.get("name") or item.get("model") or "").strip()
            if name:
                names.append(name)
        return names
    except Exception:
        return []


def _v120_deep_available() -> bool:
    return V120_DEEP_MODEL.lower() in {name.lower() for name in _ollama_models()}


def _v120_deep_warm() -> bool:
    return V120_DEEP_MODEL.lower() in {name.lower() for name in _v120_running_ollama_models()}


def _v120_deep_explicit(message: str) -> bool:
    lower = str(message or "").lower()
    phrases = (
        "use the big brain", "use big brain", "big-brain", "big brain",
        "use the 35b", "use 35b", "35b model", "deep model",
        "think deeply", "deep think", "deep analysis", "analyze deeply",
        "take your time and think", "really think this through",
    )
    return any(phrase in lower for phrase in phrases)


def _v120_complex_for_warm_deep(message: str) -> bool:
    value = str(message or "").strip()
    if len(value) < 220:
        return False
    lower = value.lower()
    signals = (
        "architecture", "root cause", "debug", "diagnose", "compare",
        "tradeoff", "trade-off", "research", "reason through", "analyze",
        "design", "migration", "benchmark", "optimize", "optimise",
    )
    return any(signal in lower for signal in signals)


def _v120_deep_chat(history: list[dict], message: str, context: dict | None = None) -> tuple[str, str] | None:
    if not _v120_deep_available():
        return None
    context = context if isinstance(context, dict) else {}
    persona = str(context.get("persona") or "").strip()[:1400]
    user_profile = str(context.get("user_profile") or "").strip()[:900]
    state = context.get("state") if isinstance(context.get("state"), dict) else {}
    state_bits = []
    for key in ("mood", "outfit", "location", "scene"):
        value = str(state.get(key) or "").strip()
        if value:
            state_bits.append(f"{key}: {value[:350]}")

    system = VEX_COGNITION_SYSTEM + """

DEEP COGNITION MODE
Reason carefully and solve the current request. Preserve established Vex/Star continuity supplied here, but do not invent facts, tool results, memories, or completed actions. Prefer a correct concrete answer over a long answer. This is a slow high-capability pass, so focus on the hard part of the request.
"""
    if persona:
        system += "\nVEX PERSONA\n" + persona
    if user_profile:
        system += "\nSTAR / RELATIONSHIP CONTEXT\n" + user_profile
    if state_bits:
        system += "\nCURRENT VEX STATE\n" + "\n".join(state_bits)

    safe_messages = [{"role": "system", "content": system}]
    for item in history[-4:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").lower().strip()
        content = str(item.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            safe_messages.append({"role": role, "content": content[:500]})
    safe_messages.append({"role": "user", "content": str(message or "").strip()[:2400]})

    try:
        import requests
        response = requests.post(
            f"{OLLAMA_BASE}/api/chat",
            json={
                "model": V120_DEEP_MODEL,
                "messages": safe_messages,
                "stream": False,
                "think": False,
                "keep_alive": "10m",
                "options": {
                    "temperature": 0.58,
                    "top_p": 0.86,
                    "num_ctx": 2048,
                    "num_predict": 160,
                    "repeat_penalty": 1.05,
                },
            },
            timeout=420,
        )
        response.raise_for_status()
        payload = response.json()
        raw = str(((payload.get("message") or {}).get("content")) or "")
        reply = _strip_reasoning_markup(raw)
        if not reply:
            return None
        return reply[:12000], V120_DEEP_MODEL
    except Exception as exc:
        print(f"[cognition] deep model failed, falling back: {exc}", flush=True)
        return None


def _v120_route_cognition(history: list[dict], message: str, context: dict | None = None) -> tuple[str, str] | None:
    use_deep = _v120_deep_explicit(message) or (_v120_deep_warm() and _v120_complex_for_warm_deep(message))
    if use_deep:
        result = _v120_deep_chat(history, message, context)
        if result is not None:
            return result
    return _ollama_chat(history, message, context)

'''
text = text.replace(anchor, helpers + anchor, 1)

old = "                result = _ollama_chat(history, message, context)\n"
new = "                result = _v120_route_cognition(history, message, context)\n"
if old in text:
    text = text.replace(old, new, 1)
else:
    old2 = "                result = _ollama_chat(history, message)\n"
    new2 = "                result = _v120_route_cognition(history, message, None)\n"
    if old2 in text:
        text = text.replace(old2, new2, 1)
    else:
        raise SystemExit("Cognition route callsite missing")

status_marker = '                "available_models": _ollama_models(),\n'
if status_marker in text:
    status_new = status_marker + '                "deep_model": V120_DEEP_MODEL,\n                "deep_model_available": _v120_deep_available(),\n                "deep_model_warm": _v120_deep_warm(),\n'
    text = text.replace(status_marker, status_new, 1)

compile(text, str(BRIDGE), "exec")
for required in [MARKER, "def _v120_deep_chat", "def _v120_route_cognition", "vex-qwen35-a3b-text:latest", "_v120_route_cognition(history, message"]:
    if required not in text:
        raise SystemExit(f"Dual-brain verifier missing: {required}")
BRIDGE.write_text(text, encoding="utf-8")
print("Applied bounded 4B/35B dual-brain cognition router")
