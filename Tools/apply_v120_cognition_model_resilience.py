#!/usr/bin/env python3
from __future__ import annotations

import runpy
from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
text = BRIDGE.read_text(encoding="utf-8")

# The cumulative source-generating harness can invoke this patch while the Bridge
# is still at the .79/.80 intermediate stage. Promote through the complete v0.12
# conversation entry first so the broad/compound recall owner survives, then harden
# model discovery. The conversation entry is idempotent and safe to encounter again
# later in the inherited patch list.
if (
    '"agent_runtime_bundle": "0.12.0"' not in text
    or 'def _v120_agent_owns_turn(message: str) -> bool:' not in text
):
    runpy.run_path("Tools/apply_v120_conversation_route_entry.py", run_name="__main__")
    text = BRIDGE.read_text(encoding="utf-8")

for marker in [
    '"agent_runtime_bundle": "0.12.0"',
    'def _v120_agent_owns_turn(message: str) -> bool:',
    'if _personal_memory_fact_question(message) and not _v120_agent_owns_turn(message):',
    'if _runtime_fact_question(message) and not _v120_agent_owns_turn(message):',
]:
    if marker not in text:
        raise SystemExit(f"v0.12 cognition resilience missing conversation prerequisite: {marker}")

start = text.find("def _ollama_models() -> list[str]:\n")
end = text.find("\n\ndef _choose_ollama_model()", start)
if start < 0 or end < 0:
    raise SystemExit("v0.12 cognition resilience could not find Ollama model discovery")

replacement = r'''_OLLAMA_MODEL_CACHE: list[str] = []
_OLLAMA_MODEL_CACHE_AT = 0.0
_OLLAMA_MODEL_CACHE_TTL_SECONDS = 120.0


def _ollama_models() -> list[str]:
    global _OLLAMA_MODEL_CACHE, _OLLAMA_MODEL_CACHE_AT
    import requests

    def remember(models: list[str]) -> list[str]:
        global _OLLAMA_MODEL_CACHE, _OLLAMA_MODEL_CACHE_AT
        if models:
            _OLLAMA_MODEL_CACHE = list(dict.fromkeys(models))
            _OLLAMA_MODEL_CACHE_AT = time.time()
        return models

    def fetch() -> list[str]:
        try:
            response = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=2.0)
            if response.status_code >= 400:
                return []
            payload = response.json()
            result: list[str] = []
            for item in payload.get("models") or []:
                name = str(item.get("name") or item.get("model") or "").strip()
                if name:
                    result.append(name)
            return result
        except Exception:
            return []

    models = fetch()
    if models:
        return remember(models)

    # A short /api/tags hiccup must not make an otherwise healthy PC advertise
    # "no local cognition model" to the phone. Try bounded service recovery first.
    _start_ollama_if_needed()
    for _ in range(8):
        time.sleep(0.75)
        models = fetch()
        if models:
            return remember(models)

    # If discovery alone is momentarily flaky, keep using a model that this same
    # Bridge verified very recently. The chat POST remains the final health check,
    # so a genuinely dead Ollama service still fails honestly instead of fabricating.
    if _OLLAMA_MODEL_CACHE and (time.time() - _OLLAMA_MODEL_CACHE_AT) <= _OLLAMA_MODEL_CACHE_TTL_SECONDS:
        return list(_OLLAMA_MODEL_CACHE)
    return []
'''
text = text[:start] + replacement + text[end:]

old_select = '''    model = _choose_ollama_model()\n    if not model:\n        return None\n'''
new_select = '''    model = _choose_ollama_model()\n    if not model:\n        # One bounded second-chance selection avoids turning a transient Ollama\n        # discovery race into a false "no local cognition model" response.\n        _start_ollama_if_needed()\n        for _ in range(3):\n            time.sleep(0.5)\n            model = _choose_ollama_model()\n            if model:\n                break\n    if not model:\n        return None\n'''
if old_select in text:
    text = text.replace(old_select, new_select, 1)
elif "One bounded second-chance selection" not in text:
    raise SystemExit("v0.12 cognition resilience could not find v120 model-selection anchor")

BRIDGE.write_text(text, encoding="utf-8")
compile(text, str(BRIDGE), "exec")

checks = [
    "_OLLAMA_MODEL_CACHE_TTL_SECONDS = 120.0",
    "return list(_OLLAMA_MODEL_CACHE)",
    "for _ in range(3):",
    "One bounded second-chance selection",
    '"agent_runtime_bundle": "0.12.0"',
    'def _v120_agent_owns_turn(message: str) -> bool:',
]
for marker in checks:
    if marker not in text:
        raise SystemExit(f"v0.12 cognition resilience missing marker: {marker}")

print("Applied v0.12 conversation-preserving Ollama discovery resilience + bounded model retry")
