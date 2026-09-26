from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import get_message_text, get_stream_response_text, new_text_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill, Role, SendMessageRequest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

VERSION = "0.15.7"
HOST = os.environ.get("VEX_A2A_HOST", "127.0.0.1")
PORT = int(os.environ.get("VEX_A2A_PORT", "8810"))
BASE = os.environ.get("VEX_A2A_BASE", f"http://127.0.0.1:{PORT}").rstrip("/")
MCP_URL = os.environ.get("VEX_A2A_MCP_URL", "http://127.0.0.1:8795/mcp")
OLLAMA_URL = os.environ.get("VEX_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
FAST_MODEL = os.environ.get("VEX_A2A_FAST_MODEL", "vex-qwen35-9b-q6:latest")
DEEP_MODEL = os.environ.get("VEX_A2A_DEEP_MODEL", "vex-bonsai2-27b:latest")
FALLBACK_DEEP_MODEL = os.environ.get("VEX_A2A_DEEP_FALLBACK", "vex-qwen35-a3b-text:latest")
CTX = int(os.environ.get("VEX_A2A_CTX", "8192"))
TOOLS_ROOT = Path(os.environ.get("VEX_TOOLS_ROOT", str(Path.home() / "Documents" / "VexNativeTools")))
PHONE_COMMAND = Path(os.environ.get("VEX_PHONE_COMMAND", str(TOOLS_ROOT / "PhoneRelay" / "VexPhoneCommand.py")))
RENDERER = Path(os.environ.get("VEX_RENDERER", str(Path.home() / "Documents" / "VexAutoRender.py")))

AGENT_NAMES = ("coordinator", "cognition", "memory", "verification", "system", "phone", "renderer")


def _json(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


async def mcp_call(tool: str, arguments: dict[str, Any] | None = None) -> Any:
    async with streamablehttp_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, arguments or {})
            if getattr(result, "isError", False):
                text = "\n".join(getattr(x, "text", "") for x in result.content)
                raise RuntimeError(text or f"MCP tool failed: {tool}")
            structured = getattr(result, "structuredContent", None)
            if structured:
                return structured.get("result", structured) if isinstance(structured, dict) else structured
            texts = [getattr(x, "text", "") for x in result.content if getattr(x, "type", "") == "text"]
            if len(texts) == 1:
                try:
                    return json.loads(texts[0])
                except Exception:
                    return texts[0]
            return texts


async def ollama_models() -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            r.raise_for_status()
            return [str(x.get("name") or x.get("model") or "") for x in r.json().get("models", [])]
    except Exception:
        return []


def choose_model(message: str, requested: str | None, available: list[str]) -> tuple[str, str]:
    if requested and requested in available:
        return requested, "requested"
    deep_words = (
        "deep", "reason", "architecture", "analy", "debug", "code", "plan", "research",
        "compare", "complex", "design", "investigate", "review", "refactor",
    )
    wants_deep = any(x in message.lower() for x in deep_words)
    if wants_deep and DEEP_MODEL in available:
        return DEEP_MODEL, "deep"
    if wants_deep and FALLBACK_DEEP_MODEL in available:
        return FALLBACK_DEEP_MODEL, "deep-fallback"
    if FAST_MODEL in available:
        return FAST_MODEL, "fast"
    if available:
        return available[0], "available-fallback"
    return FAST_MODEL, "configured-fallback"


async def cognition(text: str) -> str:
    payload = _json(text) or {}
    message = str(payload.get("message") or text).strip()
    memory = payload.get("memory")
    requested = str(payload.get("model") or "").strip() or None
    available = await ollama_models()
    model, lane = choose_model(message, requested, available)
    system = (
        "You are VexNative's local cognition specialist. Be direct, concrete, continuity-aware, "
        "and action-first. Never invent tool results or live state. Use supplied memory as context, "
        "not as higher authority than newer verified state."
    )
    if memory:
        system += "\n\nAuxiliary recalled memory:\n" + str(memory)[:12000]
    body = {
        "model": model,
        "stream": False,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": message}],
        "options": {"temperature": 0.6, "num_ctx": CTX},
    }
    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.post(f"{OLLAMA_URL}/api/chat", json=body)
        r.raise_for_status()
        data = r.json()
    answer = str((data.get("message") or {}).get("content") or data.get("response") or "").strip()
    return _dump({"agent": "cognition", "model": model, "lane": lane, "answer": answer})


async def memory(text: str) -> str:
    payload = _json(text) or {}
    action = str(payload.get("action") or "recall").lower()
    if action == "store":
        result = await mcp_call("icm_store", {
            "topic": str(payload.get("topic") or "vex-native:a2a"),
            "content": str(payload.get("content") or ""),
            "importance": str(payload.get("importance") or "medium"),
            "keywords": payload.get("keywords"),
        })
    elif action == "stats":
        result = await mcp_call("icm_stats", {})
    else:
        query = str(payload.get("query") or payload.get("message") or text)
        result = await mcp_call("icm_recall", {
            "query": query,
            "topic": payload.get("topic"),
            "limit": int(payload.get("limit") or 5),
            "keyword": payload.get("keyword"),
            "project": payload.get("project"),
        })
    return _dump({"agent": "memory", "action": action, "result": result})


async def verification(text: str) -> str:
    payload = _json(text) or {}
    gate = str(payload.get("gate_file") or "").strip()
    if gate:
        lint = await mcp_call("unlazy_lint", {"gate_file": gate, "strict": bool(payload.get("strict", True))})
        status = await mcp_call("unlazy_status", {
            "gate_file": gate,
            "root": payload.get("root"),
            "scope": payload.get("scope"),
        })
        return _dump({"agent": "verification", "lint": lint, "status": status})
    return _dump({"agent": "verification", "integration_status": await mcp_call("integration_status", {})})


async def system_agent(text: str) -> str:
    payload = _json(text)
    if payload and payload.get("tool"):
        tool = str(payload["tool"])
        if tool.startswith("a2a_"):
            raise ValueError("recursive a2a tool invocation is not allowed")
        result = await mcp_call(tool, payload.get("arguments") or {})
        return _dump({"agent": "system", "tool": tool, "result": result})
    return _dump({
        "agent": "system",
        "ping": await mcp_call("ping", {}),
        "integrations": await mcp_call("integration_status", {}),
    })


def _python_command() -> list[str] | None:
    exe = shutil.which("python") or shutil.which("python3")
    if exe:
        return [exe]
    py = shutil.which("py")
    if py:
        return [py, "-3"]
    return None


async def phone(text: str) -> str:
    payload = _json(text) or {}
    command = str(payload.get("command") or payload.get("message") or text).strip()
    py = _python_command()
    if not PHONE_COMMAND.exists() or not py:
        return _dump({"agent": "phone", "ok": False, "error": "phone command helper unavailable on this node"})
    argv = py + [str(PHONE_COMMAND), command, "--source", "vex-a2a", "--wait", str(int(payload.get("wait") or 120))]
    proc = await asyncio.to_thread(
        subprocess.run, argv, capture_output=True, text=True, timeout=int(payload.get("timeout") or 150),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return _dump({"agent": "phone", "ok": proc.returncode == 0, "returncode": proc.returncode,
                  "output": ((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")).strip()[-12000:]})


async def renderer(text: str) -> str:
    payload = _json(text) or {}
    if str(payload.get("action") or "").lower() in {"status", "health"} or not payload.get("prompt"):
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get("http://127.0.0.1:8188/system_stats")
                return _dump({"agent": "renderer", "ok": r.status_code == 200, "status": r.json()})
        except Exception as exc:
            return _dump({"agent": "renderer", "ok": False, "error": f"{type(exc).__name__}: {exc}"})
    py = _python_command()
    if not RENDERER.exists() or not py:
        return _dump({"agent": "renderer", "ok": False, "error": "renderer wrapper unavailable on this node"})
    argv = py + [str(RENDERER), str(payload["prompt"]), "--mode", str(payload.get("mode") or "normal"),
                 "--orientation", str(payload.get("orientation") or "portrait")]
    if payload.get("seed"):
        argv += ["--seed", str(int(payload["seed"]))]
    proc = await asyncio.to_thread(
        subprocess.run, argv, capture_output=True, text=True, timeout=int(payload.get("timeout") or 3600),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    output = ((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")).strip()
    return _dump({"agent": "renderer", "ok": proc.returncode == 0, "returncode": proc.returncode, "output": output[-12000:]})


async def call_a2a(agent: str, message: str) -> str:
    if agent not in AGENT_NAMES or agent == "coordinator":
        raise ValueError(f"unsupported specialist: {agent}")
    url = f"{BASE}/{agent}/"
    async with httpx.AsyncClient(timeout=10) as http_client:
        card = await A2ACardResolver(httpx_client=http_client, base_url=url).get_agent_card()
    client = await create_client(agent=card, client_config=ClientConfig(streaming=False))
    try:
        request = SendMessageRequest(message=new_text_message(message, role=Role.ROLE_USER))
        answers: list[str] = []
        async for event in client.send_message(request):
            try:
                value = get_stream_response_text(event)
            except Exception:
                try:
                    value = get_message_text(event)
                except Exception:
                    value = ""
            if value:
                answers.append(value)
        if not answers:
            raise RuntimeError(f"{agent} returned no text message")
        return answers[-1]
    finally:
        await client.close()


def route_for(message: str) -> str:
    low = message.lower()
    if any(x in low for x in ("iphone", "phone", "open youtube", "tap ", "swipe ", "devicekit")):
        return "phone"
    if any(x in low for x in ("render", "comfy", "image generation", "generate an image", "picture of")):
        return "renderer"
    if any(x in low for x in ("unlazy", "gate", "verify", "verification", "test status", "acceptance")):
        return "verification"
    if any(x in low for x in ("remember", "recall", "memory", "what did i", "continuity")):
        return "memory"
    if any(x in low for x in ("file", "process", "windows", "pc ", "computer", "directory", "powershell")):
        return "system"
    return "cognition"


async def coordinator(text: str) -> str:
    payload = _json(text) or {}
    message = str(payload.get("message") or text).strip()
    target = str(payload.get("agent") or route_for(message)).strip().lower()
    if target != "cognition":
        forwarded = dict(payload)
        forwarded.pop("agent", None)
        if not forwarded:
            forwarded = {"message": message}
        return await call_a2a(target, _dump(forwarded))
    remembered = await call_a2a("memory", _dump({"action": "recall", "query": message, "limit": 5}))
    deep = any(x in message.lower() for x in ("deep", "reason", "architecture", "analy", "debug", "code", "plan", "research", "compare", "complex"))
    cognition_payload = {
        "message": message,
        "memory": remembered,
        "model": DEEP_MODEL if deep else None,
    }
    return await call_a2a("cognition", _dump(cognition_payload))


HANDLERS = {
    "coordinator": coordinator,
    "cognition": cognition,
    "memory": memory,
    "verification": verification,
    "system": system_agent,
    "phone": phone,
    "renderer": renderer,
}


@dataclass(frozen=True)
class Spec:
    name: str
    title: str
    description: str
    tags: list[str]


SPECS = {
    "coordinator": Spec("coordinator", "Vex Coordinator", "Routes work across Vex specialist agents using A2A.", ["orchestration", "routing", "vex"]),
    "cognition": Spec("cognition", "Vex Cognition", "Local fast/deep model reasoning with automatic brain routing.", ["reasoning", "ollama", "bonsai"]),
    "memory": Spec("memory", "Vex Memory", "ICM-backed auxiliary recall and memory storage.", ["memory", "icm", "recall"]),
    "verification": Spec("verification", "Vex Verification", "Unlazy acceptance, lint, and integration verification.", ["verification", "unlazy", "gates"]),
    "system": Spec("system", "Vex System", "Authorized MCP-backed PC and tool execution.", ["mcp", "windows", "tools"]),
    "phone": Spec("phone", "Vex Phone", "VexNative iPhone command and DeviceKit-facing orchestration.", ["iphone", "vexnative", "phone"]),
    "renderer": Spec("renderer", "Vex Renderer", "ComfyUI/VexAutoRender status and render execution.", ["comfyui", "render", "image"]),
}


class VexExecutor(AgentExecutor):
    def __init__(self, name: str):
        self.name = name

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        query = get_message_text(context.message) if context.message else ""
        result = await HANDLERS[self.name](query or "")
        await event_queue.enqueue_event(new_text_message(result, role=Role.ROLE_AGENT))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("This Vex A2A agent does not expose cancellable long-running tasks yet.")


def build_agent(name: str) -> Starlette:
    spec = SPECS[name]
    skill = AgentSkill(
        id=f"vex_{name}",
        name=spec.title,
        description=spec.description,
        input_modes=["text/plain", "application/json"],
        output_modes=["text/plain", "application/json"],
        tags=spec.tags,
        examples=[f'{{"agent":"{name}","message":"status"}}'],
    )
    card = AgentCard(
        name=spec.title,
        description=spec.description,
        version=VERSION,
        default_input_modes=["text/plain", "application/json"],
        default_output_modes=["text/plain", "application/json"],
        capabilities=AgentCapabilities(streaming=False),
        supported_interfaces=[
            AgentInterface(protocol_binding="JSONRPC", url=f"{BASE}/{name}/", protocol_version="1.0")
        ],
        skills=[skill],
    )
    handler = DefaultRequestHandler(
        agent_executor=VexExecutor(name),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    routes = []
    routes.extend(create_agent_card_routes(card))
    routes.extend(create_jsonrpc_routes(handler, "/"))
    return Starlette(routes=routes)


async def health(request):
    models = await ollama_models()
    return JSONResponse({
        "ok": True,
        "version": VERSION,
        "host": socket.gethostname(),
        "protocol": "A2A/1.0",
        "mcp": MCP_URL,
        "agents": list(AGENT_NAMES),
        "fast_model": FAST_MODEL,
        "deep_model": DEEP_MODEL,
        "deep_available": DEEP_MODEL in models,
    })


async def agents(request):
    return JSONResponse({
        "agents": [{"id": n, "name": SPECS[n].title, "url": f"{BASE}/{n}"} for n in AGENT_NAMES]
    })


def build_app() -> Starlette:
    routes = [Route("/health", health), Route("/agents", agents)]
    for name in AGENT_NAMES:
        routes.append(Mount(f"/{name}", app=build_agent(name)))
    return Starlette(routes=routes)


if __name__ == "__main__":
    uvicorn.run(build_app(), host=HOST, port=PORT, log_level="info")
