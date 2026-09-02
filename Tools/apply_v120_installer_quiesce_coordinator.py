#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

INSTALLER = Path("Tools/VexAgentRuntimeInstall.py")
installer = INSTALLER.read_text(encoding="utf-8")

# Field install on the upstairs node proved VexPeerCoordinator can remain alive
# while the installer is trying to quiesce the old runtime. Because the
# coordinator can supervise/relaunch other Vex processes, leaving it outside the
# known shutdown set makes stop_known_vex_processes() time out even though the
# individual workers were killed successfully.
old = '''KNOWN_PROCESSES = (\n    "VexBridge",\n    "VexMemoryWorker",\n    "VexDoctor",\n    "VexToolbox",\n    "VexRemoteSupport",\n    "VexWindowsHost",\n    "VexNodeAgent",\n)\n'''
new = '''KNOWN_PROCESSES = (\n    "VexBridge",\n    "VexMemoryWorker",\n    "VexDoctor",\n    "VexToolbox",\n    "VexRemoteSupport",\n    "VexWindowsHost",\n    "VexNodeAgent",\n    "VexPeerCoordinator",\n)\n'''
if old in installer:
    installer = installer.replace(old, new, 1)
elif '"VexPeerCoordinator",' not in installer:
    raise SystemExit("v0.12 installer quiesce fix could not extend KNOWN_PROCESSES")

# Add one explicit tree-kill pass after the normal CIM/Stop-Process loop. This is
# bounded to the exact known Vex executables and catches stubborn child trees that
# survive a parent stop during an upgrade. Do not wildcard Vex* because the
# installer itself is also a Vex executable.
old_tail = '''if ($left.Count -gt 0) { exit 9 }\n"""\n    result = run_powershell(script, timeout=45)\n    if result.returncode != 0:\n        raise RuntimeError("Could not stop the existing Vex runtime cleanly before install.")\n'''
new_tail = '''if ($left.Count -gt 0) {\n  foreach ($p in $left) { cmd.exe /c "taskkill /PID $($p.ProcessId) /T /F" | Out-Null }\n  Start-Sleep -Milliseconds 900\n  $left=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -in $names })\n}\nif ($left.Count -gt 0) { exit 9 }\n"""\n    result = run_powershell(script, timeout=48)\n    if result.returncode != 0:\n        raise RuntimeError("Could not stop the existing Vex runtime cleanly before install.")\n'''
if old_tail in installer:
    installer = installer.replace(old_tail, new_tail, 1)
elif 'taskkill /PID $($p.ProcessId) /T /F' not in installer:
    raise SystemExit("v0.12 installer quiesce fix could not add bounded tree-kill fallback")

INSTALLER.write_text(installer, encoding="utf-8")
compile(installer, str(INSTALLER), "exec")

for marker in [
    '"VexPeerCoordinator",',
    'taskkill /PID $($p.ProcessId) /T /F',
    'timeout=48',
]:
    if marker not in installer:
        raise SystemExit(f"v0.12 installer quiesce fix missing marker: {marker}")

print("Applied v0.12 installer coordinator/tree quiesce fix")
