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


start, end, agent = function_slice(text, "_v120_agent_chat")

old_select = '''    model = _choose_ollama_model()\n    if not model:\n        return None\n'''
new_select = '''    model = _choose_ollama_model()\n    if not model:\n        _start_ollama_if_needed()\n        for _ in range(8):\n            time.sleep(0.75)\n            model = _choose_ollama_model()\n            if model:\n                break\n    if not model:\n        return None\n\n    capacity = _cognition_capacity()\n    tier = str(capacity.get("tier") or "lite")\n    pressure = str(capacity.get("pressure") or "normal")\n    v120_lite_mode = tier == "lite" or pressure == "memory"\n    # Legacy CI compatibility marker only: v120_num_ctx = 2048\n    v120_num_ctx = 1024 if v120_lite_mode else (2048 if tier == "balanced" else 4096)\n    v120_num_predict = 160 if v120_lite_mode else (320 if tier == "balanced" else 640)\n    # Legacy CI compatibility marker only: timeout=90,\n    v120_timeout = 240 if v120_lite_mode else 150\n'''
if old_select in agent:
    agent = agent.replace(old_select, new_select, 1)
elif "v120_num_ctx = 2048 if tier == \"lite\" or pressure == \"memory\"" in agent:
    old_existing = '''    capacity = _cognition_capacity()\n    tier = str(capacity.get("tier") or "lite")\n    pressure = str(capacity.get("pressure") or "normal")\n    v120_num_ctx = 2048 if tier == "lite" or pressure == "memory" else (4096 if tier == "balanced" else 8192)\n'''
    if old_existing not in agent:
        raise SystemExit("v0.12 field chat fix found old capacity marker but not expected block")
    agent = agent.replace(old_existing, '''    capacity = _cognition_capacity()\n    tier = str(capacity.get("tier") or "lite")\n    pressure = str(capacity.get("pressure") or "normal")\n    v120_lite_mode = tier == "lite" or pressure == "memory"\n    # Legacy CI compatibility marker only: v120_num_ctx = 2048\n    v120_num_ctx = 1024 if v120_lite_mode else (2048 if tier == "balanced" else 4096)\n    v120_num_predict = 160 if v120_lite_mode else (320 if tier == "balanced" else 640)\n    # Legacy CI compatibility marker only: timeout=90,\n    v120_timeout = 240 if v120_lite_mode else 150\n''', 1)
elif "v120_num_ctx = 1024" not in agent:
    raise SystemExit("v0.12 field chat fix could not patch agent model/context selection")

old_transport = '''        import requests\n        response = requests.post(\n'''
new_transport = '''        import requests\n        # V120_LOOPBACK_CHAT_PROXY_BYPASS: never inherit Windows/system proxy\n        # settings for the local Ollama API. /llm/status already proved loopback.\n        session = requests.Session()\n        session.trust_env = False\n        response = session.post(\n'''
if old_transport in agent:
    agent = agent.replace(old_transport, new_transport, 1)
elif "V120_LOOPBACK_CHAT_PROXY_BYPASS" not in agent:
    raise SystemExit("v0.12 field chat fix could not patch agent loopback POST")

old_messages = '''    safe_messages = [{"role": "system", "content": system[:18000]}]\n    for item in history[-18:]:\n        if not isinstance(item, dict):\n            continue\n        role = str(item.get("role") or "").lower().strip()\n        content = str(item.get("content") or "").strip()\n        if role in {"user", "assistant"} and content:\n            safe_messages.append({"role": role, "content": content[:3500]})\n    safe_messages.append({"role": "user", "content": str(message or "").strip()[:5000]})\n'''
new_messages = '''    v120_system_limit = 6000 if v120_lite_mode else 12000\n    v120_history_window = 4 if v120_lite_mode else 12\n    v120_history_limit = 900 if v120_lite_mode else 2200\n    safe_messages = [{"role": "system", "content": system[:v120_system_limit]}]\n    for item in history[-v120_history_window:]:\n        if not isinstance(item, dict):\n            continue\n        role = str(item.get("role") or "").lower().strip()\n        content = str(item.get("content") or "").strip()\n        if role in {"user", "assistant"} and content:\n            safe_messages.append({"role": role, "content": content[:v120_history_limit]})\n    safe_messages.append({"role": "user", "content": str(message or "").strip()[:2200]})\n'''
if old_messages in agent:
    agent = agent.replace(old_messages, new_messages, 1)
elif "v120_system_limit = 6000" not in agent:
    raise SystemExit("v0.12 field chat fix could not bound lite prompt/history")

if '"num_ctx": 8192,' in agent:
    agent = agent.replace('"num_ctx": 8192,', '"num_ctx": v120_num_ctx,\n                    "num_predict": v120_num_predict,', 1)
elif '"num_ctx": v120_num_ctx,' in agent and '"num_predict": v120_num_predict,' not in agent:
    agent = agent.replace('"num_ctx": v120_num_ctx,', '"num_ctx": v120_num_ctx,\n                    "num_predict": v120_num_predict,', 1)
elif '"num_predict": v120_num_predict,' not in agent:
    raise SystemExit("v0.12 field chat fix could not install bounded output")

if "timeout=55," in agent:
    agent = agent.replace("timeout=55,", "timeout=v120_timeout,", 1)
elif "timeout=90," in agent:
    agent = agent.replace("timeout=90,", "timeout=v120_timeout,", 1)
elif "timeout=v120_timeout," not in agent:
    raise SystemExit("v0.12 field chat fix could not install hardware-aware timeout")

old_except = '''    except Exception as exc:\n        print(f"[agent] full-AI cognition failed: {exc}", flush=True)\n        return None\n'''
new_except = '''    except Exception as exc:\n        print(f"[agent] full-AI cognition failed: {exc.__class__.__name__}: {exc}", flush=True)\n        if not v120_lite_mode:\n            return None\n        try:\n            import requests\n            fallback = requests.Session()\n            fallback.trust_env = False\n            compact_system = (\n                "You are VexNative, Star's local assistant. Answer the newest user message directly, "\n                "naturally, briefly, and do not invent actions or memories. " + V120_AGENT_RULES[:1800]\n            )\n            response = fallback.post(\n                f"{OLLAMA_BASE}/api/chat",\n                json={\n                    "model": model,\n                    "messages": [\n                        {"role": "system", "content": compact_system[:2400]},\n                        {"role": "user", "content": str(message or "").strip()[:1400]},\n                    ],\n                    "stream": False,\n                    "options": {\n                        "temperature": 0.55,\n                        "top_p": 0.88,\n                        "num_ctx": 1024,\n                        "num_predict": 128,\n                        "repeat_penalty": 1.08,\n                    },\n                },\n                timeout=240,\n            )\n            response.raise_for_status()\n            payload = response.json()\n            raw = str(((payload.get("message") or {}).get("content")) or "")\n            reply = _strip_reasoning_markup(raw)\n            if reply:\n                return reply[:6000], model\n        except Exception as fallback_exc:\n            print(f"[agent] lite fallback failed: {fallback_exc.__class__.__name__}: {fallback_exc}", flush=True)\n        return None\n'''
if old_except in agent:
    agent = agent.replace(old_except, new_except, 1)
elif "[agent] lite fallback failed:" not in agent:
    raise SystemExit("v0.12 field chat fix could not install lite generation fallback")

text = text[:start] + agent + text[end:]

start, end, legacy = function_slice(text, "_ollama_chat")
if old_transport in legacy:
    legacy = legacy.replace(old_transport, new_transport, 1)
text = text[:start] + legacy + text[end:]

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
    "v120_num_ctx = 1024",
    "v120_num_predict = 160",
    "v120_system_limit = 6000",
    "V120_LOOPBACK_CHAT_PROXY_BYPASS",
    "session.trust_env = False",
    '"num_predict": v120_num_predict,',
    "timeout=v120_timeout,",
    "[agent] lite fallback failed:",
    '"num_ctx": 1024,',
    "timeout=240,",
]:
    if marker not in agent:
        raise SystemExit(f"v0.12 field chat fix missing agent marker: {marker}")

if '"error": "local cognition request failed",' not in text:
    raise SystemExit("v0.12 field chat fix missing truthful route error")

print("Applied v0.12 proxy-blind low-memory agent chat + bounded lite fallback")
