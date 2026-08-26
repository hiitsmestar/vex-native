#!/usr/bin/env python3
from pathlib import Path

path = Path("Tools/VexRemoteSupport.py")
text = path.read_text(encoding="utf-8")

required = [
    'VERSION = "0.11.7.8"',
    'def run_remote_chat_command(',
    'if action == "remote_chat"',
    'target=run_remote_chat_command',
    '"command_accepted"',
    '"status": "running"',
    'Remote chat running; support session remains active',
    'for page in range(1, 101)',
]
for marker in required:
    if marker not in text:
        raise SystemExit(f"missing v0.11.7.8 marker: {marker}")

start = text.index('if action == "remote_chat":', text.index('class SupportWorker:'))
window = text[start:start + 1800]
if 'threading.Thread(' not in window:
    raise SystemExit('remote_chat is not dispatched on a background thread')
if 'continue' not in window:
    raise SystemExit('relay loop does not continue after dispatching remote_chat')

compile(text, str(path), "exec")
print("v0.11.7.8 non-blocking remote chat worker tests passed")
