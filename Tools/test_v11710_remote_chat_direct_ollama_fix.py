#!/usr/bin/env python3
from pathlib import Path

remote = Path('Tools/VexRemoteSupport.py').read_text(encoding='utf-8')
required = [
    'VERSION = "0.11.7.10"',
    'http://127.0.0.1:11434/api/tags',
    'http://127.0.0.1:11434/api/chat',
    'remote-technical-direct-ollama-v11710',
    'if action == "remote_chat"',
    '"command_accepted"',
    'for page in range(1, 101)',
]
for marker in required:
    if marker not in remote:
        raise SystemExit(f'missing marker: {marker}')
if 'bridge_post("/llm/remote-chat"' in remote:
    raise SystemExit('stale Bridge remote-chat route still present')
print('v0.11.7.10 direct Ollama remote-chat static checks passed')
