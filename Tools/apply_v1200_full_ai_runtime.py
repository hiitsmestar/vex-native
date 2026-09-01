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
# One Vex identity can discover, plan and execute the capabilities already present
# in the cumulative runtime. Mutating actions remain authenticated/bounded/audited.
# ---------------------------------------------------------------------------
VEX_AGENT_VERSION = "0.12.0"
VEX_AGENT_ACTION_LOG = CONFIG_PATH.parent / "agent-actions.jsonl"


def _v1200_capability_registry() -> list[dict]:
    return [
        {"id": "chat", "kind": "cognition", "mutates": False},
        {"id": "memory.recall", "kind": "memory", "mutates": False},
        {"id": "memory.learn", "kind": "memory", "mutates": True},
        {"id": "research.web", "kind": "research", "mutates": False},
        {"id": "research.files", "kind": "research", "mutates": False},
        {"id": "apps.list", "kind": "device", "mutates": False},
        {"id": "apps.launch", "kind": "device", "mutates": True},
        {"id": "windows.control", "kind": "device", "mutates": True},
        {"id": "diagnostics", "kind": "maintenance", "mutates": False},
        {"id": "adaptive.learning", "kind": "learning", "mutates": True},
        {"id": "node.coordination", "kind": "orchestration", "mutates": False},
        {"id": "art.generate", "kind": "media", "mutates": True},
        {"id": "voice", "kind": "media", "mutates": False},
        {"id": "media.youtube", "kind": "media", "mutates": False},
        {"id": "browser.open", "kind": "device", "mutates": True},
    ]


def _v1200_audit(action: str, result: dict) -> None:
    try:
        record = {
            "time": time.time(),
            "version": VEX_AGENT_VERSION,
            "action": str(action or "")[:100],
            "ok": bool(result.get("ok")),
            "tool": str(result.get("tool") or "")[:80],
            "error": str(result.get("error") or "")[:160],
        }
        VEX_AGENT_ACTION_LOG.parent.mkdir(parents=True, exist_ok=True)
        with VEX_AGENT_ACTION_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
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
            # Conversational wrappers such as "Could you launch Calculator please?"
            # belong to the request, not to the Windows app name.
            name = re.sub(r"\s+(?:please|for me)\s*$", "", name, flags=re.I).strip(" \"'.,!?-")
            if name and len(name) <= 180 and not any(x in name for x in ("http://", "https://", "\\", "/")):
                return name
    return None


def _v1200_research_query(message: str) -> tuple[str, str] | None:
    text = _v1200_clean_request(message)
    lower = text.lower()
    for marker in ("search my files for ", "find in my files ", "look in my files for ", "search the pc for "):
        if marker in lower:
            query = text[lower.index(marker) + len(marker):].strip(" .?!")
            return ("files", query) if query else None
    for marker in ("search the web for ", "search online for ", "look up ", "research "):
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
    if any(x in lower for x in ("what can you do", "what are your capabilities", "list your capabilities", "what tools do you have")):
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
        lines.append(f"- {title}: {snippet}" if snippet else f"- {title}")
    return "\n".join(lines)


def _v1200_execute_plan(plan: dict, dry_run: bool = False) -> dict:
    steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
    if len(steps) != 1:
        return {"ok": False, "version": VEX_AGENT_VERSION, "error": "plan must contain one accepted step"}
    step = steps[0] if isinstance(steps[0], dict) else {}
    tool = str(step.get("tool") or "")
    args = step.get("args") if isinstance(step.get("args"), dict) else {}

    if tool == "agent.capabilities":
        caps = _v1200_capability_registry()
        return {"ok": True, "version": VEX_AGENT_VERSION, "tool": tool, "capabilities": caps,
                "reply": "Baby, my wired runtime capabilities are: " + ", ".join(c["id"] for c in caps) + ". 🖤"}
    if tool == "memory.recall":
        recalled = _verified_personal_memory_reply(str(args.get("query") or ""))
        if recalled is None:
            return {"ok": False, "version": VEX_AGENT_VERSION, "tool": tool, "error": "verified personal memory unavailable"}
        reply, model = recalled
        return {"ok": True, "version": VEX_AGENT_VERSION, "tool": tool, "reply": reply, "model": model}
    if tool == "apps.launch":
        result = dict(_v11776_launch_app(str(args.get("name") or ""), dry_run=dry_run))
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
        return {"ok": True, "version": VEX_AGENT_VERSION, "tool": tool, "query": query, "results": results,
                "reply": _v1200_format_search(scope, query, results)}
    return {"ok": True, "version": VEX_AGENT_VERSION, "tool": "chat", "delegated": "llm"}


def _v1200_agent_try_handle(message: str, dry_run: bool = False) -> dict:
    plan = _v1200_plan(message)
    if not bool(plan.get("auto_execute")):
        return {"ok": True, "version": VEX_AGENT_VERSION, "delegated": "chat", "plan": plan}
    result = _v1200_execute_plan(plan, dry_run=dry_run)
    _v1200_audit(str((plan.get("steps") or [{}])[0].get("tool") or "unknown"), result)
    result["plan"] = plan
    return result


'''
bridge = bridge.replace(insert_anchor, layer + insert_anchor, 1)

get_anchor = '        if parsed.path == "/windows/apps":\n'
get_route = '''        if parsed.path == "/agent/capabilities":\n            caps = _v1200_capability_registry()\n            self._json(200, {"ok": True, "version": VEX_AGENT_VERSION, "count": len(caps), "capabilities": caps})\n            return\n\n'''
if get_anchor not in bridge:
    raise SystemExit("v0.12.0 GET route anchor missing")
bridge = bridge.replace(get_anchor, get_route + get_anchor, 1)

post_anchor = '        if parsed.path == "/windows/window-action":\n'
post_routes = '''        if parsed.path == "/agent/plan":\n            self._json(200, _v1200_plan(str(body.get("message") or "")))\n            return\n\n        if parsed.path == "/agent/run":\n            result = _v1200_agent_try_handle(str(body.get("message") or ""), dry_run=bool(body.get("dry_run")))\n            self._json(200 if result.get("ok") else 503, result)\n            return\n\n'''
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

required = [
    '"agent_runtime_bundle": "0.12.0"', 'def _v1200_capability_registry(', 'def _v1200_plan(',
    'def _v1200_execute_plan(', 'def _v1200_agent_try_handle(', 'parsed.path == "/agent/capabilities"',
    'parsed.path == "/agent/plan"', 'parsed.path == "/agent/run"', 'VEX_AGENT_ACTION_LOG',
    'def _v11776_launch_app(', 'def _v11777_window_action(', 'pc-memory-star-query-v11775',
]
for marker in required:
    if marker not in bridge:
        raise SystemExit(f"v0.12.0 verifier missing: {marker}")
if 'BUNDLE_VERSION = "0.12.0"' not in installer:
    raise SystemExit("v0.12.0 installer identity missing")
print("Applied Vex Agent Runtime v0.12.0 full AI orchestration foundation")
