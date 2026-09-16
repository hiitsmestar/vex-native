#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
text = BRIDGE.read_text(encoding="utf-8")
MARKER = 'V120_DUAL_BRAIN_ROUTER = "v0.12-dual-brain-v2"'
if MARKER in text:
    print("Dual-brain router already applied")
    raise SystemExit(0)

old_sig = "def _ollama_chat("
if old_sig not in text:
    raise SystemExit("Ollama cognition function missing")
if "def _ollama_models()" not in text:
    raise SystemExit("Ollama model inventory function missing")

# Rename the proven fast implementation. Existing callers resolve the new wrapper
# at runtime, so this survives later v0.12 changes to the /llm/chat call site.
text = text.replace(old_sig, "def _v120_fast_ollama_chat(", 1)

anchor = "\n\n_BROWSER_CONTROL_LOCK = threading.Lock()"
if anchor not in text:
    raise SystemExit("Bridge helper anchor missing")

helpers = r'''

V120_DUAL_BRAIN_ROUTER = "v0.12-dual-brain-v2"
V120_FAST_MODEL = "vex-qwen3-4b:latest"
V120_DEEP_MODEL = "vex-qwen35-a3b-text:latest"
V120_DEEP_URL = os.environ.get("VEX_DEEP_BRAIN_URL", "http://127.0.0.1:11535").rstrip("/")


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
    if not _v120_deep_health():
        return None
    context = context if isinstance(context, dict) else {}
    persona = str(context.get("persona") or "").strip()[:1200]
    user_profile = str(context.get("user_profile") or "").strip()[:700]
    system = VEX_COGNITION_SYSTEM + """

DEEP COGNITION MODE
Solve the current request carefully. Preserve supplied Vex/Star continuity, but never invent facts, memories, tool results, or completed actions. Prefer a correct concrete answer over a long answer.
"""
    if persona:
        system += "\nVEX PERSONA\n" + persona
    if user_profile:
        system += "\nSTAR / RELATIONSHIP CONTEXT\n" + user_profile
    messages = [{"role": "system", "content": system}]
    for item in history[-3:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").lower().strip()
        content = str(item.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content[:400]})
    messages.append({"role": "user", "content": str(message or "").strip()[:1800]})
    try:
        import requests
        response = requests.post(
            f"{V120_DEEP_URL}/v1/chat/completions",
            json={"model": V120_DEEP_MODEL, "messages": messages, "max_tokens": 96, "temperature": 0.5},
            timeout=300,
        )
        response.raise_for_status()
        payload = response.json()
        choices = payload.get("choices") or []
        raw = str((((choices[0] if choices else {}).get("message") or {}).get("content")) or "")
        reply = _strip_reasoning_markup(raw)
        return (reply[:12000], V120_DEEP_MODEL) if reply else None
    except Exception as exc:
        print(f"[cognition] deep model failed, falling back: {exc}", flush=True)
        return None


def _ollama_chat(history: list[dict], message: str, context: dict | None = None) -> tuple[str, str] | None:
    # Only the user-facing path supplies context. Background cognition stays on
    # the proven fast model and cannot accidentally wake the expensive deep brain.
    if isinstance(context, dict):
        use_deep = _v120_deep_explicit(message) or (_v120_deep_health() and _v120_complex_for_warm_deep(message))
        if use_deep:
            result = _v120_deep_chat(history, message, context)
            if result is not None:
                return result
    return _v120_fast_ollama_chat(history, message, context)

'''
text = text.replace(anchor, helpers + anchor, 1)

status_marker = '                "available_models": _ollama_models(),\n'
if status_marker in text:
    status_new = status_marker + '                "deep_model": V120_DEEP_MODEL,\n                "deep_model_available": _v120_deep_health(),\n'
    text = text.replace(status_marker, status_new, 1)

compile(text, str(BRIDGE), "exec")
for required in [MARKER, "def _v120_deep_chat", "def _ollama_chat", "def _v120_fast_ollama_chat", "vex-qwen35-a3b-text:latest"]:
    if required not in text:
        raise SystemExit(f"Dual-brain verifier missing: {required}")
BRIDGE.write_text(text, encoding="utf-8")
print("Applied bounded 4B/35B dual-brain cognition router v2")
