#!/usr/bin/env python3
from __future__ import annotations

import json, os, shutil, subprocess, tempfile, time, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path.cwd()
SAVE = "Remember this test fact: my imaginary fox is named Mica"
CORRECT = 'Correction: my imaginary fox is named Nyx, not Mica. Replace the old fact and remember Nyx as the current name.'
OLD = "my imaginary fox is named Mica"
NEW = "my imaginary fox is named Nyx"

def opener(): return urllib.request.build_opener(urllib.request.ProxyHandler({}))
def get_json(url, timeout=3):
    with opener().open(url, timeout=timeout) as r: return json.loads(r.read().decode("utf-8"))
def post_json(url, payload, timeout=8):
    req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={"Content-Type":"application/json"},method="POST")
    with opener().open(req,timeout=timeout) as r: return json.loads(r.read().decode("utf-8"))
def wait_json(url,predicate,seconds,label):
    deadline=time.time()+seconds; last=None
    while time.time()<deadline:
        try:
            v=get_json(url,2.5)
            if predicate(v): return v
            last=v
        except Exception as e: last=f"{type(e).__name__}: {e}"
        time.sleep(.4)
    raise RuntimeError(f"{label} not ready: {last}")
def psq(v): return str(v).replace("'","''")
def start_win(exe,env):
    s=f"$p=Start-Process -FilePath '{psq(exe)}' -WorkingDirectory '{psq(exe.parent)}' -PassThru; Write-Output $p.Id"
    r=subprocess.run(["powershell.exe","-NoProfile","-NonInteractive","-Command",s],env=env,text=True,capture_output=True,check=True)
    return int([x.strip() for x in r.stdout.splitlines() if x.strip()][-1])
def stop(pid):
    if pid: subprocess.run(["taskkill.exe","/PID",str(pid),"/T","/F"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

def main():
    src=(ROOT/"Bridge/vex_bridge.py").read_text("utf-8")
    for m in ['explicit-personal-memory-correction-v11752','"memory_correction": bool(replaced)','"agent_runtime_bundle": "0.11.7.52"']:
        if m not in src: raise RuntimeError(f"missing .52 marker: {m}")
    base=Path(tempfile.mkdtemp(prefix="Vex11752Correction-")); roam=base/"Roaming"; local=base/"Local"; roam.mkdir(); local.mkdir()
    env=os.environ.copy(); env.update({"APPDATA":str(roam),"LOCALAPPDATA":str(local),"PYTHONUTF8":"0","PYTHONIOENCODING":"cp1252"})
    mem=ROOT/"dist/VexMemoryWorker/VexMemoryWorker.exe"; bridge=ROOT/"dist/VexBridge/VexBridge.exe"
    mp=subprocess.Popen([str(mem),"--serve","--port","8806"],cwd=str(mem.parent),env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    bp=None
    try:
        wait_json("http://127.0.0.1:8806/health",lambda d:d.get("ok") is True,30,"memory")
        bp=start_win(bridge,env)
        cfgp=roam/"VexBridge/config.json"; deadline=time.time()+90; cfg=None
        while time.time()<deadline:
            try:
                if cfgp.exists():
                    c=json.loads(cfgp.read_text("utf-8"))
                    if c.get("token") and c.get("local_control_port"): cfg=c; break
            except Exception: pass
            time.sleep(.4)
        if not cfg: raise RuntimeError("Bridge config missing")
        q=urllib.parse.urlencode({"token":cfg["token"]}); port=int(cfg["local_control_port"])
        wait_json(f"http://127.0.0.1:{port}/status?{q}",lambda d:d.get("version")=="0.11.7.39",60,"Bridge")
        chat=f"http://127.0.0.1:{port}/llm/chat?{q}"
        first=post_json(chat,{"message":SAVE,"history":[]})
        if first.get("memory_write") is not True: raise RuntimeError(f"Mica write failed: {first}")
        corr=post_json(chat,{"message":CORRECT,"history":[]})
        print(json.dumps(corr,ensure_ascii=True),flush=True)
        if corr.get("memory_correction") is not True or corr.get("grounding")!="explicit-personal-memory-correction-v11752": raise RuntimeError(f"correction route failed: {corr}")
        found=post_json("http://127.0.0.1:8806/search",{"query":"imaginary fox Mica Nyx","memory_limit":24,"episode_limit":0})
        texts=[str(x.get("text") or "").strip() for x in found.get("memories",[]) if isinstance(x,dict)]
        if NEW not in texts: raise RuntimeError(f"Nyx missing: {texts}")
        if OLD in texts: raise RuntimeError(f"stale Mica still active: {texts}")
        recall=post_json(chat,{"message":"What is my imaginary fox named?","history":[]},timeout=12)
        reply=str(recall.get("reply") or "")
        if "Nyx" not in reply or "Mica" in reply: raise RuntimeError(f"fresh recall did not prefer correction: {recall}")
        print("[v11752-test] PASS Mica -> correction -> Nyx only -> fresh recall Nyx",flush=True)
    finally:
        stop(bp)
        try: mp.terminate(); mp.wait(timeout=5)
        except Exception:
            try: mp.kill()
            except Exception: pass
        shutil.rmtree(base,ignore_errors=True)

if __name__=="__main__": main()
