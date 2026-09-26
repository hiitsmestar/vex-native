from __future__ import annotations

import asyncio
import json
import os
import socket
import ssl
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable

import uvicorn
from a2a.helpers import get_message_text, new_task_from_user_message, new_text_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from a2a.types.a2a_pb2 import TaskState
from a2a.utils.constants import AGENT_CARD_WELL_KNOWN_PATH
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

HOST = os.environ.get("VEX_A2A_HOST", os.environ.get("VEXA2A_HOST", "127.0.0.1"))
PORT = int(os.environ.get("VEX_A2A_PORT", os.environ.get("VEXA2A_PORT", "8796")))
PUBLIC_URL = os.environ.get("VEX_A2A_PUBLIC_URL", os.environ.get("VEXA2A_PUBLIC_URL", f"http://127.0.0.1:{PORT}"))
MCP_URL = os.environ.get("VEX_A2A_MCP_URL", os.environ.get("VEXBRIDGE_MCP_URL", "http://127.0.0.1:8795/mcp"))
OLLAMA = os.environ.get("VEX_A2A_OLLAMA", "http://127.0.0.1:11434")
FAST_MODEL = os.environ.get("VEX_A2A_FAST_MODEL", "vex-qwen35-9b-q6:latest")
DEEP_MODEL = os.environ.get("VEX_A2A_DEEP_MODEL", "vex-qwen35-a3b-text:latest")
RENDER_SCRIPT = Path(os.environ.get("VEX_A2A_RENDER_SCRIPT", str(Path.home() / "Documents" / "VexAutoRender.py")))
PHONE_CONFIG = Path(os.environ.get("APPDATA", str(Path.home()))) / "VexBridge" / "config.json"
PHONE_BASE = "https://127.0.0.1:8771"
SYSTEM_PROMPT = os.environ.get("VEX_A2A_SYSTEM_PROMPT", "You are the local VexNative cognition worker. Be concise, tool-aware, and return only the requested result.")

def as_json(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except Exception:
        return None

async def mcp_call(tool: str, arguments: dict[str, Any]) -> Any:
    async with streamablehttp_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            names = {t.name for t in (await session.list_tools()).tools}
            if tool not in names:
                raise ValueError(f"unknown VexBridge tool: {tool}")
            result = await session.call_tool(tool, arguments)
            if getattr(result, "isError", False):
                raise RuntimeError("\n".join(getattr(x, "text", "") for x in result.content))
            structured = getattr(result, "structuredContent", None)
            if structured:
                return structured.get("result", structured)
            text = "\n".join(getattr(x, "text", "") for x in result.content)
            try:
                return json.loads(text)
            except Exception:
                return text

def url_json(url: str, payload: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: int = 30) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **(headers or {})})
    context = ssl._create_unverified_context() if url.startswith("https://127.0.0.1") else None
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        return json.loads(response.read().decode("utf-8"))

async def memory_agent(text: str) -> str:
    req = as_json(text)
    if req and req.get("action") == "store":
        result = await mcp_call("icm_store", {k: v for k, v in req.items() if k in {"topic", "content", "importance", "keywords", "raw"}})
    else:
        query = str((req or {}).get("query") or text)
        args = {"query": query, "limit": int((req or {}).get("limit", 5))}
        for key in ("topic", "keyword", "project"):
            if (req or {}).get(key) is not None:
                args[key] = req[key]
        result = await mcp_call("icm_recall", args)
    return json.dumps(result, ensure_ascii=False, indent=2)

async def verification_agent(text: str) -> str:
    req = as_json(text) or {"gate_file": text.strip()}
    action = str(req.get("action", "status")).lower()
    gate = str(req.get("gate_file") or "")
    if not gate:
        raise ValueError("gate_file is required")
    if action == "lint":
        result = await mcp_call("unlazy_lint", {"gate_file": gate, "strict": bool(req.get("strict", True))})
    else:
        args: dict[str, Any] = {"gate_file": gate}
        if req.get("root"):
            args["root"] = req["root"]
        if req.get("scope"):
            args["scope"] = req["scope"]
        result = await mcp_call("unlazy_status", args)
    return json.dumps(result, ensure_ascii=False, indent=2)

async def system_agent(text: str) -> str:
    req = as_json(text)
    if not req or not req.get("tool"):
        raise ValueError('system agent expects JSON: {"tool":"read_file","arguments":{...}}')
    tool = str(req["tool"])
    if tool in {"shutdown", "a2a_send", "a2a_agents", "a2a_health"}:
        raise ValueError(f"tool blocked from A2A system recursion: {tool}")
    result = await mcp_call(tool, dict(req.get("arguments") or {}))
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)

def phone_sync(command: str, wait_seconds: int) -> Any:
    cfg = json.loads(PHONE_CONFIG.read_text(encoding="utf-8-sig"))
    token = str(cfg.get("token") or "")
    if not token:
        raise RuntimeError("PhoneRelay token missing")
    query = urllib.parse.urlencode({"token": token})
    queued = url_json(PHONE_BASE + "/phone/command?" + query, {"command": command, "source": "vex-a2a"}, timeout=10)
    item = queued["command"]
    if wait_seconds <= 0:
        return item
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        time.sleep(1)
        try:
            result = url_json(PHONE_BASE + "/phone/result?" + urllib.parse.urlencode({"token": token, "id": item["id"]}), timeout=10)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                continue
            raise
        item = result.get("command") or {}
        if item.get("state") in {"completed", "failed"}:
            return item
    return {"id": item.get("id"), "state": "timeout"}

async def phone_agent(text: str) -> str:
    req = as_json(text)
    command = str((req or {}).get("command") or text)
    wait_seconds = int((req or {}).get("wait", 120))
    result = await asyncio.to_thread(phone_sync, command, wait_seconds)
    return json.dumps(result, ensure_ascii=False, indent=2)

def render_sync(req: dict[str, Any]) -> dict[str, Any]:
    if not RENDER_SCRIPT.exists():
        raise FileNotFoundError(str(RENDER_SCRIPT))
    prompt = str(req.get("prompt") or "")
    if not prompt:
        raise ValueError("render prompt is required")
    argv = ["py", "-3.12", str(RENDER_SCRIPT), prompt, "--mode", str(req.get("mode", "normal")), "--orientation", str(req.get("orientation", "portrait"))]
    if int(req.get("seed", 0)):
        argv += ["--seed", str(int(req["seed"]))]
    run = subprocess.run(argv, text=True, capture_output=True, timeout=int(req.get("timeout", 3600)), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    out = ((run.stdout or "") + "\n" + (run.stderr or "")).strip()
    if run.returncode != 0:
        raise RuntimeError(out[-4000:])
    return {"ok": True, "output": out[-8000:]}

async def renderer_agent(text: str) -> str:
    req = as_json(text) or {"prompt": text}
    result = await asyncio.to_thread(render_sync, req)
    return json.dumps(result, ensure_ascii=False, indent=2)

def ollama_sync(req: dict[str, Any]) -> str:
    mode = str(req.get("mode", "fast")).lower()
    model = str(req.get("model") or (DEEP_MODEL if mode == "deep" else FAST_MODEL))
    payload = {"model": model, "prompt": str(req.get("prompt") or ""), "system": SYSTEM_PROMPT, "stream": False, "options": {"num_ctx": int(req.get("num_ctx", 4096))}}
    result = url_json(OLLAMA + "/api/generate", payload, timeout=int(req.get("timeout", 600)))
    return str(result.get("response") or "")

async def cognition_agent(text: str) -> str:
    req = as_json(text) or {"prompt": text}
    if "prompt" not in req:
        req["prompt"] = text
    return await asyncio.to_thread(ollama_sync, req)

def a2a_post_sync(agent: str, text: str) -> str:
    body = {"jsonrpc": "2.0", "id": uuid.uuid4().hex, "method": "SendMessage", "params": {"message": {"messageId": uuid.uuid4().hex, "role": "ROLE_USER", "parts": [{"text": text}]}, "configuration": {"acceptedOutputModes": ["text/plain"], "returnImmediately": False}}}
    result = url_json(f"{PUBLIC_URL}/{agent}", body, headers={"A2A-Version": "1.0"}, timeout=900)
    if result.get("error"):
        raise RuntimeError(json.dumps(result["error"]))
    payload = result.get("result") or {}
    message = payload.get("message")
    if message:
        return "\n".join(str(p.get("text", "")) for p in message.get("parts", []) if p.get("text"))
    task = payload.get("task") or payload
    texts: list[str] = []
    for artifact in task.get("artifacts") or []:
        for part in artifact.get("parts") or []:
            if part.get("text"):
                texts.append(str(part["text"]))
    return "\n".join(texts) or json.dumps(payload, ensure_ascii=False)

async def coordinator_agent(text: str) -> str:
    raw = text.strip()
    low = raw.lower()
    if low in {"agents", "list agents", "status", "help", ""}:
        return json.dumps({
            "ok": True,
            "protocol": "1.0",
            "agents": [p.strip("/") for p, _, _ in AGENTS],
        })
    explicit = {"memory:": "memory", "verify:": "verification", "verification:": "verification", "phone:": "phone", "render:": "renderer", "system:": "system", "cognition:": "cognition", "think:": "cognition"}
    for prefix, agent in explicit.items():
        if low.startswith(prefix):
            return await asyncio.to_thread(a2a_post_sync, agent, raw[len(prefix):].strip())
    if low.startswith("{") and '"tool"' in low:
        agent = "system"
    elif any(x in low for x in ("remember ", "recall ", "memory ", "what do you remember")):
        agent = "memory"
    elif any(x in low for x in ("unlazy", "gate", "verify acceptance", "verification ledger")):
        agent = "verification"
    elif any(x in low for x in ("on my phone", "iphone", "phone command")):
        agent = "phone"
    elif any(x in low for x in ("render ", "comfyui", "generate image")):
        agent = "renderer"
    else:
        agent = "cognition"
    return await asyncio.to_thread(a2a_post_sync, agent, raw)

Handler = Callable[[str], Awaitable[str]]

class VexAgentExecutor(AgentExecutor):
    def __init__(self, handler: Handler) -> None:
        self.handler = handler

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task
        if task is None:
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue=event_queue, task_id=task.id, context_id=task.context_id)
        await updater.update_status(state=TaskState.TASK_STATE_WORKING, message=new_text_message("working"))
        query = get_message_text(context.message) or ""
        try:
            result = await self.handler(query)
            await updater.add_artifact(parts=[new_text_part(text=result, media_type="text/plain")])
            await updater.update_status(state=TaskState.TASK_STATE_COMPLETED, message=new_text_message("done"))
        except Exception as exc:
            await updater.add_artifact(parts=[new_text_part(text=f"{type(exc).__name__}: {exc}", media_type="text/plain")])
            await updater.update_status(state=TaskState.TASK_STATE_FAILED, message=new_text_message("failed"))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("cancel not supported")

def card(path: str, name: str, description: str, examples: list[str]) -> AgentCard:
    return AgentCard(name=name, description=description, version="1.0.0", default_input_modes=["text/plain"], default_output_modes=["text/plain"], capabilities=AgentCapabilities(streaming=True), supported_interfaces=[AgentInterface(protocol_binding="JSONRPC", url=f"{PUBLIC_URL}{path}", protocol_version="1.0")], skills=[AgentSkill(id=path.strip("/"), name=name, description=description, input_modes=["text/plain"], output_modes=["text/plain"], tags=["vexnative", "a2a", path.strip("/")], examples=examples)])

AGENTS: list[tuple[str, AgentCard, VexAgentExecutor]] = [
    ("/coordinator", card("/coordinator", "Vex Coordinator", "Routes work to VexNative specialist agents over A2A.", ["memory: recall VexBridge state", "phone: open YouTube"]), VexAgentExecutor(coordinator_agent)),
    ("/cognition", card("/cognition", "Vex Cognition", "Local Ollama reasoning worker with fast/deep model modes.", ["Explain this code", '{"prompt":"plan the upgrade","mode":"deep"}']), VexAgentExecutor(cognition_agent)),
    ("/memory", card("/memory", "Vex Memory", "ICM-backed auxiliary memory recall/store agent.", ["recall VexBridge", '{"action":"store","topic":"x","content":"y"}']), VexAgentExecutor(memory_agent)),
    ("/verification", card("/verification", "Vex Verification", "Unlazy acceptance-ledger status and lint agent.", ['{"gate_file":"C:\\\\path\\\\GATES.md"}']), VexAgentExecutor(verification_agent)),
    ("/phone", card("/phone", "Vex Phone", "Queues natural-language commands through VexPhoneRelay.", ["open YouTube on my phone"]), VexAgentExecutor(phone_agent)),
    ("/renderer", card("/renderer", "Vex Renderer", "Queues prompt-driven ComfyUI renders through VexAutoRender.", ["neon club portrait"]), VexAgentExecutor(renderer_agent)),
    ("/system", card("/system", "Vex System", "Delegates explicit VexBridge MCP tool calls.", ['{"tool":"ping","arguments":{}}']), VexAgentExecutor(system_agent)),
]

HANDLERS: dict[str, Handler] = {
    "coordinator": coordinator_agent,
    "cognition": cognition_agent,
    "memory": memory_agent,
    "verification": verification_agent,
    "phone": phone_agent,
    "renderer": renderer_agent,
    "system": system_agent,
}

async def health(_request):
    return JSONResponse({"ok": True, "service": "VexA2A", "protocol": "1.0", "host": socket.gethostname(), "agents": [p.strip("/") for p, _, _ in AGENTS]})

async def agents_endpoint(_request):
    return JSONResponse({"ok": True, "agents": [{"id": p.strip("/"), "name": c.name, "card": f"{PUBLIC_URL}{p}{AGENT_CARD_WELL_KNOWN_PATH}", "endpoint": f"{PUBLIC_URL}{p}"} for p, c, _ in AGENTS]})

async def local_send(request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid JSON"}, status_code=400)
    agent = str(body.get("agent") or "coordinator").strip().lower()
    if agent not in HANDLERS:
        return JSONResponse({"ok": False, "error": f"unknown agent: {agent}"}, status_code=404)
    message = body.get("message", "")
    text = message if isinstance(message, str) else json.dumps(message, ensure_ascii=False)
    try:
        result = await HANDLERS[agent](text)
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except Exception:
                pass
        return JSONResponse({"ok": True, "agent": agent, "result": result})
    except Exception as exc:
        return JSONResponse({"ok": False, "agent": agent, "error": f"{type(exc).__name__}: {exc}"}, status_code=500)

def build_app() -> Starlette:
    routes = [
        Route("/health", health),
        Route("/agents", agents_endpoint),
        Route("/vex/agents", agents_endpoint),
        Route("/vex/send", local_send, methods=["POST"]),
    ]
    for path, agent_card, executor in AGENTS:
        handler = DefaultRequestHandler(agent_executor=executor, task_store=InMemoryTaskStore(), agent_card=agent_card)
        routes.extend(create_agent_card_routes(agent_card, card_url=f"{path}{AGENT_CARD_WELL_KNOWN_PATH}"))
        routes.extend(create_jsonrpc_routes(handler, rpc_url=path))
    return Starlette(routes=routes)

if __name__ == "__main__":
    uvicorn.run(build_app(), host=HOST, port=PORT, log_level="info")
