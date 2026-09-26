import asyncio
import os
from pathlib import Path
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = os.environ.get("VEXBRIDGE_URL", "http://127.0.0.1:8795/mcp")
ROOT = Path(os.environ.get("VEXBRIDGE_TEST_ROOT", str(Path.home() / "VexBridgeSmoke")))

async def main():
    async with streamablehttp_client(URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            info = await session.initialize()
            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            required = {"ping", "read_file", "write_file", "start_process", "list_processes"}
            missing = required - names
            if missing:
                raise RuntimeError("missing tools: " + ",".join(sorted(missing)))
            await session.call_tool("create_directory", {"path": str(ROOT)})
            test_file = ROOT / "smoke.txt"
            await session.call_tool("write_file", {"path": str(test_file), "content": "vexbridge-smoke"})
            result = await session.call_tool("read_file", {"path": str(test_file)})
            text = "\n".join(getattr(x, "text", "") for x in result.content)
            if "vexbridge-smoke" not in text:
                raise RuntimeError("read/write smoke failed")
            print("SERVER", info.serverInfo.name, info.serverInfo.version)
            print("TOOL_COUNT", len(names))
            print("VEXBRIDGE_PACKAGED_SMOKE=PASS")

asyncio.run(main())
