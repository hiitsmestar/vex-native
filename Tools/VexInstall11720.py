from __future__ import annotations
import hashlib, json, os, shutil, subprocess, sys, time, urllib.parse, urllib.request
from pathlib import Path
from tkinter import Tk, messagebox

VERSION='0.11.7.20'
FILES=['VexBridge.exe','VexRemoteSupport.exe','VexDoctor.exe','VexBridgeWatchdog-v11720.ps1']

def sha256(path: Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def package_dir()->Path:
    return Path(sys.executable if getattr(sys,'frozen',False) else __file__).resolve().parent

def find_home()->Path:
    dl=Path.home()/'Downloads'
    candidates=[]
    for p in dl.iterdir():
        if p.is_dir() and (p/'START-VEX-SELF-HEAL.cmd').exists() and (p/'VexBridge.exe').exists(): candidates.append(p)
    preferred=[p for p in candidates if p.name.startswith('VexBridge-v0.11.0-Personal-Memory-Star-Seeded')]
    if not (preferred or candidates): raise RuntimeError('Could not find the existing Vex folder under Downloads.')
    return (preferred or candidates)[0]

def run_ps(script:str, timeout:int=45):
    return subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-Command',script],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),timeout=timeout,capture_output=True,text=True)

def stop_all_vex(home:Path)->None:
    home_s=str(home).replace("'","''")
    script=rf'''
$ErrorActionPreference='SilentlyContinue'
$home='{home_s}'
$deadline=(Get-Date).AddSeconds(35)
do {{
  $targets = Get-CimInstance Win32_Process | Where-Object {{
    ($_.Name -like 'Vex*.exe') -or
    ($_.CommandLine -and ($_.CommandLine -like '*VexBridgeWatchdog*' -or $_.CommandLine -like '*START-VEX-SELF-HEAL*' -or $_.CommandLine -like ('*'+$home+'*')))
  }}
  $targets | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}
  Start-Sleep -Milliseconds 650
  $left = Get-CimInstance Win32_Process | Where-Object {{
    ($_.Name -like 'Vex*.exe') -or
    ($_.CommandLine -and ($_.CommandLine -like '*VexBridgeWatchdog*' -or $_.CommandLine -like '*START-VEX-SELF-HEAL*' -or $_.CommandLine -like ('*'+$home+'*')))
  }}
}} while ($left -and (Get-Date) -lt $deadline)
if ($left) {{ exit 9 }}
'''
    r=run_ps(script,timeout=40)
    if r.returncode!=0: raise RuntimeError('Could not stop all stale Vex processes before install.')

def replace_with_retry(src:Path,dst:Path,seconds:int=35)->None:
    deadline=time.time()+seconds; last=None
    while time.time()<deadline:
        try:
            tmp=dst.with_name(dst.name+'.vexnew')
            try:
                if tmp.exists(): tmp.unlink()
            except Exception: pass
            shutil.copy2(src,tmp)
            if sha256(src)!=sha256(tmp): raise RuntimeError(f'Hash verification failed while staging {dst.name}')
            os.replace(tmp,dst)
            if sha256(src)!=sha256(dst): raise RuntimeError(f'Hash verification failed: {dst.name}')
            return
        except Exception as exc:
            last=exc; time.sleep(0.8)
    raise RuntimeError(f'Could not replace {dst.name}: {last}')

def bridge_config()->dict:
    p=Path(os.environ.get('APPDATA',str(Path.home())))/'VexBridge'/'config.json'
    try: return json.loads(p.read_text('utf-8'))
    except Exception: return {}

def wait_bridge_version(expected:str, seconds:int=45)->None:
    deadline=time.time()+seconds; last='no response'
    while time.time()<deadline:
        cfg=bridge_config(); token=str(cfg.get('token') or '').strip(); external=int(cfg.get('port') or 8765); port=int(cfg.get('local_control_port') or (external+1))
        if token:
            url=f'http://127.0.0.1:{port}/status?'+urllib.parse.urlencode({'token':token})
            try:
                opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(url,timeout=4) as r: data=json.loads(r.read().decode('utf-8'))
                got=str(data.get('version') or ''); protocol=str(data.get('local_control_protocol') or '')
                if got==expected and protocol=='vex-local-v1': return
                last=f'expected {expected}/vex-local-v1, got {got or "unknown"}/{protocol or "unknown"}'
            except Exception as exc: last=exc.__class__.__name__
        else: last='Bridge config token unavailable'
        time.sleep(1)
    raise RuntimeError(f'Unified local control plane did not verify Bridge {expected}: {last}')

def wait_remote_identity(expected:str, seconds:int=20)->None:
    p=Path(os.environ.get('APPDATA',str(Path.home())))/'VexRemoteSupport'/'runtime-identity.json'
    try: p.unlink(missing_ok=True)
    except Exception: pass
    deadline=time.time()+seconds; last='missing runtime identity'
    while time.time()<deadline:
        try:
            data=json.loads(p.read_text('utf-8')); got=str(data.get('version') or '')
            if got==expected and int(data.get('pid') or 0)>0: return
            last=f'expected {expected}, got {got or "unknown"}'
        except Exception as exc: last=exc.__class__.__name__
        time.sleep(0.75)
    raise RuntimeError(f'New Remote Support did not prove runtime version {expected}: {last}')

def verify_doctor(home:Path)->None:
    doc=home/'VexDoctor.exe'
    if not doc.exists(): raise RuntimeError('VexDoctor.exe was not installed.')
    out=Path(os.environ.get('APPDATA',str(Path.home())))/'VexDoctor'/'install-smoke.json'
    out.parent.mkdir(parents=True,exist_ok=True)
    try:
        subprocess.run([str(doc),'--headless','--json-out',str(out)],cwd=str(home),timeout=45,capture_output=True,text=True)
    except Exception as exc:
        raise RuntimeError(f'VexDoctor smoke test could not run: {exc.__class__.__name__}')
    if not out.exists(): raise RuntimeError('VexDoctor smoke test produced no report.')

def main():
    root=Tk(); root.withdraw()
    try:
        pkg=package_dir(); home=find_home()
        for name in FILES:
            if not (pkg/name).exists(): raise RuntimeError(f'Package file missing: {name}')
        stop_all_vex(home)
        for name in FILES:
            dstname='VexBridgeWatchdog.ps1' if name.endswith('v11720.ps1') else name
            replace_with_retry(pkg/name,home/dstname)
        subprocess.Popen([str(home/'VexBridge.exe')],cwd=str(home))
        wait_bridge_version(VERSION,seconds=45)
        verify_doctor(home)
        subprocess.Popen([str(home/'VexRemoteSupport.exe')],cwd=str(home))
        wait_remote_identity(VERSION,seconds=20)
        watchdog=home/'VexBridgeWatchdog.ps1'
        subprocess.Popen(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(watchdog)],cwd=str(home),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        messagebox.showinfo('Vex Install',f'Vex {VERSION} installed and unified control plane verified. Bridge, Remote Support, Doctor, watchdog, local HTTP control, and LAN TLS service are coordinated.\n\nStart a fresh 2-hour support session and enable SAFE maintenance.')
    except Exception as exc:
        messagebox.showerror('Vex Install',f'Install failed: {exc}')
        raise
    finally: root.destroy()
if __name__=='__main__': main()
