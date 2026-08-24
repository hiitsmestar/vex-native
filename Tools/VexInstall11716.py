from __future__ import annotations
import hashlib, os, shutil, subprocess, sys, time
from pathlib import Path
from tkinter import Tk, messagebox

VERSION='0.11.7.16'
FILES=['VexBridge.exe','VexRemoteSupport.exe','VexBridgeWatchdog-v11714.ps1']

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
        if p.is_dir() and (p/'START-VEX-SELF-HEAL.cmd').exists() and (p/'VexBridge.exe').exists():
            candidates.append(p)
    preferred=[p for p in candidates if p.name.startswith('VexBridge-v0.11.0-Personal-Memory-Star-Seeded')]
    if not (preferred or candidates): raise RuntimeError('Could not find the existing Vex folder under Downloads.')
    return (preferred or candidates)[0]

def run_ps(script:str, timeout:int=30):
    return subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-Command',script],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),timeout=timeout,capture_output=True,text=True)

def stop_vex_processes(home:Path)->None:
    script = r'''
$ErrorActionPreference='SilentlyContinue'
$deadline=(Get-Date).AddSeconds(20)
do {
  Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -in @('VexBridge.exe','VexRemoteSupport.exe')) -or
    ($_.CommandLine -and ($_.CommandLine -like '*VexBridgeWatchdog*' -or $_.CommandLine -like '*START-VEX-SELF-HEAL*'))
  } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  Start-Sleep -Milliseconds 500
  $left = Get-Process VexBridge,VexRemoteSupport -ErrorAction SilentlyContinue
} while ($left -and (Get-Date) -lt $deadline)
'''
    run_ps(script, timeout=25)

def replace_with_retry(src:Path,dst:Path,seconds:int=25)->None:
    deadline=time.time()+seconds
    last=None
    while time.time()<deadline:
        try:
            tmp=dst.with_name(dst.name+'.vexnew')
            try:
                if tmp.exists(): tmp.unlink()
            except Exception:
                pass
            shutil.copy2(src,tmp)
            if sha256(src)!=sha256(tmp):
                raise RuntimeError(f'Hash verification failed while staging {dst.name}')
            os.replace(tmp,dst)
            if sha256(src)!=sha256(dst):
                raise RuntimeError(f'Hash verification failed: {dst.name}')
            return
        except Exception as exc:
            last=exc
            time.sleep(0.75)
    raise RuntimeError(f'Could not replace {dst.name} after waiting for Windows to release it: {last}')

def main():
    root=Tk(); root.withdraw()
    try:
        pkg=package_dir(); home=find_home()
        for name in FILES:
            if not (pkg/name).exists(): raise RuntimeError(f'Package file missing: {name}')
        stop_vex_processes(home)
        time.sleep(1)
        for name in FILES:
            dstname='VexBridgeWatchdog.ps1' if name.endswith('v11714.ps1') else name
            replace_with_retry(pkg/name, home/dstname)
        start=home/'START-VEX-SELF-HEAL.cmd'
        if start.exists(): subprocess.Popen([str(start)],cwd=str(home),shell=True)
        time.sleep(3)
        subprocess.Popen([str(home/'VexRemoteSupport.exe')],cwd=str(home))
        messagebox.showinfo('Vex Install',f'Vex {VERSION} installed and SHA256 verified.\n\nStart a fresh 2-hour support session and enable SAFE maintenance.')
    except Exception as exc:
        messagebox.showerror('Vex Install',f'Install failed: {exc}')
        raise
    finally:
        root.destroy()
if __name__=='__main__': main()
