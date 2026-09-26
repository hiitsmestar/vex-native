import asyncio, json, pathlib, time
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

ROOT = r"C:\Users\monte\Documents\VexNativeTools\VexBridgeTests"

async def main():
    async with streamablehttp_client("http://127.0.0.1:8795/mcp") as (read, write, _):
        async with ClientSession(read, write) as s:
            await s.initialize()
            async def call(name, args):
                r = await s.call_tool(name, args)
                if getattr(r, "isError", False):
                    raise RuntimeError(name + ": " + "\n".join(x.text for x in r.content))
                return "\n".join(x.text for x in r.content)
            await call("create_directory", {"path": ROOT})
            p = ROOT + r"\alpha.txt"
            await call("write_file", {"path": p, "content": "alpha\nbeta\n", "mode": "rewrite"})
            assert "alpha" in await call("read_file", {"path": p})
            assert "2" in await call("get_file_info", {"path": p})
            await call("edit_block", {"file_path": p, "old_string": "beta", "new_string": "gamma", "expected_replacements": 1})
            assert "gamma" in await call("read_file", {"path": p})
            moved = ROOT + r"\moved.txt"
            await call("move_file", {"source": p, "destination": moved})
            assert "moved.txt" in await call("list_directory", {"path": ROOT, "depth": 1})
            sid = json.loads(await call("start_search", {"path": ROOT, "pattern": "gamma", "searchType": "content", "literalSearch": True}))["sessionId"]
            await asyncio.sleep(.3)
            assert "moved.txt" in await call("get_more_search_results", {"sessionId": sid, "length": 20})
            xlsx = ROOT + r"\test.xlsx"
            await call("write_file", {"path": xlsx, "content": '[["Name","N"],["Star",42]]'})
            assert "Star" in await call("read_file", {"path": xlsx, "sheet": "0", "range": "A1:B2"})
            docx = ROOT + r"\test.docx"
            await call("write_file", {"path": docx, "content": "# VexBridge\nField proof"})
            assert "Field proof" in await call("read_file", {"path": docx})
            pdf = ROOT + r"\test.pdf"
            await call("write_pdf", {"path": pdf, "content": "# VexBridge\n\nField proof"})
            assert "Field proof" in await call("read_file", {"path": pdf})
            proc = json.loads(await call("start_process", {"timeout_ms": 1000, "command": "python -i"}))
            pid = proc["pid"]
            assert "42" in await call("interact_with_process", {"pid": pid, "input": "print(6*7)", "timeout_ms": 3000})
            await call("force_terminate", {"pid": pid})
            await call("list_processes", {})
            await call("list_sessions", {})
            print("VEXBRIDGE_FIELD_TEST=PASS")

asyncio.run(main())