#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
text = BRIDGE.read_text(encoding="utf-8")
MARKER = 'V120_DUAL_BRAIN_ROUTER = "v0.12-tri-brain-v5"'
if MARKER in text:
    print("Tri-brain router already applied")
    raise SystemExit(0)

old_sig = "def _ollama_chat("
if old_sig not in text:
    raise SystemExit("Ollama cognition function missing")
if "def _ollama_models()" not in text:
    raise SystemExit("Ollama model inventory function missing")
if "def _v120_agent_chat(" not in text:
    raise SystemExit("v0.12 agent chat function missing")

# Preserve the proven local 4B legacy path as the fast fallback. Existing legacy
# callers keep calling _ollama_chat(), which becomes the bounded router below.
text = text.replace(old_sig, "def _v120_fast_ollama_chat(", 1)

anchor = "\n\n_BROWSER_CONTROL_LOCK = threading.Lock()"
if anchor not in text:
    raise SystemExit("Bridge helper anchor missing")

helpers = r'''

V120_DUAL_BRAIN_ROUTER = "v0.12-tri-brain-v5"
V120_FAST_MODEL = "vex-qwen3-4b:latest"
V120_MID_MODEL = "vex-qwen35-9b-q6:latest"
V120_DEEP_MODEL = "vex-qwen35-a3b-text:latest"
V120_DEEP_URL = os.environ.get("VEX_DEEP_BRAIN_URL", "http://127.0.0.1:11535").rstrip("/")


def _v120_model_available(name: str) -> bool:
    wanted = str(name or "").lower()
    return wanted in {model.lower() for model in _ollama_models()}


def _v120_deep_health(timeout: float = 0.8) -> bool:
    try:
        import requests
        response = requests.get(f"{V120_DEEP_URL}/health", timeout=timeout)
        return response.status_code < 400 and str((response.json() or {}).get("status") or "").lower() == "ok"
    except Exception:
        return False


def _v120_deep_explicit(message: str) -> bool:
    lower = str(message or "").lower()
    phrases = (
        "use the 35b", "use 35b", "35b model", "35b brain",
        "use the biggest brain", "biggest brain", "ultra deep", "ultra-deep",
        "maximum reasoning", "max reasoning",
    )
    return any(phrase in lower for phrase in phrases)


def _v120_mid_explicit(message: str) -> bool:
    lower = str(message or "").lower()
    phrases = (
        "use the 9b", "use 9b", "9b model", "9b brain",
        "use the big brain", "use big brain", "big-brain", "big brain",
        "smart brain", "think harder", "think carefully", "deep analysis",
        "analyze deeply", "really think this through",
    )
    return any(phrase in lower for phrase in phrases)


def _v120_mid_complex(message: str) -> bool:
    value = str(message or "").strip()
    if len(value) < 180:
        return False
    lower = value.lower()
    signals = (
        "architecture", "root cause", "debug", "diagnose", "compare",
        "tradeoff", "trade-off", "research", "reason through", "analyze",
        "design", "migration", "benchmark", "optimize", "optimise",
        "refactor", "plan", "evaluate",
    )
    return any(signal in lower for signal in signals)


def _v120_select_agent_model(message: str) -> str | None:
    # The user-facing v0.12 agent owns /llm/chat and posts to Ollama directly.
    # Pick its Ollama tier here so rich memory/tool/persona grounding is preserved.
    wants_smart = _v120_deep_explicit(message) or _v120_mid_explicit(message) or _v120_mid_complex(message)
    if wants_smart and _v120_model_available(V120_MID_MODEL):
        return V120_MID_MODEL
    if _v120_model_available(V120_FAST_MODEL):
        return V120_FAST_MODEL
    return _choose_ollama_model()


def _v120_context_messages(history: list[dict], message: str, context: dict | None, mode: str) -> list[dict]:
    context = context if isinstance(context, dict) else {}
    persona = str(context.get("persona") or "").strip()[:1400]
    user_profile = str(context.get("user_profile") or "").strip()[:900]
    system = VEX_COGNITION_SYSTEM + f"""

{mode.upper()} COGNITION MODE
Solve the current request carefully. Preserve supplied Vex/Star continuity, but never invent facts, memories, tool results, or completed actions. Prefer a correct concrete answer over unnecessary length.
"""
    if persona:
        system += "\nVEX PERSONA\n" + persona
    if user_profile:
        system += "\nSTAR / RELATIONSHIP CONTEXT\n" + user_profile
    messages = [{"role": "system", "content": system}]
    for item in history[-5:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").lower().strip()
        content = str(item.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content[:650]})
    messages.append({"role": "user", "content": str(message or "").strip()[:2400]})
    return messages


def _v120_mid_chat(history: list[dict], message: str, context: dict | None = None) -> tuple[str, str] | None:
    if not _v120_model_available(V120_MID_MODEL):
        return None
    try:
        import requests
        session = requests.Session()
        session.trust_env = False
        response = session.post(
            f"{OLLAMA_BASE}/api/chat",
            json={
                "model": V120_MID_MODEL,
                "messages": _v120_context_messages(history, message, context, "smart"),
                "stream": False,
                "think": False,
                "keep_alive": "20m",
                "options": {
                    "temperature": 0.58,
                    "top_p": 0.86,
                    "num_ctx": 2048,
                    "num_predict": 180,
                    "repeat_penalty": 1.05,
                },
            },
            timeout=240,
        )
        response.raise_for_status()
        payload = response.json()
        raw = str(((payload.get("message") or {}).get("content")) or "")
        reply = _strip_reasoning_markup(raw)
        return (reply[:12000], V120_MID_MODEL) if reply else None
    except Exception as exc:
        print(f"[cognition] 9B model failed, falling back: {exc}", flush=True)
        return None


def _v120_deep_chat(history: list[dict], message: str, context: dict | None = None) -> tuple[str, str] | None:
    if not _v120_deep_health():
        return None
    try:
        import requests
        session = requests.Session()
        session.trust_env = False
        response = session.post(
            f"{V120_DEEP_URL}/v1/chat/completions",
            json={
                "model": V120_DEEP_MODEL,
                "messages": _v120_context_messages(history, message, context, "ultra-deep"),
                "max_tokens": 96,
                "temperature": 0.5,
            },
            timeout=300,
        )
        response.raise_for_status()
        payload = response.json()
        choices = payload.get("choices") or []
        raw = str((((choices[0] if choices else {}).get("message") or {}).get("content")) or "")
        reply = _strip_reasoning_markup(raw)
        return (reply[:12000], V120_DEEP_MODEL) if reply else None
    except Exception as exc:
        print(f"[cognition] 35B model failed, falling back: {exc}", flush=True)
        return None


def _ollama_chat(history: list[dict], message: str, context: dict | None = None) -> tuple[str, str] | None:
    # Background cognition calls do not supply context and stay on the proven 4B.
    # This prevents maintenance/learning loops from waking the expensive brains.
    if isinstance(context, dict):
        if _v120_deep_explicit(message):
            result = _v120_deep_chat(history, message, context)
            if result is not None:
                return result
            result = _v120_mid_chat(history, message, context)
            if result is not None:
                return result
        elif _v120_mid_explicit(message) or _v120_mid_complex(message):
            result = _v120_mid_chat(history, message, context)
            if result is not None:
                return result
    return _v120_fast_ollama_chat(history, message, context)

'''
text = text.replace(anchor, helpers + anchor, 1)

# The production /llm/chat route is owned by _v120_agent_chat, not the legacy
# _ollama_chat helper. Patch that function surgically so 9B uses the full agent
# prompt/memory/tool stack. Only explicit 35B requests can bypass to the direct
# mmap server, and if it is not healthy the normal agent falls through to 9B.
agent_start = text.find("def _v120_agent_chat(")
agent_end = text.find("\n\ndef ", agent_start + 10)
if agent_start < 0:
    raise SystemExit("v0.12 agent route missing after tri-brain helper insertion")
if agent_end < 0:
    agent_end = len(text)
agent = text[agent_start:agent_end]

plan_anchor = "    plan = _v120_plan(message)\n"
if plan_anchor not in agent:
    raise SystemExit("v0.12 agent plan anchor missing")
phone_context_expr = "phone_context" if "phone_context" in agent.splitlines()[0] else "None"
deep_gate = (
    "    if _v120_deep_explicit(message) and _v120_deep_health():\n"
    f"        deep_result = _v120_deep_chat(history, message, {phone_context_expr})\n"
    "        if deep_result is not None:\n"
    "            return deep_result\n\n"
)
agent = agent.replace(plan_anchor, deep_gate + plan_anchor, 1)

model_anchor = "    model = _choose_ollama_model()\n"
if model_anchor not in agent:
    raise SystemExit("v0.12 live agent model-selection anchor missing")
agent = agent.replace(model_anchor, "    model = _v120_select_agent_model(message)\n", 1)
text = text[:agent_start] + agent + text[agent_end:]

status_marker = '                "available_models": _ollama_models(),\n'
if status_marker in text:
    status_new = status_marker + (
        '                "fast_model": V120_FAST_MODEL,\n'
        '                "smart_model": V120_MID_MODEL,\n'
        '                "smart_model_available": _v120_model_available(V120_MID_MODEL),\n'
        '                "deep_model": V120_DEEP_MODEL,\n'
        '                "deep_model_available": _v120_deep_health(),\n'
    )
    text = text.replace(status_marker, status_new, 1)

compile(text, str(BRIDGE), "exec")
for required in [
    MARKER,
    "def _v120_mid_chat",
    "def _v120_deep_chat",
    "def _v120_select_agent_model",
    "def _ollama_chat",
    "def _v120_fast_ollama_chat",
    "model = _v120_select_agent_model(message)",
    "deep_result = _v120_deep_chat(history, message",
    "vex-qwen35-9b-q6:latest",
    "vex-qwen35-a3b-text:latest",
]:
    if required not in text:
        raise SystemExit(f"Tri-brain verifier missing: {required}")
BRIDGE.write_text(text, encoding="utf-8")
print("Applied live v0.12 bounded 4B/Q6-9B/35B cognition router v5")
