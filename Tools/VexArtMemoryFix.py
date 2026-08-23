#!/usr/bin/env python3
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
from pathlib import Path

VERSION = "0.10.1"
APPDATA = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
STATE_ROOT = APPDATA / "VexArtWorker"
STATUS_PATH = STATE_ROOT / "memory-status.json"
FIX_SCRIPT = STATE_ROOT / "enable-system-managed-pagefile.ps1"


def _run_powershell(script: str, timeout: int = 30) -> dict:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            creationflags=flags,
        )
        return {"ok": proc.returncode == 0, "returncode": proc.returncode, "output": (proc.stdout or "").strip()}
    except Exception as exc:
        return {"ok": False, "error": f"{exc.__class__.__name__}: {exc}"}


def memory_status() -> dict:
    if os.name != "nt":
        return {"ok": False, "error": "Windows only"}
    script = r'''
$ErrorActionPreference = 'Stop'
$cs = Get-CimInstance Win32_ComputerSystem
$os = Get-CimInstance Win32_OperatingSystem
$pfs = @(Get-CimInstance Win32_PageFileUsage -ErrorAction SilentlyContinue)
$allocated = 0
$current = 0
$peak = 0
foreach ($pf in $pfs) {
  $allocated += [int64]$pf.AllocatedBaseSize
  $current += [int64]$pf.CurrentUsage
  $peak += [int64]$pf.PeakUsage
}
[pscustomobject]@{
  automatic_managed_pagefile = [bool]$cs.AutomaticManagedPagefile
  physical_memory_mb = [math]::Round([double]$cs.TotalPhysicalMemory / 1MB)
  free_physical_memory_mb = [math]::Round([double]$os.FreePhysicalMemory / 1024)
  total_virtual_memory_mb = [math]::Round([double]$os.TotalVirtualMemorySize / 1024)
  free_virtual_memory_mb = [math]::Round([double]$os.FreeVirtualMemory / 1024)
  pagefile_allocated_mb = $allocated
  pagefile_current_usage_mb = $current
  pagefile_peak_usage_mb = $peak
  pagefile_count = $pfs.Count
} | ConvertTo-Json -Compress
'''
    result = _run_powershell(script)
    if not result.get("ok"):
        payload = {"ok": False, "error": result.get("error") or result.get("output") or "PowerShell query failed"}
    else:
        try:
            payload = json.loads(str(result.get("output") or "{}"))
            payload["ok"] = True
        except Exception as exc:
            payload = {"ok": False, "error": f"Could not parse memory status: {exc}"}
    try:
        STATE_ROOT.mkdir(parents=True, exist_ok=True)
        STATUS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        pass
    return payload


def write_fix_script() -> Path:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    text = r'''$ErrorActionPreference = 'Stop'
Write-Host "Vex Art Memory Fix" -ForegroundColor Cyan
Write-Host "Enabling Windows-managed paging file..."
$cs = Get-CimInstance Win32_ComputerSystem
Set-CimInstance -InputObject $cs -Property @{AutomaticManagedPagefile=$true} | Out-Null
$verify = Get-CimInstance Win32_ComputerSystem
if (-not $verify.AutomaticManagedPagefile) {
    throw "Windows did not accept AutomaticManagedPagefile=True"
}
Write-Host "Done. Windows-managed paging is enabled." -ForegroundColor Green
Write-Host "Restart Windows before trying the Vex Art render test again." -ForegroundColor Yellow
Write-Host "This helper did not delete files or change Vex/Bridge settings."
Read-Host "Press Enter to close"
'''
    FIX_SCRIPT.write_text(text, encoding="utf-8")
    return FIX_SCRIPT


def request_fix() -> tuple[bool, str]:
    if os.name != "nt":
        return False, "Windows only"
    try:
        script = write_fix_script()
        args = f'-NoProfile -ExecutionPolicy Bypass -File "{script}"'
        code = ctypes.windll.shell32.ShellExecuteW(None, "runas", "powershell.exe", args, None, 1)
        if int(code) <= 32:
            return False, f"Windows elevation request failed (code {int(code)})"
        return True, "UAC request opened. Approve it, let the blue repair window finish, then restart Windows."
    except Exception as exc:
        return False, f"{exc.__class__.__name__}: {exc}"


def main() -> int:
    import tkinter as tk
    from tkinter import messagebox
    from tkinter.scrolledtext import ScrolledText

    root = tk.Tk()
    root.title(f"Vex Art Memory Fix v{VERSION}")
    root.geometry("760x560")
    root.minsize(680, 500)

    tk.Label(root, text="Vex Art Memory Fix", font=("Segoe UI", 18, "bold")).pack(pady=(16, 4))
    tk.Label(
        root,
        text="Repairs Windows virtual-memory configuration for ComfyUI checkpoint loading.\n"
             "This is a separate repair tool; it does not modify Vex cognition, Bridge, prompts, files, or models.",
        justify="center",
    ).pack(pady=(0, 12))

    status_label = tk.Label(root, text="Checking Windows virtual memory...", font=("Segoe UI", 11, "bold"))
    status_label.pack(pady=(0, 8))

    text = ScrolledText(root, wrap="word", font=("Consolas", 10), height=16)
    text.pack(fill="both", expand=True, padx=16, pady=8)

    buttons = tk.Frame(root)
    buttons.pack(fill="x", padx=16, pady=(4, 16))

    state = {"status": {}}

    def refresh() -> None:
        payload = memory_status()
        state["status"] = payload
        text.delete("1.0", "end")
        text.insert("end", json.dumps(payload, indent=2))
        if not payload.get("ok"):
            status_label.configure(text="Could not read virtual-memory state")
            return
        auto = bool(payload.get("automatic_managed_pagefile"))
        allocated = int(payload.get("pagefile_allocated_mb") or 0)
        physical = int(payload.get("physical_memory_mb") or 0)
        if auto:
            status_label.configure(text=f"Windows-managed paging: ON   |   pagefile allocated now: {allocated:,} MB")
        else:
            status_label.configure(text=f"Windows-managed paging: OFF   |   pagefile allocated now: {allocated:,} MB")
        text.insert("end", "\n\nArt failure we are repairing: Windows OSError 1455 while CheckpointLoaderSimple loads the model.\n")
        text.insert("end", f"Physical RAM detected: {physical:,} MB. Enabling Windows-managed paging lets Windows grow commit space as the local model needs it.\n")

    def fix() -> None:
        if not messagebox.askyesno(
            "Vex Art Memory Fix",
            "Enable Windows-managed paging file?\n\n"
            "Windows will ask for Administrator approval. A restart is required before retesting art.\n"
            "No personal files or Vex settings will be deleted.",
        ):
            return
        ok, message = request_fix()
        if ok:
            messagebox.showinfo("Vex Art Memory Fix", message)
        else:
            messagebox.showerror("Vex Art Memory Fix", message)

    def restart() -> None:
        if messagebox.askyesno("Restart Windows", "Restart this PC now so the paging-file change can take effect?"):
            subprocess.Popen(["shutdown.exe", "/r", "/t", "5"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    tk.Button(buttons, text="Refresh Status", width=18, command=refresh).pack(side="left", padx=4)
    tk.Button(buttons, text="Enable Windows-Managed Paging", width=30, command=fix).pack(side="left", padx=4)
    tk.Button(buttons, text="Restart Windows", width=18, command=restart).pack(side="right", padx=4)

    refresh()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
