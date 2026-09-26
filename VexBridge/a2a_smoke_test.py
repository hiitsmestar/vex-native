from __future__ import annotations

import asyncio
import json
import os

import httpx
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import new_text_message
from a2a.types import Role, SendMessageRequest

BASE=os.environ.get("VEX_A2A_TEST_URL","http://127.0.0.1:8800").rstrip("/")

def artifact_text(value):
    out=[]
    if isinstance(value,dict):
        for artifact in value.get("artifacts") or []:
            for part in artifact.get("parts") or []:
                if isinstance(part,dict) and isinstance(part.get("text"),str):
                    out.append(part["text"])
        if not out:
            for item in value.values():
                out.extend(artifact_text(item))
    elif isinstance(value,list):
        for item in value:
            out.extend(artifact_text(item))
    return out

async def send(base_url,payload):
    async with httpx.AsyncClient(timeout=30.0) as http:
        card=await A2ACardResolver(httpx_client=http,base_url=base_url).get_agent_card()
    client=await create_client(agent=card,client_config=ClientConfig(streaming=False))
    try:
        req=SendMessageRequest(message=new_text_message(json.dumps(payload),role=Role.ROLE_USER))
        chunks=[]
        async for chunk in client.send_message(req):
            chunks.append(chunk.model_dump(mode="json") if hasattr(chunk,"model_dump") else {"value":str(chunk)})
        texts=artifact_text(chunks)
        return "\n".join(texts) if texts else json.dumps(chunks)
    finally:
        await client.close()

async def main():
    async with httpx.AsyncClient(timeout=10.0) as http:
        health=(await http.get(BASE+"/health")).json()
        registry=(await http.get(BASE+"/registry")).json()
        assert health["ok"] is True
        assert health["protocol"]=="A2A 1.0"
        assert {"coordinator","cognition","memory","verification","system","node"} <= set(registry["local"])
        for suffix in ["","/cognition","/memory","/verification","/system","/node"]:
            card=await A2ACardResolver(httpx_client=http,base_url=BASE+suffix).get_agent_card()
            assert card.name.startswith("Vex ")

    brain=await send(BASE+"/cognition",{"action":"status"})
    assert "policy" in brain.lower(),brain
    direct=await send(BASE+"/system",{"tool":"ping","arguments":{}})
    assert "pong" in direct.lower(),direct
    delegated=await send(BASE,{"agent":"system","payload":{"tool":"ping","arguments":{}}})
    assert "pong" in delegated.lower(),delegated
    status=await send(BASE,{"agent":"status"})
    assert "integrations" in status.lower(),status
    print("VEX_A2A_SMOKE=PASS")

asyncio.run(main())
