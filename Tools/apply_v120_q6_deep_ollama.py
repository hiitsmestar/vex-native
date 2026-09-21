#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
text = BRIDGE.read_text(encoding="utf-8")
MARKER = 'V120_Q6_DEEP_OLLAMA = "v0.12-q6-deep-ollama-v1"'

if MARKER in text:
    print("Q6 deep Ollama route already applied")
    raise SystemExit(0)

required = [
    'V120_DUAL_BRAIN_ROUTER = "v0.12-tri-brain-v4"',
    'V120_DEEP_MODEL = "vex-qwen35-a3b-text:latest"',
    "def _v120_deep_health(",
    "def _v120_deep_chat(",
]
for item in required:
    if item not in text:
        raise SystemExit(f"required tri-brain marker missing: {item}")

anchor = "\n\n_BROWSER_CONTROL_LOCK = threading.Lock()"
if anchor not in text:
    raise SystemExit("Bridge helper anchor missing")

layer = r'''

# ---------------------------------------------------------------------------
# v0.12 Q6 deep cognition backend
#
# The HP's best local Q6 model fits RAM and generates at useful speed once
# resident, but a cold HDD load is too slow for the ordinary smart tier.
# Keep 4B fast + Q4 9B smart unchanged. Explicit deep requests use the Q6
# model through Ollama with a longer cold-start timeout and a long keep-alive.
# ---------------------------------------------------------------------------
V120_Q6_DEEP_OLLAMA = "v0.12-q6-deep-ollama-v1"


def _v120_deep_health(timeout: float = 0.8) -> bool:
    # Deep availability is the local Ollama model inventory, not a permanently
    # resident 11535 llama-server. This avoids reserving ~7-8 GiB all day.
    try:
        return _v120_model_available(V120_DEEP_MODEL)
    except Exception:
        return False


def _v120_deep_chat(history: list[dict], message: str, context: dict | None = None) -> tuple[str, str] | None:
    if not _v120_model_available(V120_DEEP_MODEL):
        return None
    try:
        import requests
        session = requests.Session()
        session.trust_env = False
        response = session.post(
            f"{OLLAMA_BASE}/api/chat",
            json={
                "model": V120_DEEP_MODEL,
                "messages": _v120_context_messages(history, message, context, "ultra-deep"),
                "stream": False,
                "think": False,
                "keep_alive": "30m",
                "options": {
                    "temperature": 0.52,
                    "top_p": 0.88,
                    "num_ctx": 2048,
                    "num_predict": 160,
                    "repeat_penalty": 1.05,
                },
            },
            timeout=600,
        )
        response.raise_for_status()
        payload = response.json()
        raw = str(((payload.get("message") or {}).get("content")) or "")
        reply = _strip_reasoning_markup(raw)
        return (reply[:12000], V120_DEEP_MODEL) if reply else None
    except Exception as exc:
        print(f"[cognition] Q6 deep model failed, falling back: {exc}", flush=True)
        return None
'''

text = text.replace(anchor, layer + anchor, 1)

compile(text, str(BRIDGE), "exec")
for item in [
    MARKER,
    'keep_alive": "30m"',
    "timeout=600",
    'V120_DEEP_MODEL = "vex-qwen35-a3b-text:latest"',
    'V120_MID_MODEL = "vex-qwen35-9b:latest"',
]:
    if item not in text:
        raise SystemExit(f"Q6 deep verifier missing: {item}")

BRIDGE.write_text(text, encoding="utf-8")
print("Applied Q6 deep Ollama backend; 4B fast and Q4 smart unchanged")
