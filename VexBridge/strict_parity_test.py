import asyncio, json, os, pathlib
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL=os.environ.get('VEXBRIDGE_TEST_URL','http://127.0.0.1:8796/mcp')
ROOT=os.environ.get('VEXBRIDGE_TEST_ROOT',r'C:\Users\monte\Documents\VexBridgeStrictParity')
DEVICE=os.environ.get('VEXBRIDGE_TEST_DEVICE','monte')

async def main():
    async with streamablehttp_client(URL) as (read,write,_):
        async with ClientSession(read,write) as s:
            await s.initialize()
            listed=await s.list_tools()
            tools={t.name:t for t in listed.tools}
            assert len(tools)==41
            expected={'ping','list_devices','who_am_i','get_prompts','give_feedback_to_desktop_commander','get_config','set_config_value','read_file','read_multiple_files','write_file','write_pdf','create_directory','list_directory','move_file','start_search','get_more_search_results','stop_search','list_searches','get_file_info','edit_block','start_process','read_process_output','interact_with_process','force_terminate','list_sessions','list_processes','kill_process','get_usage_stats','get_recent_tool_calls','shutdown','integration_status','icm_store','icm_recall','icm_stats','unlazy_status','unlazy_lint','a2a_status','a2a_agents','a2a_card','a2a_send','a2a_rpc'}
            assert set(tools)==expected
            remote=expected-{'list_devices','who_am_i'}
            for name in remote:
                assert 'deviceId' in tools[name].inputSchema.get('properties',{}), name
            sp=set(tools['start_search'].inputSchema['properties'])
            assert sp=={'maxResults','includeHidden','timeout_ms','contextLines','filePattern','ignoreCase','searchType','earlyTermination','pattern','path','deviceId','literalSearch'}
            rp=set(tools['get_recent_tool_calls'].inputSchema['properties'])
            assert rp=={'maxResults','toolName','since','deviceId'}
            gp=tools['get_prompts'].inputSchema
            assert set(gp.get('required',[]))=={'action','promptId'}

            async def call(name,args):
                r=await s.call_tool(name,args)
                if getattr(r,'isError',False):
                    raise RuntimeError(name+': '+'\n'.join(getattr(x,'text','') for x in r.content))
                return '\n'.join(getattr(x,'text','') for x in r.content)

            assert 'pong' in (await call('ping',{'deviceId':DEVICE})).lower()
            assert 'device_name' in await call('list_devices',{})
            assert 'local_authorized' in await call('who_am_i',{})
            assert 'Organize' in await call('get_prompts',{'action':'get_prompt','promptId':'onb2_01','deviceId':DEVICE})
            await call('give_feedback_to_desktop_commander',{'deviceId':DEVICE})
            cfg=json.loads(await call('get_config',{'deviceId':DEVICE}))
            roots=cfg.get('allowedDirectories',cfg.get('allowedRoots',[]))
            cfg2=json.loads(await call('set_config_value',{'key':'allowedDirectories','value':roots,'deviceId':DEVICE}))
            assert cfg2.get('allowedDirectories')==cfg2.get('allowedRoots')

            await call('create_directory',{'path':ROOT,'deviceId':DEVICE})
            a=ROOT+r'\a.txt'; b=ROOT+r'\b.txt'; c=ROOT+r'\c.txt'
            await call('write_file',{'path':a,'content':'needle one\nalpha\n','mode':'rewrite','deviceId':DEVICE})
            await call('write_file',{'path':b,'content':'beta\nneedle two\n','mode':'rewrite','deviceId':DEVICE})
            await call('write_file',{'path':c,'content':'needle three\ngamma\n','mode':'rewrite','deviceId':DEVICE})
            assert 'needle one' in await call('read_file',{'path':a,'deviceId':DEVICE})
            assert 'needle two' in await call('read_multiple_files',{'paths':[a,b],'deviceId':DEVICE})
            await call('edit_block',{'file_path':a,'old_string':'alpha','new_string':'delta','expected_replacements':1,'deviceId':DEVICE})
            assert 'delta' in await call('read_file',{'path':a,'deviceId':DEVICE})

            sid=json.loads(await call('start_search',{'path':ROOT,'pattern':'needle','searchType':'content','literalSearch':True,'maxResults':2,'includeHidden':False,'contextLines':1,'timeout_ms':5000,'deviceId':DEVICE}))['sessionId']
            for _ in range(20):
                await asyncio.sleep(.1)
                page=json.loads(await call('get_more_search_results',{'sessionId':sid,'offset':0,'length':10,'deviceId':DEVICE}))
                if page.get('done'): break
            assert page['total']==2, page
            p0=json.loads(await call('get_more_search_results',{'sessionId':sid,'offset':0,'length':1,'deviceId':DEVICE}))['results']
            p1=json.loads(await call('get_more_search_results',{'sessionId':sid,'offset':1,'length':1,'deviceId':DEVICE}))['results']
            assert p0 and p1 and p0[0]!=p1[0]
            assert 'context' in p0[0] and 'lineNumber' in p0[0]
            await call('list_searches',{'deviceId':DEVICE})

            proc=json.loads(await call('start_process',{'timeout_ms':1000,'command':'python -i','deviceId':DEVICE}))
            pid=proc['pid']
            assert '42' in await call('interact_with_process',{'pid':pid,'input':'print(6*7)','timeout_ms':3000,'deviceId':DEVICE})
            await call('read_process_output',{'pid':pid,'timeout_ms':500,'offset':-20,'length':20,'deviceId':DEVICE})
            await call('list_sessions',{'deviceId':DEVICE})
            await call('force_terminate',{'pid':pid,'deviceId':DEVICE})
            await call('list_processes',{'deviceId':DEVICE})

            rr=await s.call_tool('get_recent_tool_calls',{'maxResults':100,'deviceId':DEVICE})
            recent=(getattr(rr,'structuredContent',None) or {}).get('result',[])
            assert any(x.get('tool')=='ping' for x in recent)
            fr=await s.call_tool('get_recent_tool_calls',{'maxResults':10,'toolName':'write_file','deviceId':DEVICE})
            filtered=(getattr(fr,'structuredContent',None) or {}).get('result',[])
            assert filtered and all(x.get('tool')=='write_file' for x in filtered)
            await call('get_usage_stats',{'deviceId':DEVICE})
            print('VEXBRIDGE_STRICT_PARITY=PASS')
            print('TOOL_COUNT=41')

asyncio.run(main())
