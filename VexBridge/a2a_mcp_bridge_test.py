from __future__ import annotations

import asyncio
import json
import os

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL=os.environ.get("VEXBRIDGE_TEST_URL","http://127.0.0.1:8798/mcp")

def value(result):
    structured=getattr(result,"structuredContent",None)
    if isinstance(structured,dict) and "result" in structured:
        return structured["result"]
    text="\n".join(getattr(x,"text","") for x in result.content)
    return json.loads(text)

async def main():
    async with streamablehttp_client(URL) as (read,write,_):
        async with ClientSession(read,write) as s:
            await s.initialize()
            submitted=value(await s.call_tool("a2a_send",{
                "agent":"system",
                "message":json.dumps({"tool":"ping","arguments":{}}),
            }))
            job_id=submitted["jobId"]
            assert submitted["status"]=="submitted"
            state=None
            for _ in range(100):
                await asyncio.sleep(.1)
                state=value(await s.call_tool("a2a_result",{"jobId":job_id}))
                if state.get("status") in {"completed","failed"}:
                    break
            assert state and state["status"]=="completed",state
            payload=state["result"]
            rendered=json.dumps(payload).lower()
            assert "pong" in rendered,rendered
            print("VEX_A2A_MCP_CALLBACK=PASS")

asyncio.run(main())
