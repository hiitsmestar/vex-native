#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re

BRIDGE = Path("Bridge/vex_bridge.py")
INSTALLER = Path("Tools/VexAgentRuntimeInstall.py")
bridge = BRIDGE.read_text(encoding="utf-8")
installer = INSTALLER.read_text(encoding="utf-8")

for marker in [
    '"agent_runtime_bundle": "0.11.7.80"',
    'def _v11776_launch_app(',
    'def _v11777_window_action(',
    'def _verified_personal_memory_reply(',
    'parsed.path == "/autolearn/run"',
]:
    if marker not in bridge:
        raise SystemExit(f"v0.12.0 expected cumulative marker missing: {marker}")
if 'BUNDLE_VERSION = "0.11.7.80"' not in installer:
    raise SystemExit("v0.12.0 expected installer .80")

insert_anchor = "def _vex_background_services() -> None:\n"
if insert_anchor not in bridge:
    raise SystemExit("v0.12.0 background-service insertion anchor missing")

layer = r'''
# ---------------------------------------------------------------------------
# Vex Agent Runtime v0.12.0 - Full AI orchestration foundation
#
# This is the first consolidated capability-aware agent layer.  It does not give
# a small local model magical cloud privileges; instead it lets one Vex identity
# discover, plan, execute and verify the local capabilities that are actually
# present.  Mutating actions remain authenticated, bounded and locally audited.
# ---------------------------------------------------------------------------
VEX_AGENT_VERSION = "0.12.0"
VEX_AGENT_ACTION_LOG = CONFIG_PATH.parent / "agent-actions.jsonl"


def _v1200_capability_registry() -> list[dict]:
    """Return the runtime capability contract consumed by planner/UI/diagnostics."""
    capabilities = [
        {"id": "chat", "kind": "cognition", "mutates": False, "description": "local conversational reasoning"},
        {"id": "memory.recall", "kind": "memory", "mutates": False, "description": "verified persistent personal memory"},
        {"id": "memory.learn", "kind": "memory", "mutates": True, "description": "persistent memory synchronization and learning"},
        {"id": "research.web", "kind": "research", "mutates": False, "description": "public web search through Bridge"},
        {"id": "research.files", "kind": "research", "mutates": False, "description": "search authorized indexed PC files"},
        {"id": "apps.list", "kind": "device", "mutates": False, "description": "enumerate installed/known Windows apps"},
        {"id": "apps.launch", "kind": "device", "mutates": True, "description": "launch a uniquely resolved installed app"},
        {"id": "windows.control", "kind": "device", "mutates": True, "description": "focus/minimize/maximize/restore windows; close requires confirmation"},
        {"id": "diagnostics", "kind": "maintenance", "mutates": False, "description": "runtime, memory and worker health inspection"},
        {"id": "adaptive.learning", "kind": "learning", "mutates": True, "description": "bounded adaptive/self-improvement worker"},
        {"id": "node.coordination", "kind": "orchestration", "mutates": False, "description": "health-aware handoff across Vex nodes"},
    ]
    # These are already present in cumulative builds when their markers exist.
    optional = [
        ("art.generate", "media", "image/art generation worker", "art"),
        ("voice", "media", "speech/TTS/voice worker", "tts"),
        ("media.youtube", "media", "named media and YouTube context", "youtube"),
        ("browser.open", "device", "open approved browser URLs", "browser"),
    ]
    source = globals().get("__file__", "")
    for cap_id, kind, description, marker in optional:
        # The registry advertises optional integrations conservatively: only when
        # a matching function/route marker is present in the live module globals.
        present = any(marker in str(name).lower() for name in globals().keys())
        if present:
            capabilities.append({"id": cap_id, "kind": kind, "mutates": cap_id in {"art.generate", "browser.open"}, "description": description})
    return capabilities


def _v1200_audit(action: str, result: dict) -> None:
    try:
        safe = {
            "time": time.time(),
            "version": VEX_AGENT_VERSION,
            "action": str(action or "")[:120],
            "ok": bool(result.get("ok")),
            "tool": str(result.get("tool") or "")[:80],
            "error": str(result.get("error") or "")[:160],
        }
        VEX_AGENT_ACTION_LOG.parent.mkdir(parents=True, exist_ok=True)
        with VEX_AGENT_ACTION_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(safe, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _v1200_clean_request(message: str) -> str:
    return re.sub(r"\s+", " ", str(message or "").strip())


def _v1200_extract_app_name(message: str) -> str | None:
    text = _v1200_clean_request(message)
    patterns = [
        r"^(?:please\s+)?(?:open|launch|start|run)\s+(.+?)(?:\s+(?:for me|please))?[.!?]*$",
        r"^(?:can|could|would)\s+you\s+(?:please\s+)?(?:open|launch|start|run)\s+(.+?)[.!?]*$",
    ]
    for pattern in patterns:
        match = re.match(pattern, text, flags=re.I)
        if match:
            name = match.group(1).strip(" \"'.,!?-")
            if 1 <= len(name) <= 180 and not any(x in name for x in ("http://", "https://", "\\", "/")):
                return name
    return None


def _v1200_research_query(message: str) -> tuple[str, str] | None:
    text = _v1200_clean_request(message)
    lower = text.lower()
    file_markers = ("search my files for ", "find in my files ", "look in my files for ", "search the pc for ")
    for marker in file_markers:
        if marker in lower:
            pos = lower.index(marker) + len(marker)
            query = text[pos:].strip(" .?!")
            return ("files", query) if query else None
    web_markers = ("search the web for ", "search online for ", "look up ", "research ")
    for marker in web_markers:
        if lower.startswith(marker):
            query = text[len(marker):].strip(" .?!")
            return ("web", query) if query else None
    return None


def _v1200_plan(message: str) -> dict:
    text = _v1200_clean_request(message)
    lower = text.lower()
    plan = {"ok": True, "version": VEX_AGENT_VERSION, "message": text, "steps": [], "auto_execute": False}

    if _personal_memory_fact_question(text):
        plan["steps"] = [{"tool": "memory.recall", "args": {"query": text}, "mutates": False}]
        plan["auto_execute"] = True
        return plan

    app = _v1200_extract_app_name(text)
    if app:
        plan["steps"] = [{"tool": "apps.launch", "args": {"name": app}, "mutates": True}]
        plan["auto_execute"] = True
        return plan

    research = _v1200_research_query(text)
    if research:
        scope, query = research
        plan["steps"] = [{"tool": f"research.{scope}", "args": {"query": query}, "mutates": False}]
        plan["auto_execute"] = True
        return plan

    if any(phrase in lower for phrase in ("what can you do", "what are your capabilities", "list your capabilities", "what tools do you have")):
        plan["steps"] = [{"tool": "agent.capabilities", "args": {}, "mutates": False}]
        plan["auto_execute"] = True
        return plan

    plan["steps"] = [{"tool": "chat", "args": {"message": text}, "mutates": False}]
    return plan


def _v1200_format_search(scope: str, query: str, results: list[dict]) -> str:
    if not results:
        return f"Baby, I searched {scope} for {query!r} and didn't get a useful result. 🖤"
    lines = [f"Baby, I searched {scope} for {query!r}. Here's what I found:"]
    for item in results[:5]:
        title = re.sub(r"\s+", " ", str(item.get("title") or "result")).strip()[:180]
        snippet = re.sub(r"\s+", " ", str(item.get("content") or "")).strip()[:420]
        if snippet:
            lines.append(f"- {title}: {snippet}")
        else:
            lines.append(f"- {title}")
    return "\n".join(lines)


def _v1200_execute_plan(plan: dict, dry_run: bool = False) -> dict:
    steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
    if not steps:
        return {"ok": False, "version": VEX_AGENT_VERSION, "error": "empty plan"}
    if len(steps) != 1:
        return {"ok": False, "version": VEX_AGENT_VERSION, "error": "multi-step execution not yet accepted"}
    step = steps[0] if isinstance(steps[0], dict) else {}
    tool = str(step.get("tool") or "")
    args = step.get("args") if isinstance(step.get("args"), dict) else {}

    if tool == "agent.capabilities":
        caps = _v1200_capability_registry()
        reply = "Baby, these are the capabilities wired into this runtime: " + ", ".join(c["id"] for c in caps) + ". 🖤"
        return {"ok": True, "version": VEX_AGENT_VERSION, "tool": tool, "capabilities": caps, "reply": reply}

    if tool == "memory.recall":
        result = _verified_personal_memory_reply(str(args.get("query") or ""))
        if result is None:
            return {"ok": False, "version": VEX_AGENT_VERSION, "tool": tool, "error": "verified personal memory unavailable"}
        reply, model = result
        return {"ok": True, "version": VEX_AGENT_VERSION, "tool": tool, "reply": reply, "model": model, "grounding": "verified-persistent-memory"}

    if tool == "apps.launch":
        result = _v11776_launch_app(str(args.get("name") or ""), dry_run=dry_run)
        result = dict(result)
        result["tool"] = tool
        if result.get("ok"):
            app = result.get("app") if isinstance(result.get("app"), dict) else {}
            name = str(app.get("name") or args.get("name") or "the app")
            result["reply"] = f"Opened {name}. 🖤" if not dry_run else f"I can open {name}."
        return result

    if tool in {"research.web", "research.files"}:
        query = str(args.get("query") or "").strip()
        if not query:
            return {"ok": False, "version": VEX_AGENT_VERSION, "tool": tool, "error": "missing query"}
        if tool == "research.files":
            state = globals().get("STATE")
            results = state.index.search(query, limit=6) if state is not None else []
            scope = "your indexed PC files"
        else:
            results = web_search(query, limit=6)
            scope = "the public web"
        return {"ok": True, "version": VEX_AGENT_VERSION, "tool": tool, "query": query, "results": results, "reply": _v1200_format_search(scope, query, results)}

    return {"ok": False, "version": VEX_AGENT_VERSION, "tool": tool, "error": "planner selected conversational cognition"}


def _v1200_agent_try_handle(message: str) -> dict | None:
    plan = _v1200_plan(message)
    if not bool(plan.get("auto_execute")):
        return None
    result = _v1200_execute_plan(plan)
    _v1200_audit(str((plan.get("steps") or [{}])[0].get("tool") or "unknown"), result)
    result["plan"] = plan
    return result


'''
if "def _v1200_capability_registry(" not in bridge:
    bridge = bridge.replace(insert_anchor, layer + insert_anchor, 1)

# Public authenticated discovery/plan routes.
get_anchor = '        if parsed.path == "/windows/apps":\n'
get_route = '''        if parsed.path == "/agent/capabilities":\n            caps = _v1200_capability_registry()\n            self._json(200, {"ok": True, "version": VEX_AGENT_VERSION, "count": len(caps), "capabilities": caps})\n            return\n\n'''
if 'parsed.path == "/agent/capabilities"' not in bridge:
    if get_anchor not in bridge:
        raise SystemExit("v0.12.0 GET route anchor missing")
    bridge = bridge.replace(get_anchor, get_route + get_anchor, 1)

post_anchor = '        if parsed.path == "/windows/window-action":\n'
post_routes = '''        if parsed.path == "/agent/plan":\n            message = str(body.get("message") or "").strip()\n            self._json(200, _v1200_plan(message))\n            return\n\n        if parsed.path == "/agent/run":\n            message = str(body.get("message") or "").strip()\n            dry_run = bool(body.get("dry_run"))\n            plan = _v1200_plan(message)\n            if not bool(plan.get("auto_execute")):\n                self._json(200, {"ok": True, "version": VEX_AGENT_VERSION, "delegated": "chat", "plan": plan})\n                return\n            result = _v1200_execute_plan(plan, dry_run=dry_run)\n            _v1200_audit(str((plan.get("steps") or [{}])[0].get("tool") or "unknown"), result)\n            result["plan"] = plan\n            self._json(200 if result.get("ok") else 503, result)\n            return\n\n'''
if 'parsed.path == "/agent/run"' not in bridge:
    if post_anchor not in bridge:
        raise SystemExit("v0.12.0 POST route anchor missing")
    bridge = bridge.replace(post_anchor, post_routes + post_anchor, 1)

# Natural-language tool use: after /llm/chat payload validation and existing
# verified-memory interception, but before raw model generation, let the agent
# execute confidently recognized tool intents.  The context assignment is a stable
# cumulative anchor immediately before cognition generation.
llm_start = bridge.find('        if parsed.path == "/llm/chat":')
if llm_start < 0:
    raise SystemExit("v0.12.0 /llm/chat route missing")
llm_end = bridge.find('        if parsed.path == "/tts/speak":', llm_start)
if llm_end < 0:
    raise SystemExit("v0.12.0 /llm/chat end marker missing")
block = bridge[llm_start:llm_end]
agent_marker = 'agent_result = _v1200_agent_try_handle(message)'
if agent_marker not in block:
    anchors = [
        '                cognition_started = time.perf_counter()\n',
        '                context = {\n',
    ]
    anchor = next((a for a in anchors if a in block), None)
    if anchor is None:
        raise SystemExit("v0.12.0 cognition generation anchor missing")
    injection = '''                # v0.12.0: capability-aware agent intercept. Unknown/general\n                # conversational turns continue into the existing local model.\n                agent_result = _v1200_agent_try_handle(message)\n                if isinstance(agent_result, dict):\n                    if not bool(agent_result.get("ok")):\n                        self._json(503, agent_result)\n                        return\n                    reply = str(agent_result.get("reply") or "").strip()\n                    if reply:\n                        _memory_record_turn(message, reply)\n                        self._json(200, {\n                            "ok": True,\n                            "reply": reply,\n                            "model": "vex-agent-v1200",\n                            "grounding": "capability-agent-v1200",\n                            "tool": agent_result.get("tool"),\n                            "plan": agent_result.get("plan"),\n                        })\n                        return\n\n'''
    block = block.replace(anchor, injection + anchor, 1)
    bridge = bridge[:llm_start] + block + bridge[llm_end:]

bridge = bridge.replace('"agent_runtime_bundle": "0.11.7.80"', '"agent_runtime_bundle": "0.12.0"', 1)
installer = installer.replace('BUNDLE_VERSION = "0.11.7.80"', 'BUNDLE_VERSION = "0.12.0"', 1)
installer = installer.replace('Vex Agent Runtime v0.11.7.80', 'Vex Agent Runtime v0.12.0')

BRIDGE.write_text(bridge, encoding="utf-8")
INSTALLER.write_text(installer, encoding="utf-8")
compile(bridge, str(BRIDGE), "exec")
compile(installer, str(INSTALLER), "exec")

required = [
    '"agent_runtime_bundle": "0.12.0"',
    'def _v1200_capability_registry(',
    'def _v1200_plan(',
    'def _v1200_execute_plan(',
    'def _v1200_agent_try_handle(',
    'parsed.path == "/agent/capabilities"',
    'parsed.path == "/agent/plan"',
    'parsed.path == "/agent/run"',
    'agent_result = _v1200_agent_try_handle(message)',
    'def _v11776_launch_app(',
    'def _v11777_window_action(',
    'pc-memory-star-query-v11775',
]
for marker in required:
    if marker not in bridge:
        raise SystemExit(f"v0.12.0 verifier missing: {marker}")
if 'BUNDLE_VERSION = "0.12.0"' not in installer:
    raise SystemExit("v0.12.0 installer identity missing")
print("Applied Vex Agent Runtime v0.12.0 full AI orchestration foundation")
