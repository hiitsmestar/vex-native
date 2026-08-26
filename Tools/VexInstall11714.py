from __future__ import annotations
import hashlib, os, shutil, subprocess, sys, time
from pathlib import Path
from tkinter import Tk, messagebox

VERSION='0.11.7.14'
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

def run_ps(script:str):
    subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-Command',script],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),timeout=30)

def main():
    root=Tk(); root.withdraw()
    try:
        pkg=package_dir(); home=find_home()
        for name in FILES:
            if not (pkg/name).exists(): raise RuntimeError(f'Package file missing: {name}')
        run_ps("Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {$_.CommandLine -and $_.CommandLine -like '*VexBridgeWatchdog*'} | ForEach-Object {Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue}; Stop-Process -Name VexBridge,VexRemoteSupport -Force -ErrorAction SilentlyContinue")
        time.sleep(2)
        for name in FILES:
            dstname='VexBridgeWatchdog.ps1' if name.endswith('v11714.ps1') else name
            src=pkg/name; dst=home/dstname
            shutil.copy2(src,dst)
            if sha256(src)!=sha256(dst): raise RuntimeError(f'Hash verification failed: {dstname}')
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
