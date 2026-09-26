import asyncio, json, pathlib, time
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

ROOT = r"C:\Users\monte\Documents\VexBridgeParity"

async def main():
    async with streamablehttp_client("http://127.0.0.1:8795/mcp") as (read, write, _):
        async with ClientSession(read, write) as s:
            await s.initialize()
            tools = await s.list_tools()
            names = {t.name for t in tools.tools}
            expected = {
                "ping","list_devices","who_am_i","get_prompts","give_feedback_to_desktop_commander",
                "get_config","set_config_value","read_file","read_multiple_files","write_file","write_pdf",
                "create_directory","list_directory","move_file","start_search","get_more_search_results",
                "stop_search","list_searches","get_file_info","edit_block","start_process","read_process_output",
                "interact_with_process","force_terminate","list_sessions","list_processes","kill_process",
                "get_usage_stats","get_recent_tool_calls","shutdown"
            }
            missing = sorted(expected - names)
            if missing:
                raise RuntimeError("missing tools: " + ",".join(missing))

            async def call(name, args):
                r = await s.call_tool(name, args)
                if getattr(r, "isError", False):
                    raise RuntimeError(name + ": " + "\n".join(getattr(x, "text", "") for x in r.content))
                return "\n".join(getattr(x, "text", "") for x in r.content)

            assert "pong" in (await call("ping", {})).lower()
            assert "device_name" in await call("list_devices", {})
            assert "local_authorized" in await call("who_am_i", {})
            cfg = json.loads(await call("get_config", {}))
            await call("set_config_value", {"key":"fileReadLineLimit","value":cfg.get("fileReadLineLimit",1000)})
            await call("get_prompts", {})
            await call("give_feedback_to_desktop_commander", {"feedback":"VexBridge parity self-test"})

            await call("create_directory", {"path":ROOT})
            a = ROOT + r"\a.txt"
            b = ROOT + r"\b.txt"
            await call("write_file", {"path":a,"content":"alpha\nbeta\n","mode":"rewrite"})
            assert "alpha" in await call("read_file", {"path":a})
            await call("write_file", {"path":b,"content":"bravo\n","mode":"rewrite"})
            multi = await call("read_multiple_files", {"paths":[a,b]})
            assert "alpha" in multi and "bravo" in multi
            assert "lineCount" in await call("get_file_info", {"path":a})
            await call("edit_block", {"file_path":a,"old_string":"beta","new_string":"gamma","expected_replacements":1})
            moved = ROOT + r"\moved.txt"
            await call("move_file", {"source":a,"destination":moved})
            assert "moved.txt" in await call("list_directory", {"path":ROOT,"depth":1})

            sid = json.loads(await call("start_search", {"path":ROOT,"pattern":"gamma","searchType":"content","literalSearch":True}))["sessionId"]
            await asyncio.sleep(.2)
            await call("list_searches", {})
            assert "moved.txt" in await call("get_more_search_results", {"sessionId":sid,"length":20})
            sid2 = json.loads(await call("start_search", {"path":r"C:\Users\monte\Documents","pattern":"unlikely-parity-sentinel","searchType":"content","literalSearch":True}))["sessionId"]
            await call("stop_search", {"sessionId":sid2})

            xlsx = ROOT + r"\test.xlsx"
            await call("write_file", {"path":xlsx,"content":'[["Name","N"],["Star",42]]'})
            assert "Star" in await call("read_file", {"path":xlsx,"sheet":"0","range":"A1:B2"})
            await call("edit_block", {"file_path":xlsx,"range":"Sheet1!B2:B2","content":[[43]]})
            assert "43" in await call("read_file", {"path":xlsx,"sheet":"0","range":"A1:B2"})

            docx = ROOT + r"\test.docx"
            await call("write_file", {"path":docx,"content":"# VexBridge\nParity proof"})
            assert "Parity proof" in await call("read_file", {"path":docx})

            pdf = ROOT + r"\test.pdf"
            await call("write_pdf", {"path":pdf,"content":"# VexBridge\n\nParity proof"})
            assert "Parity proof" in await call("read_file", {"path":pdf})
            pdf2 = ROOT + r"\test-mod.pdf"
            await call("write_pdf", {"path":pdf,"outputPath":pdf2,"content":[{"type":"insert","pageIndex":1,"markdown":"# Added page"}]})
            assert "Added page" in await call("read_file", {"path":pdf2})

            proc = json.loads(await call("start_process", {"timeout_ms":1000,"command":"python -i"}))
            pid = proc["pid"]
            assert "42" in await call("interact_with_process", {"pid":pid,"input":"print(6*7)","timeout_ms":3000})
            await call("read_process_output", {"pid":pid,"timeout_ms":500,"offset":-20,"length":20})
            await call("list_sessions", {})
            await call("force_terminate", {"pid":pid})

            sleeper = json.loads(await call("start_process", {"timeout_ms":300,"command":"python -c \"import time; time.sleep(30)\""}))
            await call("kill_process", {"pid":sleeper["pid"]})
            await call("list_processes", {})
            await call("get_usage_stats", {})
            await call("get_recent_tool_calls", {"limit":20})
            print("VEXBRIDGE_PARITY_TEST=PASS")
            print("TOOL_COUNT=" + str(len(names)))

asyncio.run(main())