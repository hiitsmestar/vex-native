#!/usr/bin/env python3
from __future__ import annotations

import runpy
from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
text = BRIDGE.read_text(encoding="utf-8")

# The field failure occurs in the v0.12 agent wrapper, not the older raw Ollama
# helper. Make sure the full agent layer exists before editing its live chat path.
if "def _v120_agent_chat(" not in text:
    runpy.run_path("Tools/apply_v120_conversation_route_entry.py", run_name="__main__")
    text = BRIDGE.read_text(encoding="utf-8")


def function_slice(source: str, name: str) -> tuple[int, int, str]:
    start = source.find(f"def {name}(")
    if start < 0:
        raise SystemExit(f"v0.12 field chat fix missing function: {name}")
    end = source.find("\n\ndef ", start + 10)
    if end < 0:
        end = len(source)
    return start, end, source[start:end]


# Patch the *actual* v0.12 agent function. Earlier resilience used a generic
# first-match replacement and could harden the legacy _ollama_chat while leaving
# this wrapper unchanged.
start, end, agent = function_slice(text, "_v120_agent_chat")

old_select = '''    model = _choose_ollama_model()\n    if not model:\n        return None\n'''
new_select = '''    model = _choose_ollama_model()\n    if not model:\n        _start_ollama_if_needed()\n        for _ in range(8):\n            time.sleep(0.75)\n            model = _choose_ollama_model()\n            if model:\n                break\n    if not model:\n        return None\n\n    # The upstairs 8 GB field node can report the model as installed/ready while\n    # an 8192-token KV cache still pushes the first generation over memory limits.\n    # Scale context to the same hardware pressure signal used by model selection.\n    capacity = _cognition_capacity()\n    tier = str(capacity.get("tier") or "lite")\n    pressure = str(capacity.get("pressure") or "normal")\n    v120_num_ctx = 2048 if tier == "lite" or pressure == "memory" else (4096 if tier == "balanced" else 8192)\n'''
if old_select in agent:
    agent = agent.replace(old_select, new_select, 1)
elif "v120_num_ctx = 2048" not in agent:
    raise SystemExit("v0.12 field chat fix could not patch agent model/context selection")

old_transport = '''        import requests\n        response = requests.post(\n'''
new_transport = '''        import requests\n        # V120_LOOPBACK_CHAT_PROXY_BYPASS: never inherit Windows/system proxy\n        # settings for the local Ollama API. /llm/status already proved loopback.\n        session = requests.Session()\n        session.trust_env = False\n        response = session.post(\n'''
if old_transport in agent:
    agent = agent.replace(old_transport, new_transport, 1)
elif "V120_LOOPBACK_CHAT_PROXY_BYPASS" not in agent:
    raise SystemExit("v0.12 field chat fix could not patch agent loopback POST")

if '"num_ctx": 8192,' in agent:
    agent = agent.replace('"num_ctx": 8192,', '"num_ctx": v120_num_ctx,', 1)
elif '"num_ctx": v120_num_ctx,' not in agent:
    raise SystemExit("v0.12 field chat fix could not make context hardware-aware")

if "timeout=55," in agent:
    agent = agent.replace("timeout=55,", "timeout=90,", 1)
elif "timeout=90," not in agent:
    raise SystemExit("v0.12 field chat fix could not extend first-generation timeout")

text = text[:start] + agent + text[end:]

# Harden the legacy cognition helper too because Remote Support/older callers can
# still reach it independently of the v0.12 agent wrapper.
start, end, legacy = function_slice(text, "_ollama_chat")
if old_transport in legacy:
    legacy = legacy.replace(old_transport, new_transport, 1)
text = text[:start] + legacy + text[end:]

# The old route used one generic message for every None return (model lookup,
# Ollama load failure, timeout, proxy failure). Stop falsely claiming the model is
# absent when the status endpoint has already verified one.
text = text.replace(
    '"error": "no local cognition model available",',
    '"error": "local cognition request failed",',
    1,
)

BRIDGE.write_text(text, encoding="utf-8")
compile(text, str(BRIDGE), "exec")

_, _, agent = function_slice(text, "_v120_agent_chat")
for marker in [
    "for _ in range(8):",
    "v120_num_ctx = 2048",
    "V120_LOOPBACK_CHAT_PROXY_BYPASS",
    "session.trust_env = False",
    '"num_ctx": v120_num_ctx,',
    "timeout=90,",
]:
    if marker not in agent:
        raise SystemExit(f"v0.12 field chat fix missing agent marker: {marker}")

if '"error": "local cognition request failed",' not in text:
    raise SystemExit("v0.12 field chat fix missing truthful route error")

print("Applied v0.12 proxy-blind + low-memory field chat transport fix")
