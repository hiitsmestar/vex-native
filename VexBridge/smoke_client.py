import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main():
    async with streamablehttp_client("http://127.0.0.1:8795/mcp") as (read, write, get_session_id):
        async with ClientSession(read, write) as session:
            info = await session.initialize()
            tools = await session.list_tools()
            print("SERVER", info.serverInfo.name, info.serverInfo.version)
            print("TOOLS", ",".join(sorted(t.name for t in tools.tools)))
            result = await session.call_tool("ping", {})
            print("PING", result.content[0].text)
            result = await session.call_tool("read_file", {"path": r"C:\Users\monte\Documents\VexContinuityVault\Recall\hourly_recall.json"})
            print("READ_OK", "VEXRECALL60" in result.content[0].text)

asyncio.run(main())

[executed on device: monte (ba771288-2aa1-4f30-88d5-2b8b8f2fd961)]