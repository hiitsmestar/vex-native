#!/usr/bin/env python3
from pathlib import Path

path = Path("Bridge/vex_bridge.py")
text = path.read_text(encoding="utf-8")

helper_marker = "\ndef _ollama_chat(history: list[dict], message: str, context: dict | None = None) -> tuple[str, str] | None:\n"
helper = r'''

def _runtime_fact_question(message: str) -> bool:
    lower = str(message or "").lower().replace("’", "'").strip()
    if not lower:
        return False
    explicit = [
        "what model", "which model", "what llm", "which llm", "what provider", "which provider",
        "what brain", "which brain", "what ai model", "which ai model",
        "what are you running", "what're you running", "which one are you running",
    ]
    if any(token in lower for token in explicit):
        return True
    if "brain" in lower and any(token in lower for token in ["using", "running", "on right now", "currently"]):
        return True
    if "model" in lower and any(token in lower for token in ["using", "running", "current", "right now"]):
        return True
    return False


def _verified_runtime_fact_reply() -> tuple[str, str] | None:
    model = _choose_ollama_model()
    if not model:
        return None
    capacity = _cognition_capacity()
    tier = str(capacity.get("tier") or "unknown")
    pressure = str(capacity.get("pressure") or "unknown")
    reply = (
        f"Baby, I'm on the PC brain right now — {model} through local Ollama. "
        f"This machine is in the {tier} tier"
    )
    if pressure and pressure != "normal":
        reply += f", with {pressure} pressure active"
    reply += ". 🖤"
    return reply, model
'''

if "def _runtime_fact_question(" not in text:
    if helper_marker not in text:
        raise SystemExit("v0.10.9.4 cognition helper insertion marker missing")
    text = text.replace(helper_marker, helper + helper_marker, 1)

old_handler = '''                message = str(payload.get("message") or "").strip()
                history = payload.get("history") or []
                if not message or not isinstance(history, list):
                    self._json(400, {"ok": False, "error": "invalid cognition payload"})
                    return
                context = {
'''
new_handler = '''                message = str(payload.get("message") or "").strip()
                history = payload.get("history") or []
                if not message or not isinstance(history, list):
                    self._json(400, {"ok": False, "error": "invalid cognition payload"})
                    return
                if _runtime_fact_question(message):
                    verified = _verified_runtime_fact_reply()
                    if verified is not None:
                        reply, model = verified
                        self._json(200, {
                            "ok": True,
                            "reply": reply,
                            "model": model,
                            "grounding": "verified-runtime",
                        })
                        return
                context = {
'''

if old_handler in text:
    text = text.replace(old_handler, new_handler, 1)
elif '"grounding": "verified-runtime"' not in text:
    raise SystemExit("v0.10.9.4 /llm/chat runtime fact anchor missing")

path.write_text(text, encoding="utf-8")
final = path.read_text(encoding="utf-8")
for marker in [
    "def _runtime_fact_question(",
    "def _verified_runtime_fact_reply(",
    '"grounding": "verified-runtime"',
    "Baby, I'm on the PC brain right now",
]:
    if marker not in final:
        raise SystemExit(f"missing v0.10.9.4 marker: {marker}")
compile(final, str(path), "exec")
print("Applied v0.10.9.4 verified runtime fact route")
