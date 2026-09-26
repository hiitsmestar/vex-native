from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx
import uvicorn
from a2a.client import A2ACardResolver, ClientConfig, create_client
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
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    Role,
    SendMessageRequest,
    TaskState,
)
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

try:
    from .brain_router import chat as brain_chat, status as brain_status
except ImportError:
    from brain_router import chat as brain_chat, status as brain_status

HOST = os.environ.get("VEX_A2A_HOST", "127.0.0.1")
PORT = int(os.environ.get("VEX_A2A_PORT", "8800"))
BASE_URL = os.environ.get("VEX_A2A_BASE_URL", f"http://{HOST}:{PORT}").rstrip("/")
MCP_URL = os.environ.get("VEXBRIDGE_MCP_URL", "http://127.0.0.1:8795/mcp")
APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "VexA2A"
CONFIG_PATH = APP_DIR / "config.json"
APP_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_CONFIG: dict[str, Any] = {
    "schema": "vex-a2a-v1",
    "nodeName": os.environ.get("COMPUTERNAME") or socket.gethostname(),
    "peers": {},
}


def load_config() -> dict[str, Any]:
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
        return {**DEFAULT_CONFIG, **raw}
    except Exception:
        return dict(DEFAULT_CONFIG)


def parse_payload(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        if isinstance(value, dict):
            return value
    except Exception:
        pass
    return {"text": raw}


async def call_mcp(tool: str, arguments: dict[str, Any] | None = None) -> Any:
    async with streamablehttp_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            names = {item.name for item in listed.tools}
            if tool not in names:
                raise ValueError(f"unknown VexBridge tool: {tool}")
            result = await session.call_tool(tool, arguments or {})
            if getattr(result, "isError", False):
                message = "\n".join(getattr(item, "text", "") for item in result.content)
                raise RuntimeError(message or f"VexBridge tool failed: {tool}")
            structured = getattr(result, "structuredContent", None)
            if structured is not None:
                return structured.get("result", structured) if isinstance(structured, dict) else structured
            texts = [getattr(item, "text", "") for item in result.content if getattr(item, "text", "")]
            if len(texts) == 1:
                try:
                    return json.loads(texts[0])
                except Exception:
                    return texts[0]
            return texts


def relay_client_path() -> Path:
    explicit = os.environ.get("VEXBRIDGE_RELAY_CLIENT", "").strip()
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    candidates.extend(
        [
            local / "VexBridgeMCP" / "Client" / "VexBridgeRelayClient.exe",
            Path.home() / "Documents" / "VexNativeTools" / "VexBridgeRelayClient.py",
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("VexBridge relay client was not found")


async def call_remote(peer: str, tool: str, arguments: dict[str, Any]) -> Any:
    cfg = load_config()
    peers = cfg.get("peers") or {}
    info = peers.get(peer)
    if not isinstance(info, dict) or not info.get("node"):
        raise ValueError(f"unknown A2A peer alias: {peer}")
    node = str(info["node"])
    client = relay_client_path()
    fd, arg_path = tempfile.mkstemp(prefix="vex-a2a-", suffix=".json", dir=str(APP_DIR))
    os.close(fd)
    path = Path(arg_path)
    path.write_text(json.dumps(arguments, ensure_ascii=False), encoding="utf-8")
    try:
        command = [str(client)]
        if client.suffix.lower() == ".py":
            command = [os.environ.get("PYTHON", "python"), str(client)]
        command += [
            "--node",
            node,
            "--tool",
            tool,
            "--arguments",
            "@" + str(path),
            "--timeout",
            "180",
        ]
        proc = await asyncio.to_thread(
            subprocess.run,
            command,
            text=True,
            capture_output=True,
            timeout=210,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "relay call failed")[-4000:])
        return json.loads(proc.stdout)
    finally:
        path.unlink(missing_ok=True)


def _artifact_text(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        artifacts = value.get("artifacts")
        if isinstance(artifacts, list):
            for artifact in artifacts:
                if not isinstance(artifact, dict):
                    continue
                parts = artifact.get("parts")
                if isinstance(parts, list):
                    for part in parts:
                        if isinstance(part, dict) and isinstance(part.get("text"), str):
                            found.append(part["text"])
        if not found:
            for item in value.values():
                found.extend(_artifact_text(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_artifact_text(item))
    return found



def _stream_response_text(chunk: Any) -> str:
    found: list[str] = []
    try:
        if chunk.HasField("message"):
            found.extend(
                part.text for part in chunk.message.parts
                if getattr(part, "text", "")
            )
        if chunk.HasField("artifact_update"):
            artifact = chunk.artifact_update.artifact
            found.extend(
                part.text for part in artifact.parts
                if getattr(part, "text", "")
            )
        if chunk.HasField("task"):
            for artifact in chunk.task.artifacts:
                found.extend(
                    part.text for part in artifact.parts
                    if getattr(part, "text", "")
                )
        if chunk.HasField("status_update") and chunk.status_update.status.HasField("message"):
            found.extend(
                part.text for part in chunk.status_update.status.message.parts
                if getattr(part, "text", "")
            )
    except Exception:
        pass
    return "\n".join(found)

async def send_a2a(base_url: str, payload: dict[str, Any] | str) -> str:
    timeout = httpx.Timeout(240.0, connect=15.0)
    async with httpx.AsyncClient(timeout=timeout) as http:
        card = await A2ACardResolver(httpx_client=http, base_url=base_url).get_agent_card()
        a2a_client = await create_client(
            agent=card,
            client_config=ClientConfig(streaming=False, httpx_client=http),
        )
        try:
            text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
            request = SendMessageRequest(message=new_text_message(text, role=Role.ROLE_USER))
            texts: list[str] = []
            events: list[str] = []
            async for chunk in a2a_client.send_message(request):
                extracted = _stream_response_text(chunk)
                if extracted:
                    texts.append(extracted)
                events.append(str(chunk))
            return "\n".join(texts) if texts else json.dumps(events, ensure_ascii=False)
        finally:
            await a2a_client.close()

async def memory_agent(text: str) -> str:
    payload = parse_payload(text)
    action = str(payload.get("action") or "recall").lower()
    if action == "stats":
        result = await call_mcp("icm_stats", {})
    elif action == "store":
        result = await call_mcp(
            "icm_store",
            {
                "topic": str(payload.get("topic") or "vex-a2a"),
                "content": str(payload.get("content") or payload.get("text") or ""),
                "importance": str(payload.get("importance") or "medium"),
                "keywords": payload.get("keywords"),
            },
        )
    else:
        result = await call_mcp(
            "icm_recall",
            {
                "query": str(payload.get("query") or payload.get("text") or ""),
                "topic": payload.get("topic"),
                "limit": int(payload.get("limit") or 5),
                "keyword": payload.get("keyword"),
                "project": payload.get("project"),
            },
        )
    return json.dumps(result, indent=2, ensure_ascii=False, default=str)


async def verification_agent(text: str) -> str:
    payload = parse_payload(text)
    action = str(payload.get("action") or "status").lower()
    gate_file = str(payload.get("gate_file") or payload.get("text") or "")
    if not gate_file:
        raise ValueError("gate_file is required")
    if action == "lint":
        result = await call_mcp(
            "unlazy_lint",
            {"gate_file": gate_file, "strict": bool(payload.get("strict", False))},
        )
    else:
        result = await call_mcp(
            "unlazy_status",
            {
                "gate_file": gate_file,
                "root": payload.get("root"),
                "scope": payload.get("scope"),
            },
        )
    return json.dumps(result, indent=2, ensure_ascii=False, default=str)


async def system_agent(text: str) -> str:
    payload = parse_payload(text)
    tool = str(payload.get("tool") or payload.get("action") or payload.get("text") or "ping")
    if tool in {"shutdown", "a2a_send"}:
        raise ValueError(f"tool is not exposed through A2A system agent: {tool}")
    arguments = payload.get("arguments") or {}
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be an object")
    result = await call_mcp(tool, arguments)
    return json.dumps(result, indent=2, ensure_ascii=False, default=str)


async def node_agent(text: str) -> str:
    payload = parse_payload(text)
    peer = str(payload.get("peer") or "")
    tool = str(payload.get("tool") or "ping")
    arguments = payload.get("arguments") or {}
    if not peer:
        raise ValueError("peer is required")
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be an object")
    result = await call_remote(peer, tool, arguments)
    return json.dumps(result, indent=2, ensure_ascii=False, default=str)


async def coordinator_agent(text: str) -> str:
    payload = parse_payload(text)
    target = str(payload.get("agent") or "").lower()
    body = payload.get("payload")
    if body is None:
        body = {k: v for k, v in payload.items() if k != "agent"}
    if target in {"cognition", "memory", "verification", "system", "node"}:
        return await send_a2a(f"{BASE_URL}/{target}", body)
    if target in {"status", "health"}:
        result = {
            "node": load_config().get("nodeName"),
            "mcp": await call_mcp("ping", {}),
            "integrations": await call_mcp("integration_status", {}),
            "agents": ["coordinator", "cognition", "memory", "verification", "system", "node"],
            "peers": sorted((load_config().get("peers") or {}).keys()),
        }
        return json.dumps(result, indent=2, ensure_ascii=False, default=str)

    raw = str(payload.get("text") or text or "").strip()
    if raw.lower().startswith("recall "):
        return await send_a2a(f"{BASE_URL}/memory", {"action": "recall", "query": raw[7:]})
    if raw.lower() in {"ping", "status"}:
        return await coordinator_agent(json.dumps({"agent": "status"}))
    if raw:
        return await send_a2a(f"{BASE_URL}/cognition", {"mode": "auto", "prompt": raw})
    return json.dumps(
        {
            "ok": True,
            "message": "Vex A2A coordinator is online.",
            "agents": ["cognition", "memory", "verification", "system", "node", "status"],
        },
        ensure_ascii=False,
    )


Handler = Callable[[str], Awaitable[str]]


class FunctionExecutor(AgentExecutor):
    def __init__(self, handler: Handler):
        self.handler = handler

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.current_task:
            task = context.current_task
        else:
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue=event_queue, task_id=task.id, context_id=task.context_id)
        await updater.update_status(
            state=TaskState.TASK_STATE_WORKING,
            message=new_text_message("Working"),
        )
        query = get_message_text(context.message) or ""
        result = await self.handler(query)
        await updater.add_artifact(parts=[new_text_part(text=result, media_type="text/plain")])
        await updater.update_status(
            state=TaskState.TASK_STATE_COMPLETED,
            message=new_text_message("Completed"),
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("cancel is not supported")


def skill(skill_id: str, name: str, description: str, examples: list[str]) -> AgentSkill:
    return AgentSkill(
        id=skill_id,
        name=name,
        description=description,
        input_modes=["text/plain"],
        output_modes=["text/plain"],
        tags=["vexnative", "a2a", skill_id],
        examples=examples,
    )


def card(name: str, description: str, path: str, skills: list[AgentSkill]) -> AgentCard:
    url = (BASE_URL + path).rstrip("/") + "/"
    return AgentCard(
        name=name,
        description=description,
        version="1.0.0",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(streaming=True),
        supported_interfaces=[
            AgentInterface(protocol_binding="JSONRPC", url=url, protocol_version="1.0")
        ],
        skills=skills,
    )


def agent_app(agent_card: AgentCard, handler: Handler) -> Starlette:
    request_handler = DefaultRequestHandler(
        agent_executor=FunctionExecutor(handler),
        task_store=InMemoryTaskStore(),
        agent_card=agent_card,
    )
    routes = []
    routes.extend(create_agent_card_routes(agent_card))
    routes.extend(create_jsonrpc_routes(request_handler, "/"))
    return Starlette(routes=routes)


cognition_card = card(
    "Vex Cognition Agent",
    "Dual-brain VexNative cognition agent using fast Qwen and deep Bonsai routing.",
    "/cognition",
    [skill("cognition", "Cognition", "Route chat/reasoning work to fast Qwen or deep Bonsai.", ['{"mode":"auto","prompt":"Analyze this architecture"}'])],
)
memory_card = card(
    "Vex Memory Agent",
    "ICM-backed VexNative memory and retrieval agent.",
    "/memory",
    [skill("memory", "Memory", "Recall, store, and inspect Vex ICM memory.", ['{"action":"recall","query":"VexBridge"}'])],
)
verification_card = card(
    "Vex Verification Agent",
    "Unlazy-backed completion and acceptance-gate verification agent.",
    "/verification",
    [skill("verification", "Verification", "Inspect or lint Unlazy gate ledgers.", ['{"action":"status","gate_file":"C:\\\\path\\\\GATES.md"}'])],
)
system_card = card(
    "Vex System Agent",
    "VexBridge tool agent for the local authorized Windows node.",
    "/system",
    [skill("system", "System Tools", "Call a VexBridge MCP tool on the local node.", ['{"tool":"ping","arguments":{}}'])],
)
node_card = card(
    "Vex Mesh Agent",
    "Encrypted VexBridge relay agent for configured peer Windows nodes.",
    "/node",
    [skill("node", "Mesh Peer", "Call a VexBridge tool on a configured encrypted-relay peer.", ['{"peer":"ashley","tool":"ping","arguments":{}}'])],
)
coordinator_card = card(
    "Vex Coordinator",
    "A2A coordinator for VexNative memory, verification, Windows control, and encrypted peer delegation.",
    "",
    [
        skill("delegate", "Delegate", "Route work to Vex specialist agents.", ['{"agent":"cognition","payload":{"mode":"auto","prompt":"Plan this task"}}']),
        skill("status", "Status", "Report Vex A2A and integration status.", ['{"agent":"status"}']),
    ],
)

cognition_app = agent_app(cognition_card, cognition_agent)
memory_app = agent_app(memory_card, memory_agent)
verification_app = agent_app(verification_card, verification_agent)
system_app = agent_app(system_card, system_agent)
node_app = agent_app(node_card, node_agent)

coordinator_handler = DefaultRequestHandler(
    agent_executor=FunctionExecutor(coordinator_agent),
    task_store=InMemoryTaskStore(),
    agent_card=coordinator_card,
)
routes = []
routes.extend(create_agent_card_routes(coordinator_card))
routes.extend(create_jsonrpc_routes(coordinator_handler, "/"))
routes.extend(
    [
        Mount("/cognition", app=cognition_app),
        Mount("/memory", app=memory_app),
        Mount("/verification", app=verification_app),
        Mount("/system", app=system_app),
        Mount("/node", app=node_app),
        Route(
            "/health",
            endpoint=lambda request: JSONResponse(
                {
                    "ok": True,
                    "service": "VexA2A",
                    "protocol": "A2A 1.0",
                    "node": load_config().get("nodeName"),
                    "mcp": MCP_URL,
                }
            ),
            methods=["GET"],
        ),
        Route(
            "/registry",
            endpoint=lambda request: JSONResponse(
                {
                    "local": {
                        "coordinator": BASE_URL,
                        "cognition": BASE_URL + "/cognition",
                        "memory": BASE_URL + "/memory",
                        "verification": BASE_URL + "/verification",
                        "system": BASE_URL + "/system",
                        "node": BASE_URL + "/node",
                    },
                    "peers": load_config().get("peers") or {},
                }
            ),
            methods=["GET"],
        ),
    ]
)
app = Starlette(routes=routes)


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
