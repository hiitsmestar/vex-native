from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from a2a.helpers import (
    get_message_text,
    new_task_from_user_message,
    new_text_message,
    new_text_part,
)
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
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

BIND_HOST = os.environ.get("VEXA2A_HOST", "127.0.0.1")
PORT = int(os.environ.get("VEXA2A_PORT", "8796"))
PUBLIC_URL = os.environ.get("VEXA2A_PUBLIC_URL", f"http://127.0.0.1:{PORT}")
MCP_URL = os.environ.get("VEXBRIDGE_MCP_URL", "http://127.0.0.1:8795/mcp")
TOOLS_ROOT = Path(
    os.environ.get(
        "VEX_TOOLS_ROOT",
        str(Path.home() / "Documents" / "VexNativeTools"),
    )
)
PHONE_COMMAND = TOOLS_ROOT / "PhoneRelay" / "VexPhoneCommand.py"
AGY = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "agy" / "bin" / "agy.exe"

Handler = Callable[[str], Awaitable[dict[str, Any] | list[Any] | str]]

AGENT_SPECS: dict[str, dict[str, Any]] = {
    "coordinator": {
        "name": "Vex Coordinator",
        "description": "Routes work across VexNative specialist agents.",
        "skill": "coordinate",
        "skill_name": "Coordinate Vex agents",
        "tags": ["vexnative", "coordination", "routing"],
        "examples": ["list agents", '{"agent":"memory","message":"recall VexBridge"}'],
    },
    "memory": {
        "name": "Vex Memory",
        "description": "ICM-backed auxiliary memory retrieval and storage.",
        "skill": "memory",
        "skill_name": "Recall and store Vex memory",
        "tags": ["vexnative", "icm", "memory"],
        "examples": ['{"action":"recall","query":"VexBridge"}', '{"action":"stats"}'],
    },
    "verification": {
        "name": "Vex Verification",
        "description": "Unlazy acceptance-ledger status and lint verification.",
        "skill": "verification",
        "skill_name": "Verify acceptance gates",
        "tags": ["vexnative", "unlazy", "verification"],
        "examples": ['{"action":"status","gate_file":"C:\\\\work\\\\GATES.md"}'],
    },
    "renderer": {
        "name": "Vex Renderer",
        "description": "ComfyUI renderer health and queue specialist.",
        "skill": "renderer",
        "skill_name": "Inspect renderer state",
        "tags": ["vexnative", "comfyui", "renderer"],
        "examples": ["status", "queue"],
    },
    "phone": {
        "name": "Vex Phone",
        "description": "Dispatches authorized VexNative iPhone commands.",
        "skill": "phone",
        "skill_name": "Control the VexNative phone endpoint",
        "tags": ["vexnative", "iphone", "phone"],
        "examples": ['{"action":"status"}', '{"action":"command","command":"open YouTube on my phone"}'],
    },
    "coding": {
        "name": "Vex Coding",
        "description": "Coding-worker discovery and explicit VexBridge process dispatch.",
        "skill": "coding",
        "skill_name": "Run coding and process work",
        "tags": ["vexnative", "coding", "antigravity"],
        "examples": ['{"action":"status"}', '{"action":"process","command":"python -V"}'],
    },
}


def parse_request(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {}
    if text.startswith("{"):
        try:
            value = json.loads(text)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass
    return {"text": text}


async def mcp_call(tool: str, arguments: dict[str, Any]) -> Any:
    async with streamablehttp_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, arguments)
            if getattr(result, "isError", False):
                raise RuntimeError(
                    "\n".join(getattr(item, "text", "") for item in result.content)
                )
            structured = getattr(result, "structuredContent", None)
            if structured:
                return structured.get("result", structured)
            text = "\n".join(
                getattr(item, "text", "") for item in result.content
            ).strip()
            if not text:
                return None
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text


async def memory_handler(text: str) -> Any:
    req = parse_request(text)
    action = str(req.get("action") or ("recall" if req.get("text") else "stats")).lower()
    if action == "stats":
        return await mcp_call("icm_stats", {})
    if action == "store":
        content = str(req.get("content") or "")
        topic = str(req.get("topic") or "vex-native:a2a")
        if not content:
            return {"ok": False, "error": "content is required"}
        return await mcp_call(
            "icm_store",
            {
                "topic": topic,
                "content": content,
                "importance": str(req.get("importance") or "medium"),
                "keywords": req.get("keywords"),
            },
        )
    query = str(req.get("query") or req.get("text") or "")
    if not query:
        return {"ok": False, "error": "query is required"}
    return await mcp_call(
        "icm_recall",
        {
            "query": query,
            "topic": req.get("topic"),
            "limit": int(req.get("limit") or 5),
            "keyword": req.get("keyword"),
            "project": req.get("project"),
        },
    )


async def verification_handler(text: str) -> Any:
    req = parse_request(text)
    action = str(req.get("action") or "status").lower()
    gate_file = str(req.get("gate_file") or req.get("gateFile") or "")
    if not gate_file:
        return {
            "ok": False,
            "error": "gate_file is required",
            "actions": ["status", "lint"],
        }
    if action == "lint":
        return await mcp_call(
            "unlazy_lint",
            {"gate_file": gate_file, "strict": bool(req.get("strict", True))},
        )
    return await mcp_call(
        "unlazy_status",
        {
            "gate_file": gate_file,
            "root": req.get("root"),
            "scope": req.get("scope"),
        },
    )


async def renderer_handler(text: str) -> Any:
    req = parse_request(text)
    action = str(req.get("action") or req.get("text") or "status").lower()
    endpoint = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188")
    path = "/queue" if "queue" in action else "/system_stats"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(endpoint + path)
            response.raise_for_status()
            data = response.json()
        return {"ok": True, "endpoint": endpoint, "action": action, "data": data}
    except Exception as exc:
        return {
            "ok": False,
            "endpoint": endpoint,
            "action": action,
            "error": f"{type(exc).__name__}: {exc}",
        }


async def phone_handler(text: str) -> Any:
    req = parse_request(text)
    action = str(req.get("action") or "command").lower()
    if action == "status" or not req:
        return {
            "ok": PHONE_COMMAND.exists(),
            "commandHelper": str(PHONE_COMMAND),
            "available": PHONE_COMMAND.exists(),
        }
    command = str(req.get("command") or req.get("text") or "")
    if not command:
        return {"ok": False, "error": "command is required"}
    if not PHONE_COMMAND.exists():
        return {"ok": False, "error": f"phone helper missing: {PHONE_COMMAND}"}

    def run() -> dict[str, Any]:
        proc = subprocess.run(
            [
                sys.executable,
                str(PHONE_COMMAND),
                command,
                "--source",
                "vexa2a",
                "--wait",
                str(max(5, min(int(req.get("wait") or 120), 600))),
            ],
            text=True,
            capture_output=True,
            timeout=max(10, min(int(req.get("wait") or 120) + 15, 615)),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        output = ((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")).strip()
        return {"ok": proc.returncode == 0, "returncode": proc.returncode, "output": output[-12000:]}

    return await asyncio.to_thread(run)


async def coding_handler(text: str) -> Any:
    req = parse_request(text)
    action = str(req.get("action") or "status").lower()
    if action == "status":
        return {
            "ok": True,
            "antigravity": {"path": str(AGY), "available": AGY.exists()},
            "python": sys.version.split()[0],
            "vexbridge": MCP_URL,
        }
    if action == "process":
        command = str(req.get("command") or "")
        if not command:
            return {"ok": False, "error": "command is required"}
        return await mcp_call(
            "start_process",
            {
                "timeout_ms": int(req.get("timeout_ms") or 5000),
                "command": command,
                "shell": req.get("shell"),
            },
        )
    return {"ok": False, "error": f"unsupported coding action: {action}"}


def route_text(text: str) -> str:
    lower = text.lower()
    if any(word in lower for word in ("remember", "recall", "memory", "icm")):
        return "memory"
    if any(word in lower for word in ("verify", "gate", "unlazy", "acceptance", "lint")):
        return "verification"
    if any(word in lower for word in ("render", "image", "comfy", "comfyui")):
        return "renderer"
    if any(word in lower for word in ("iphone", "phone", "ios")):
        return "phone"
    if any(word in lower for word in ("code", "coding", "antigravity", "agy", "process")):
        return "coding"
    return "coordinator"


async def coordinator_handler(text: str) -> Any:
    req = parse_request(text)
    requested = str(req.get("agent") or "").lower().strip()
    message = req.get("message")
    if requested:
        if requested == "coordinator":
            return {"ok": False, "error": "coordinator cannot dispatch to itself"}
        if requested not in HANDLERS:
            return {"ok": False, "error": f"unknown agent: {requested}", "agents": sorted(HANDLERS)}
        payload = message if isinstance(message, str) else json.dumps(message if message is not None else req)
        return {"agent": requested, "result": await HANDLERS[requested](payload)}
    raw = str(req.get("text") or "")
    if raw.lower().strip() in {"agents", "list agents", "status", "help", ""}:
        return {
            "ok": True,
            "protocol": "A2A 1.0",
            "agents": sorted(AGENT_SPECS),
            "bind": f"{BIND_HOST}:{PORT}",
        }
    target = route_text(raw)
    if target == "coordinator":
        return {
            "ok": True,
            "agent": "coordinator",
            "message": "No specialist matched. Send JSON with agent + message for explicit routing.",
            "agents": sorted(HANDLERS),
        }
    return {"agent": target, "result": await HANDLERS[target](raw)}


HANDLERS: dict[str, Handler] = {
    "memory": memory_handler,
    "verification": verification_handler,
    "renderer": renderer_handler,
    "phone": phone_handler,
    "coding": coding_handler,
}
HANDLERS["coordinator"] = coordinator_handler


class VexAgentExecutor(AgentExecutor):
    def __init__(self, agent_id: str, handler: Handler) -> None:
        self.agent_id = agent_id
        self.handler = handler

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.current_task:
            task = context.current_task
        else:
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(
            event_queue=event_queue,
            task_id=task.id,
            context_id=task.context_id,
        )
        await updater.update_status(
            state=TaskState.TASK_STATE_WORKING,
            message=new_text_message(f"{self.agent_id} working"),
        )
        query = get_message_text(context.message) or ""
        try:
            result = await self.handler(query)
            rendered = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
            await updater.add_artifact(
                parts=[new_text_part(text=rendered, media_type="application/json" if not isinstance(result, str) else "text/plain")]
            )
            await updater.update_status(
                state=TaskState.TASK_STATE_COMPLETED,
                message=new_text_message("Done"),
            )
        except Exception as exc:
            await updater.add_artifact(
                parts=[new_text_part(text=json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), media_type="application/json")]
            )
            await updater.update_status(
                state=TaskState.TASK_STATE_FAILED,
                message=new_text_message("Failed"),
            )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("Cancel is not supported")


def build_card(agent_id: str) -> AgentCard:
    spec = AGENT_SPECS[agent_id]
    path = f"/{agent_id}"
    return AgentCard(
        name=spec["name"],
        description=spec["description"],
        version="1.0.0",
        default_input_modes=["text/plain", "application/json"],
        default_output_modes=["text/plain", "application/json"],
        capabilities=AgentCapabilities(streaming=False),
        supported_interfaces=[
            AgentInterface(
                protocol_binding="JSONRPC",
                url=f"{PUBLIC_URL}{path}",
                protocol_version="1.0",
            )
        ],
        skills=[
            AgentSkill(
                id=spec["skill"],
                name=spec["skill_name"],
                description=spec["description"],
                input_modes=["text/plain", "application/json"],
                output_modes=["text/plain", "application/json"],
                tags=spec["tags"],
                examples=spec["examples"],
            )
        ],
    )


CARDS = {agent_id: build_card(agent_id) for agent_id in AGENT_SPECS}


async def health(_: Request) -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "service": "VexA2A",
            "protocol": "1.0",
            "host": BIND_HOST,
            "port": PORT,
            "agents": sorted(CARDS),
            "time": time.time(),
        }
    )


async def list_agents(_: Request) -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "agents": [
                {
                    "id": agent_id,
                    "name": card.name,
                    "description": card.description,
                    "card": f"{PUBLIC_URL}/{agent_id}{AGENT_CARD_WELL_KNOWN_PATH}",
                    "endpoint": f"{PUBLIC_URL}/{agent_id}",
                }
                for agent_id, card in CARDS.items()
            ],
        }
    )


async def local_send(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid JSON"}, status_code=400)
    agent = str(body.get("agent") or "coordinator").lower()
    if agent not in HANDLERS:
        return JSONResponse({"ok": False, "error": f"unknown agent: {agent}"}, status_code=404)
    message = body.get("message", "")
    text = message if isinstance(message, str) else json.dumps(message, ensure_ascii=False)
    try:
        result = await HANDLERS[agent](text)
        return JSONResponse({"ok": True, "agent": agent, "result": result})
    except Exception as exc:
        return JSONResponse(
            {"ok": False, "agent": agent, "error": f"{type(exc).__name__}: {exc}"},
            status_code=500,
        )


def build_app() -> Starlette:
    routes = [
        Route("/health", health, methods=["GET"]),
        Route("/vex/agents", list_agents, methods=["GET"]),
        Route("/vex/send", local_send, methods=["POST"]),
    ]
    for agent_id, card in CARDS.items():
        path = f"/{agent_id}"
        handler = DefaultRequestHandler(
            agent_executor=VexAgentExecutor(agent_id, HANDLERS[agent_id]),
            task_store=InMemoryTaskStore(),
            agent_card=card,
        )
        routes.extend(
            create_agent_card_routes(
                card,
                card_url=f"{path}{AGENT_CARD_WELL_KNOWN_PATH}",
            )
        )
        routes.extend(create_jsonrpc_routes(handler, rpc_url=path))
    return Starlette(routes=routes)


if __name__ == "__main__":
    print(f"VexA2A serving {len(CARDS)} A2A 1.0 agents on {BIND_HOST}:{PORT}")
    uvicorn.run(build_app(), host=BIND_HOST, port=PORT, log_level="info")
