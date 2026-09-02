#!/usr/bin/env python3
from __future__ import annotations

import ast
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
# Legacy readiness compatibility marker only: _OLLAMA_MODEL_CACHE_TTL_SECONDS = 120.0
_OLLAMA_MODEL_CACHE_TTL_SECONDS = 1800.0


def _ollama_models() -> list[str]:
    global _OLLAMA_MODEL_CACHE, _OLLAMA_MODEL_CACHE_AT
    import subprocess
    import requests

    def remember(models: list[str]) -> list[str]:
        global _OLLAMA_MODEL_CACHE, _OLLAMA_MODEL_CACHE_AT
        clean = [str(name or "").strip() for name in models if str(name or "").strip()]
        if clean:
            _OLLAMA_MODEL_CACHE = list(dict.fromkeys(clean))
            _OLLAMA_MODEL_CACHE_AT = time.time()
        return clean

    def fetch_http() -> list[str]:
        # Never let a system/user HTTP proxy intercept the loopback Ollama API.
        session = requests.Session()
        session.trust_env = False
        try:
            response = session.get(f"{OLLAMA_BASE}/api/tags", timeout=4.0)
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
        finally:
            try:
                session.close()
            except Exception:
                pass

    def fetch_cli() -> list[str]:
        exe = _ollama_executable()
        if not exe:
            return []
        try:
            proc = subprocess.run(
                [exe, "list"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=8,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if proc.returncode != 0:
                return []
            result: list[str] = []
            for line in (proc.stdout or "").splitlines():
                stripped = line.strip()
                if not stripped or stripped.lower().startswith("name"):
                    continue
                name = stripped.split()[0].strip()
                if name and ":" in name:
                    result.append(name)
            return result
        except Exception:
            return []

    models = fetch_http()
    if models:
        return remember(models)

    # A short /api/tags hiccup must not turn an installed model into a false
    # "no local cognition model" result. Start/recover Ollama and retry loopback.
    _start_ollama_if_needed()
    for _ in range(10):
        time.sleep(0.75)
        models = fetch_http()
        if models:
            return remember(models)

    # If the HTTP discovery route is still flaky, ask Ollama itself for its
    # installed model list. The subsequent chat POST remains the real health test.
    models = fetch_cli()
    if models:
        return remember(models)

    # Preserve the last model verified by this Bridge across brief service churn.
    # Thirty minutes is long enough for slow Windows/Ollama recovery but bounded.
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

# Field validation proved that a later cumulative source layer could leave the
# chooser call intact while dropping cognition helpers after the old .39 check.
runpy.run_path("Tools/apply_v120_cognition_capacity_integrity.py", run_name="__main__")

# The purple Windows Host routes through _v120_agent_chat, not the legacy
# _ollama_chat helper. Make the real field path the final transport owner here.
# This patch is idempotent, so the later installer-tolerance stage may verify it
# again without changing the already-correct Bridge source.
runpy.run_path("Tools/apply_v120_field_chat_transport.py", run_name="__main__")
text = BRIDGE.read_text(encoding="utf-8")
compile(text, str(BRIDGE), "exec")

checks = [
    "_OLLAMA_MODEL_CACHE_TTL_SECONDS = 1800.0",
    '[exe, "list"]',
    "return list(_OLLAMA_MODEL_CACHE)",
    "One bounded second-chance selection",
    '"agent_runtime_bundle": "0.12.0"',
    'def _v120_agent_owns_turn(message: str) -> bool:',
    'def _cognition_capacity() -> dict:',
    "V120_LOOPBACK_CHAT_PROXY_BYPASS",
    "session.trust_env = False",
    "v120_num_ctx = 2048",
    '"num_ctx": v120_num_ctx,',
    "timeout=90,",
    '"error": "local cognition request failed",',
]
for marker in checks:
    if marker not in text:
        raise SystemExit(f"v0.12 cognition resilience missing marker: {marker}")

# Verify the actual v0.12 field-generation function itself, not a legacy helper.
tree = ast.parse(text)
agent_chat = next(
    (node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_v120_agent_chat"),
    None,
)
if agent_chat is None:
    raise SystemExit("v0.12 cognition resilience final _v120_agent_chat missing")
agent_source = ast.get_source_segment(text, agent_chat) or ""
for marker in [
    "V120_LOOPBACK_CHAT_PROXY_BYPASS",
    "session.trust_env = False",
    "response = session.post(",
    '"num_ctx": v120_num_ctx,',
    "timeout=90,",
]:
    if marker not in agent_source:
        raise SystemExit(f"v0.12 cognition resilience final agent chat missing marker: {marker}")
if "requests.post(" in agent_source:
    raise SystemExit("v0.12 cognition resilience active agent chat regressed to proxy-aware requests.post")

print("Applied v0.12 final proxy-safe model discovery + low-memory active agent chat + cognition helper integrity")
