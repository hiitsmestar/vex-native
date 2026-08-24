#!/usr/bin/env python3
from pathlib import Path

path = Path("Tools/VexRemoteSupport.py")
text = path.read_text(encoding="utf-8")
compile(text, str(path), "exec")

required = [
    'VERSION = "0.11.7.11"',
    'action == "project_status"',
    'action == "project_hash"',
    'action == "project_stop"',
    'action == "project_start"',
    'action == "project_restart"',
    'action == "safe_update"',
    'PROJECT_ALLOWED_FILES',
    'PROJECT_PROCESS_NAMES',
    'apply-safe-update.ps1',
    'user-owned-vex-project-only',
    'http://127.0.0.1:11434/api/chat',
]
for marker in required:
    if marker not in text:
        raise SystemExit(f"missing marker: {marker}")

# Guardrails: no generic shell command action and no arbitrary path command surface.
for forbidden in [
    'action == "shell"',
    'action == "exec"',
    'action == "run_command"',
    'subprocess.Popen(str(command.get("command")',
]:
    if forbidden in text:
        raise SystemExit(f"forbidden generic command surface present: {forbidden}")

print("v0.11.7.11 project control layer markers verified")
