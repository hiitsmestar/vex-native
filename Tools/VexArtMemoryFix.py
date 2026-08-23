#!/usr/bin/env python3
from __future__ import annotations

import ctypes
import json
import os
import subprocess
from pathlib import Path

VERSION = "0.10.2"
APPDATA = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
STATE_ROOT = APPDATA / "VexArtWorker"
STATUS_PATH = STATE_ROOT / "memory-status.json"
FIX_SCRIPT = STATE_ROOT / "set-art-safe-pagefile.ps1"
PAGEFILE_MIN_MB = 32768
PAGEFILE_MAX_MB = 65536


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
$settings = @(Get-CimInstance Win32_PageFileSetting -ErrorAction SilentlyContinue)
$allocated = 0
$current = 0
$peak = 0
foreach ($pf in $pfs) {
  $allocated += [int64]$pf.AllocatedBaseSize
  $current += [int64]$pf.CurrentUsage
  $peak += [int64]$pf.PeakUsage
}
$configuredInitial = 0
$configuredMaximum = 0
foreach ($setting in $settings) {
  if ($setting.Name -ieq 'C:\pagefile.sys') {
    $configuredInitial = [int64]$setting.InitialSize
    $configuredMaximum = [int64]$setting.MaximumSize
  }
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
  c_pagefile_initial_mb = $configuredInitial
  c_pagefile_maximum_mb = $configuredMaximum
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
    text = rf'''$ErrorActionPreference = 'Stop'
Write-Host "Vex Art Memory Fix v{VERSION}" -ForegroundColor Cyan
Write-Host "Configuring the INTERNAL C: pagefile for the 8 GB local art node..."
Write-Host "Minimum: {PAGEFILE_MIN_MB} MB   Maximum: {PAGEFILE_MAX_MB} MB"
$cs = Get-CimInstance Win32_ComputerSystem
Set-CimInstance -InputObject $cs -Property @{{AutomaticManagedPagefile=$false}} | Out-Null
$existing = Get-CimInstance Win32_PageFileSetting -ErrorAction SilentlyContinue | Where-Object {{ $_.Name -ieq 'C:\pagefile.sys' }}
if ($null -eq $existing) {{
    New-CimInstance -ClassName Win32_PageFileSetting -Property @{{Name='C:\pagefile.sys'; InitialSize={PAGEFILE_MIN_MB}; MaximumSize={PAGEFILE_MAX_MB}}} | Out-Null
}} else {{
    Set-CimInstance -InputObject $existing -Property @{{InitialSize={PAGEFILE_MIN_MB}; MaximumSize={PAGEFILE_MAX_MB}}} | Out-Null
}}
$verifyCS = Get-CimInstance Win32_ComputerSystem
$verifyPF = Get-CimInstance Win32_PageFileSetting -ErrorAction SilentlyContinue | Where-Object {{ $_.Name -ieq 'C:\pagefile.sys' }}
if ($verifyCS.AutomaticManagedPagefile) {{ throw 'Windows still reports automatic pagefile management enabled.' }}
if ($null -eq $verifyPF) {{ throw 'C:\pagefile.sys setting was not created.' }}
if ([int64]$verifyPF.InitialSize -lt {PAGEFILE_MIN_MB}) {{ throw 'Pagefile minimum did not apply.' }}
Write-Host "Done. C: pagefile configuration is ready." -ForegroundColor Green
Write-Host "Restart Windows before running Vex Art Worker again." -ForegroundColor Yellow
Write-Host "The external Seagate drive was NOT changed." -ForegroundColor DarkGray
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
        return True, "UAC request opened. Approve it, let the repair window say Done, then restart Windows."
    except Exception as exc:
        return False, f"{exc.__class__.__name__}: {exc}"


def main() -> int:
    import tkinter as tk
    from tkinter import messagebox
    from tkinter.scrolledtext import ScrolledText

    root = tk.Tk()
    root.title(f"Vex Art Memory Fix v{VERSION}")
    root.geometry("780x590")
    root.minsize(700, 520)

    tk.Label(root, text="Vex Art Memory Fix", font=("Segoe UI", 18, "bold")).pack(pady=(16, 4))
    tk.Label(
        root,
        text="Preallocates a sane INTERNAL Windows pagefile for the 8 GB CPU art node.\n"
             "It does not touch the external Seagate drive, personal files, Vex cognition, Bridge, prompts, or models.",
        justify="center",
    ).pack(pady=(0, 12))

    status_label = tk.Label(root, text="Checking Windows virtual memory...", font=("Segoe UI", 11, "bold"))
    status_label.pack(pady=(0, 8))

    text = ScrolledText(root, wrap="word", font=("Consolas", 10), height=17)
    text.pack(fill="both", expand=True, padx=16, pady=8)

    buttons = tk.Frame(root)
    buttons.pack(fill="x", padx=16, pady=(4, 16))

    def refresh() -> None:
        payload = memory_status()
        text.delete("1.0", "end")
        text.insert("end", json.dumps(payload, indent=2))
        if not payload.get("ok"):
            status_label.configure(text="Could not read virtual-memory state")
            return
        allocated = int(payload.get("pagefile_allocated_mb") or 0)
        initial = int(payload.get("c_pagefile_initial_mb") or 0)
        maximum = int(payload.get("c_pagefile_maximum_mb") or 0)
        if initial >= PAGEFILE_MIN_MB and maximum >= PAGEFILE_MAX_MB:
            status_label.configure(text=f"Art-safe pagefile configured: {initial:,}-{maximum:,} MB | currently allocated: {allocated:,} MB")
        else:
            status_label.configure(text=f"Current pagefile is still small for SDXL CPU rendering | allocated now: {allocated:,} MB")
        text.insert("end", "\n\nTarget for this PC: 32 GB minimum / 64 GB maximum on INTERNAL C:.\n")
        text.insert("end", "Reason: RealVisXL/SDXL plus an 8 GB CPU host needs commit headroom without forcing the whole desktop into emergency paging.\n")

    def fix() -> None:
        if not messagebox.askyesno(
            "Vex Art Memory Fix",
            "Set the INTERNAL C: pagefile to 32 GB minimum / 64 GB maximum?\n\n"
            "Windows will ask for Administrator approval and a restart is required.\n"
            "The external Seagate drive will not be changed.",
        ):
            return
        ok, message = request_fix()
        if ok:
            messagebox.showinfo("Vex Art Memory Fix", message)
        else:
            messagebox.showerror("Vex Art Memory Fix", message)

    def restart() -> None:
        if messagebox.askyesno("Restart Windows", "Restart this PC now so the pagefile change can take effect?"):
            subprocess.Popen(["shutdown.exe", "/r", "/t", "5"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    tk.Button(buttons, text="Refresh Status", width=18, command=refresh).pack(side="left", padx=4)
    tk.Button(buttons, text="Set 32-64 GB Internal Pagefile", width=31, command=fix).pack(side="left", padx=4)
    tk.Button(buttons, text="Restart Windows", width=18, command=restart).pack(side="right", padx=4)

    refresh()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
