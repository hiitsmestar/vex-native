#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
bridge = BRIDGE.read_text(encoding="utf-8")
MARKER = 'V120_DC_ADAPTER = "v0.12-desktop-commander-mcp-v1"'
if MARKER in bridge:
    print("Desktop Commander adapter already applied")
    raise SystemExit(0)

anchor = "def _v120_capability_registry() -> list[dict]:\n"
if anchor not in bridge:
    raise SystemExit("v0.12 capability registry anchor missing")
layer = r'''
V120_DC_ADAPTER = "v0.12-desktop-commander-mcp-v1"
V120_DC_URL = os.environ.get("VEX_DC_ADAPTER_URL", "http://127.0.0.1:8776").rstrip("/")
V120_DC_SESSION = requests.Session()
V120_DC_SESSION.trust_env = False


def _v120_dc_health(timeout: float = 1.2) -> dict:
    try:
        response = V120_DC_SESSION.get(f"{V120_DC_URL}/health", timeout=timeout)
        data = response.json() if response.content else {}
        if not isinstance(data, dict):
            data = {"value": data}
        data["http_status"] = response.status_code
        return data
    except Exception as exc:
        return {"ok": False, "error": exc.__class__.__name__}


def _v120_dc_call(name: str, arguments: dict | None = None, timeout: float = 12.0) -> dict:
    try:
        response = V120_DC_SESSION.post(
            f"{V120_DC_URL}/call",
            json={"tool": str(name or ""), "arguments": arguments if isinstance(arguments, dict) else {}},
            timeout=timeout,
        )
        data = response.json() if response.content else {}
        if not isinstance(data, dict):
            data = {"value": data}
        data["http_status"] = response.status_code
        return data
    except Exception as exc:
        return {"ok": False, "error": exc.__class__.__name__}


'''
bridge = bridge.replace(anchor, layer + anchor, 1)

definition_anchor = '        ("node_routing", "health-aware multi-PC routing", False, False),\n'
if definition_anchor not in bridge:
    raise SystemExit("v0.12 capability definition anchor missing")
bridge = bridge.replace(
    definition_anchor,
    definition_anchor + '        ("desktop_commander", "bounded Desktop Commander MCP filesystem and process inspection", True, False),\n',
    1,
)

case_anchor = '''        elif name == "node_routing":
            available, detail = True, "Bridge/iPhone resource director"
        else:
'''
case_replace = '''        elif name == "node_routing":
            available, detail = True, "Bridge/iPhone resource director"
        elif name == "desktop_commander":
            health = _v120_dc_health()
            available = bool(health.get("ok")) and 200 <= int(health.get("http_status") or 0) < 300
            detail = "Desktop Commander MCP adapter" if available else str(health.get("error") or "adapter unavailable")
        else:
'''
if case_anchor not in bridge:
    raise SystemExit("v0.12 capability case anchor missing")
bridge = bridge.replace(case_anchor, case_replace, 1)

plan_anchor = '    if any(x in lower for x in ("repair yourself", "self repair", "fix your runtime", "diagnose yourself")):\n'
plan_layer = '''    if any(x in lower for x in ("list processes", "running processes", "what is running", "what's running")):
        plan["steps"].append({"tool": "dc.list_processes", "args": {}, "risk": "read"})
'''
if plan_anchor not in bridge:
    raise SystemExit("v0.12 planning anchor missing")
bridge = bridge.replace(plan_anchor, plan_layer + plan_anchor, 1)

execute_anchor = '    if tool == "conversation.reason":\n'
execute_layer = '''    if tool.startswith("dc."):
        mapping = {
            "dc.list_processes": "list_processes",
            "dc.list_directory": "list_directory",
            "dc.read_file": "read_file",
            "dc.get_file_info": "get_file_info",
        }
        backend_tool = mapping.get(tool)
        if not backend_tool:
            return {"ok": False, "tool": tool, "error": "Desktop Commander action is not registered"}
        result = _v120_dc_call(backend_tool, args)
        return {"ok": bool(result.get("ok")), "tool": tool, "provider": "desktop-commander-mcp", "result": result}
'''
if execute_anchor not in bridge:
    raise SystemExit("v0.12 execute anchor missing")
bridge = bridge.replace(execute_anchor, execute_layer + execute_anchor, 1)

chat_anchor = '''    else:
        tool_note = ""

    model = _choose_ollama_model()
'''
chat_replace = '''    else:
        tool_note = ""

    if not tool_note and isinstance(steps, list) and len(steps) == 1 and isinstance(steps[0], dict):
        planned_tool = str(steps[0].get("tool") or "")
        if planned_tool.startswith("dc."):
            result = _v120_execute_tool(planned_tool, steps[0].get("args") or {}, confirm=False)
            tool_note = json.dumps(result, ensure_ascii=False)[:12000]

    model = _choose_ollama_model()
'''
if chat_anchor not in bridge:
    raise SystemExit("v0.12 agent-chat tool note anchor missing")
bridge = bridge.replace(chat_anchor, chat_replace, 1)

BRIDGE.write_text(bridge, encoding="utf-8")
compile(bridge, str(BRIDGE), "exec")
for required in [MARKER, '"desktop_commander"', 'tool.startswith("dc.")', '"dc.list_processes"', 'provider": "desktop-commander-mcp"']:
    if required not in bridge:
        raise SystemExit(f"Desktop Commander verifier missing: {required}")
print("Applied bounded Desktop Commander MCP provider to Vex Agent Runtime v0.12")
