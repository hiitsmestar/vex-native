#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

REMOTE_PATH = Path("Tools/VexRemoteSupport.py")
remote = REMOTE_PATH.read_text(encoding="utf-8")

if 'VERSION = "0.11.7.7"' not in remote:
    raise SystemExit("v0.11.7.8 expected v0.11.7.7 Remote Support source")

remote = re.sub(
    r'^VERSION = "[^"]+"',
    'VERSION = "0.11.7.8"',
    remote,
    count=1,
    flags=re.M,
)

class_anchor = 'class SupportWorker:\n'
helper = r'''def run_remote_chat_command(command: dict, command_id: str, allow_maintenance: bool) -> None:
    """Run model-backed remote chat off the relay polling thread.

    A slow or wedged local cognition request must never stop the support worker from
    polling GitHub, answering diagnostics, or accepting a later recovery command.
    """
    try:
        result = execute_command(command, allow_maintenance=allow_maintenance)
    except Exception as exc:
        result = {
            "remote_chat": {
                "ok": False,
                "error_class": exc.__class__.__name__,
                "source": "remote-technical-partner",
            }
        }
    try:
        post_comment(
            "command_result",
            {
                "command_id": command_id,
                "action": "remote_chat",
                "result": result,
            },
        )
    except Exception:
        pass


'''
if class_anchor not in remote:
    raise SystemExit("v0.11.7.8 SupportWorker anchor missing")
remote = remote.replace(class_anchor, helper + class_anchor, 1)

old = '''                    self.on_status(f"Running {str(command.get('action') or 'command')}…")
                    result = execute_command(command, allow_maintenance=bool(self.allow_maintenance()))
                    post_comment("command_result", {"command_id": command_id, "action": str(command.get("action") or "")[:80], "result": result})
                    self.on_status("Support session is active")
'''
new = '''                    action = str(command.get("action") or "").strip().lower()
                    self.on_status(f"Running {action or 'command'}…")
                    if action == "remote_chat":
                        threading.Thread(
                            target=run_remote_chat_command,
                            args=(command, command_id, bool(self.allow_maintenance())),
                            daemon=True,
                            name=f"VexRemoteChat-{command_id[:24]}",
                        ).start()
                        post_comment(
                            "command_accepted",
                            {
                                "command_id": command_id,
                                "action": "remote_chat",
                                "status": "running",
                            },
                        )
                        self.on_status("Remote chat running; support session remains active")
                        continue
                    result = execute_command(command, allow_maintenance=bool(self.allow_maintenance()))
                    post_comment("command_result", {"command_id": command_id, "action": action[:80], "result": result})
                    self.on_status("Support session is active")
'''
if old not in remote:
    raise SystemExit("v0.11.7.8 command loop anchor missing")
remote = remote.replace(old, new, 1)

REMOTE_PATH.write_text(remote, encoding="utf-8")
compile(remote, str(REMOTE_PATH), "exec")

checks = [
    'VERSION = "0.11.7.8"',
    "def run_remote_chat_command(",
    'if action == "remote_chat"',
    '"command_accepted"',
    '"Remote chat running; support session remains active"',
    "for page in range(1, 101)",
]
final = REMOTE_PATH.read_text(encoding="utf-8")
for marker in checks:
    if marker not in final:
        raise SystemExit(f"v0.11.7.8 verifier missing: {marker}")

print("Applied v0.11.7.8 non-blocking remote chat worker fix")
