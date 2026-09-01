#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
INSTALLER = Path("Tools/VexAgentRuntimeInstall.py")
bridge = BRIDGE.read_text(encoding="utf-8")
installer = INSTALLER.read_text(encoding="utf-8")

required_base = [
    '"agent_runtime_bundle": "0.11.7.80"',
    'def _ollama_chat(',
    'def _memory_post(',
    'def _v11776_launch_app(',
    'def _v11777_window_action(',
    'def _autonomy_probe_capability(',
    'parsed.path == "/llm/chat"',
]
for marker in required_base:
    if marker not in bridge:
        raise SystemExit(f"v0.12.0 expected cumulative .80 marker missing: {marker}")
if 'BUNDLE_VERSION = "0.11.7.80"' not in installer:
    raise SystemExit("v0.12.0 expected installer .80")

insert_anchor = "def _vex_background_services() -> None:\n"
if insert_anchor not in bridge:
    raise SystemExit("v0.12.0 orchestration insertion anchor missing")

layer = r'''
# ---------------------------------------------------------------------------
# Vex Agent Runtime v0.12.0 — Full AI Foundation
# One bounded agent loop around the proven cognition, memory, research, file,
# Windows-control, adaptive-learning and self-repair capabilities.  The agent
# can reason with capability context and execute only registered/audited tools.
# ---------------------------------------------------------------------------
V120_AGENT_VERSION = "0.12.0"


def _v120_capability_registry() -> list[dict]:
    probes = {
        "conversation": (bool(_choose_ollama_model()), "local cognition"),
        "memory": _autonomy_probe_capability("personal_memory"),
        "web_research": _autonomy_probe_capability("web_research"),
        "file_search": _autonomy_probe_capability("file_index"),
        "learned_skills": _autonomy_probe_capability("learned_skills"),
        "self_repair": _autonomy_probe_capability("self_repair"),
        "art": _autonomy_probe_capability("art_worker"),
    }
    catalog = []
    definitions = [
        ("conversation", "reason", False, False),
        ("memory", "remember", False, False),
        ("web_research", "research public web", False, False),
        ("file_search", "search approved PC files", False, False),
        ("windows_apps", "list and launch installed apps", True, False),
        ("window_control", "focus/minimize/maximize/restore windows; close needs confirmation", True, True),
        ("learned_skills", "reuse compiled local skills", False, False),
        ("self_repair", "bounded health repair", True, False),
        ("art", "local image worker when installed", True, False),
        ("adaptive_learning", "gap detection and staged improvements", True, False),
        ("node_routing", "health-aware multi-PC routing", False, False),
    ]
    for name, description, auditable, confirmation in definitions:
        if name in probes:
            raw = probes[name]
            if isinstance(raw, tuple):
                available, detail = bool(raw[0]), str(raw[1])
            else:
                available, detail = bool(raw), ""
        elif name == "windows_apps":
            available, detail = callable(globals().get("_v11776_launch_app")), "safe app catalog"
        elif name == "window_control":
            available, detail = callable(globals().get("_v11777_window_action")), "Win32 broker"
        elif name == "adaptive_learning":
            available, detail = callable(globals().get("_adaptive_status")) or callable(globals().get("_autonomy_status")), "local adaptive state"
        elif name == "node_routing":
            available, detail = True, "Bridge/iPhone resource director"
        else:
            available, detail = False, "unavailable"
        catalog.append({
            "name": name,
            "description": description,
            "available": bool(available),
            "detail": str(detail)[:220],
            "auditable": bool(auditable),
            "confirmation_required_for_destructive": bool(confirmation),
        })
    return catalog


def _v120_fact_rows(query: str, limit: int = 6) -> list[dict]:
    data = _memory_post("/facts", {"query": str(query or "")[:5000], "limit": max(1, min(int(limit), 12))}, timeout=1.8)
    if not isinstance(data, dict):
        return []
    facts = data.get("facts")
    return facts if isinstance(facts, list) else []


def _v120_context(message: str) -> dict:
    text = str(message or "").strip()
    lower = " " + text.lower() + " "
    context: dict = {"memory": [], "files": [], "web": []}

    # Give ordinary conversation a small trusted-memory grounding window so the
    # model can *reason with* continuity instead of only answering explicit recall.
    facts = _v120_fact_rows(text, 5)
    if not facts:
        facts = _v120_fact_rows("", 4)
    for item in facts[:5]:
        if not isinstance(item, dict):
            continue
        fact = re.sub(r"\s+", " ", str(item.get("text") or "")).strip()
        if fact:
            context["memory"].append(fact[:1200])

    file_cues = (" file ", " document ", " folder ", " on the pc ", " on my pc ", " find my ", " search my ")
    if any(cue in lower for cue in file_cues):
        try:
            index = getattr(STATE, "index", None) if STATE is not None else None
            if index is not None:
                context["files"] = index.search(text, limit=4)
        except Exception:
            pass

    web_cues = (" search the web ", " search online ", " research ", " current ", " latest ", " news ", " look up ")
    if any(cue in lower for cue in web_cues):
        try:
            context["web"] = web_search(text, limit=5)
        except Exception:
            pass
    return context


def _v120_plan(message: str) -> dict:
    text = re.sub(r"\s+", " ", str(message or "")).strip()
    lower = text.lower()
    plan = {"version": V120_AGENT_VERSION, "goal": text[:1000], "steps": [], "automatic": True}

    if re.search(r"\b(open|launch|start)\s+(?:the\s+)?[a-z0-9][a-z0-9 ._+-]{1,80}$", lower):
        match = re.search(r"\b(?:open|launch|start)\s+(?:the\s+)?(.+)$", text, flags=re.I)
        name = (match.group(1) if match else "").strip(" .!?")[:120]
        if name:
            plan["steps"].append({"tool": "windows.launch", "args": {"name": name}, "risk": "normal"})
            return plan

    if any(x in lower for x in ("search the web", "search online", "look up", "research", "latest", "current news")):
        plan["steps"].append({"tool": "web.search", "args": {"query": text}, "risk": "read"})
    if any(x in lower for x in ("find my file", "search my files", "find the document", "on my pc", "on the pc")):
        plan["steps"].append({"tool": "files.search", "args": {"query": text}, "risk": "read"})
    if _personal_memory_fact_question(text):
        plan["steps"].append({"tool": "memory.facts", "args": {"query": text}, "risk": "read"})
    if any(x in lower for x in ("repair yourself", "self repair", "fix your runtime", "diagnose yourself")):
        plan["steps"].append({"tool": "self.repair", "args": {}, "risk": "audited"})
    if not plan["steps"]:
        plan["steps"].append({"tool": "conversation.reason", "args": {}, "risk": "read"})
    return plan


def _v120_execute_tool(tool: str, args: dict | None = None, confirm: bool = False) -> dict:
    tool = str(tool or "").strip().lower()
    args = args if isinstance(args, dict) else {}
    if tool == "memory.facts":
        return {"ok": True, "tool": tool, "facts": _v120_fact_rows(str(args.get("query") or ""), int(args.get("limit") or 6))}
    if tool == "files.search":
        try:
            index = getattr(STATE, "index", None) if STATE is not None else None
            if index is None:
                return {"ok": False, "tool": tool, "error": "file index unavailable"}
            return {"ok": True, "tool": tool, "results": index.search(str(args.get("query") or ""), limit=max(1, min(int(args.get("limit") or 5), 10)))}
        except Exception as exc:
            return {"ok": False, "tool": tool, "error": exc.__class__.__name__}
    if tool == "web.search":
        return {"ok": True, "tool": tool, "results": web_search(str(args.get("query") or ""), limit=max(1, min(int(args.get("limit") or 6), 10)))}
    if tool == "windows.launch":
        name = str(args.get("name") or "").strip()
        return {"tool": tool, **_v11776_launch_app(name, dry_run=bool(args.get("dry_run")))}
    if tool == "window.action":
        action = str(args.get("action") or "").strip().lower()
        if action == "close" and not confirm:
            return {"ok": False, "tool": tool, "error": "close requires explicit confirmation"}
        try:
            hwnd = int(args.get("hwnd") or 0)
        except Exception:
            hwnd = 0
        return {"tool": tool, **_v11777_window_action(hwnd, action, confirm=confirm, dry_run=bool(args.get("dry_run")))}
    if tool == "self.repair":
        fn = globals().get("_sr_run_once")
        if not callable(fn):
            return {"ok": False, "tool": tool, "error": "self-repair supervisor unavailable"}
        try:
            fn(force=False, include_art=False)
            status_fn = globals().get("_sr_status")
            status = status_fn() if callable(status_fn) else {"ok": True}
            return {"ok": bool(status.get("ok", True)), "tool": tool, "status": status}
        except Exception as exc:
            return {"ok": False, "tool": tool, "error": exc.__class__.__name__}
    if tool == "conversation.reason":
        return {"ok": True, "tool": tool, "deferred_to_cognition": True}
    return {"ok": False, "tool": tool, "error": "tool is not in the v0.12.0 capability registry"}


def _v120_context_text(context: dict) -> str:
    chunks = []
    memories = context.get("memory") if isinstance(context, dict) else []
    if memories:
        chunks.append("TRUSTED MEMORY:\n" + "\n".join(f"- {x}" for x in memories[:5]))
    files = context.get("files") if isinstance(context, dict) else []
    if files:
        chunks.append("APPROVED LOCAL FILE SEARCH RESULTS:\n" + "\n".join(
            f"- {str(x.get('title') or '')}: {str(x.get('content') or '')[:650]}" for x in files[:4] if isinstance(x, dict)
        ))
    web = context.get("web") if isinstance(context, dict) else []
    if web:
        chunks.append("PUBLIC WEB SEARCH RESULTS:\n" + "\n".join(
            f"- {str(x.get('title') or '')}: {str(x.get('content') or '')[:650]}" for x in web[:5] if isinstance(x, dict)
        ))
    return "\n\n".join(chunks)[:9000]


V120_AGENT_RULES = """
You are the reasoning/orchestration layer of VexNative Full AI Runtime v0.12.0.
Use supplied trusted memory as continuity context, not as text to dump mechanically. Distinguish Star facts from instructions/persona metadata. Answer naturally in Vex's established voice while keeping factual claims grounded.
You have registered tools for persistent memory, approved local-file search, public-web research, safe Windows app launching/window control, adaptive learning, and bounded self-repair. Never claim a tool action happened unless a confirmed tool result says it did. Destructive actions require confirmation. Do not invent memories, sources, files, device state, or completed actions.
When evidence is missing, say what is missing instead of filling the gap. Prefer solving the user's actual goal over narrating architecture.
"""


def _v120_agent_chat(history: list[dict], message: str) -> tuple[str, str] | None:
    plan = _v120_plan(message)
    steps = plan.get("steps") if isinstance(plan, dict) else []

    # Execute only simple, explicitly requested registered actions automatically.
    if isinstance(steps, list) and len(steps) == 1 and isinstance(steps[0], dict) and steps[0].get("tool") == "windows.launch":
        result = _v120_execute_tool("windows.launch", steps[0].get("args") or {}, confirm=False)
        if result.get("ok"):
            label = str(result.get("name") or result.get("matched_name") or (steps[0].get("args") or {}).get("name") or "that app")
            return f"Done, babe — I opened {label}. 🖤", "vex-agent-tool"
        # Failed action falls through to cognition with the real result attached.
        tool_note = json.dumps(result, ensure_ascii=False)[:1200]
    else:
        tool_note = ""

    model = _choose_ollama_model()
    if not model:
        return None
    context = _v120_context(message)
    grounding = _v120_context_text(context)
    capabilities = [item["name"] for item in _v120_capability_registry() if item.get("available")]
    system = VEX_COGNITION_SYSTEM + "\n\n" + V120_AGENT_RULES + "\nAvailable capability classes: " + ", ".join(capabilities)
    if grounding:
        system += "\n\nGrounding for this turn:\n" + grounding
    if tool_note:
        system += "\n\nConfirmed attempted tool result:\n" + tool_note

    safe_messages = [{"role": "system", "content": system[:18000]}]
    for item in history[-18:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").lower().strip()
        content = str(item.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            safe_messages.append({"role": role, "content": content[:3500]})
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
                    "temperature": 0.66,
                    "top_p": 0.90,
                    "num_ctx": 8192,
                    "repeat_penalty": 1.10,
                },
            },
            timeout=55,
        )
        response.raise_for_status()
        payload = response.json()
        raw = str(((payload.get("message") or {}).get("content")) or "")
        reply = _strip_reasoning_markup(raw)
        if not reply:
            return None
        return reply[:12000], model
    except Exception as exc:
        print(f"[agent] full-AI cognition failed: {exc}", flush=True)
        return None


'''
if "def _v120_capability_registry(" not in bridge:
    bridge = bridge.replace(insert_anchor, layer + insert_anchor, 1)

# Give the normal phone chat path the full agent wrapper rather than raw cognition.
old_call = "                result = _ollama_chat(history, message)\n"
new_call = "                result = _v120_agent_chat(history, message)\n"
if old_call not in bridge:
    raise SystemExit("v0.12.0 /llm/chat cognition call anchor missing")
bridge = bridge.replace(old_call, new_call, 1)

get_anchor = '        if parsed.path == "/llm/status":\n'
get_route = '''        if parsed.path == "/agent/capabilities":\n            self._json(200, {\n                "ok": True,\n                "version": V120_AGENT_VERSION,\n                "capabilities": _v120_capability_registry(),\n            })\n            return\n\n'''
if 'parsed.path == "/agent/capabilities"' not in bridge:
    if get_anchor not in bridge:
        raise SystemExit("v0.12.0 GET route anchor missing")
    bridge = bridge.replace(get_anchor, get_route + get_anchor, 1)

post_anchor = '        if parsed.path == "/llm/chat":\n'
post_routes = '''        if parsed.path == "/agent/plan":\n            try:\n                length = int(self.headers.get("Content-Length", "0") or "0")\n                if length <= 0 or length > 120_000:\n                    self._json(413, {"ok": False, "error": "agent payload too large"})\n                    return\n                payload = json.loads(self.rfile.read(length).decode("utf-8"))\n                message = str(payload.get("message") or "").strip()\n                self._json(200, {"ok": True, "plan": _v120_plan(message)})\n            except Exception as exc:\n                self._json(400, {"ok": False, "error": f"agent plan failed: {exc.__class__.__name__}"})\n            return\n\n        if parsed.path == "/agent/execute":\n            try:\n                length = int(self.headers.get("Content-Length", "0") or "0")\n                if length <= 0 or length > 120_000:\n                    self._json(413, {"ok": False, "error": "agent payload too large"})\n                    return\n                payload = json.loads(self.rfile.read(length).decode("utf-8"))\n                tool = str(payload.get("tool") or "")\n                args = payload.get("args") if isinstance(payload.get("args"), dict) else {}\n                confirm = bool(payload.get("confirm"))\n                result = _v120_execute_tool(tool, args, confirm=confirm)\n                self._json(200 if result.get("ok") else 400, result)\n            except Exception as exc:\n                self._json(400, {"ok": False, "error": f"agent execute failed: {exc.__class__.__name__}"})\n            return\n\n'''
if 'parsed.path == "/agent/plan"' not in bridge:
    if post_anchor not in bridge:
        raise SystemExit("v0.12.0 POST route anchor missing")
    bridge = bridge.replace(post_anchor, post_routes + post_anchor, 1)

bridge = bridge.replace('"agent_runtime_bundle": "0.11.7.80"', '"agent_runtime_bundle": "0.12.0"', 1)
installer = installer.replace('BUNDLE_VERSION = "0.11.7.80"', 'BUNDLE_VERSION = "0.12.0"', 1)
installer = installer.replace('Vex Agent Runtime v0.11.7.80', 'Vex Agent Runtime v0.12.0')

BRIDGE.write_text(bridge, encoding="utf-8")
INSTALLER.write_text(installer, encoding="utf-8")
compile(bridge, str(BRIDGE), "exec")
compile(installer, str(INSTALLER), "exec")

final = BRIDGE.read_text(encoding="utf-8")
required = [
    '"agent_runtime_bundle": "0.12.0"',
    'def _v120_capability_registry(',
    'def _v120_plan(',
    'def _v120_execute_tool(',
    'def _v120_agent_chat(',
    'parsed.path == "/agent/capabilities"',
    'parsed.path == "/agent/plan"',
    'parsed.path == "/agent/execute"',
    'result = _v120_agent_chat(history, message)',
    'def _v11776_launch_app(',
    'def _v11777_window_action(',
    'pc-memory-star-query-v11775',
]
for marker in required:
    if marker not in final:
        raise SystemExit(f"v0.12.0 verifier missing: {marker}")
if 'BUNDLE_VERSION = "0.12.0"' not in installer:
    raise SystemExit("v0.12.0 installer identity missing")
print("Applied Vex Agent Runtime v0.12.0 Full AI Foundation")
