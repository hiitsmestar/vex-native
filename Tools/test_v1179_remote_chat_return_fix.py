#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "Bridge" / "vex_bridge.py"
REMOTE = ROOT / "Tools" / "VexRemoteSupport.py"

bridge = BRIDGE.read_text(encoding="utf-8")
remote = REMOTE.read_text(encoding="utf-8")

required_bridge = [
    '"version": "0.11.7.9"',
    'def _remote_partner_chat(',
    'parsed.path == "/llm/remote-chat"',
    'timeout=(3.0, 70.0)',
    '"num_predict": 320',
    '"grounding": "remote-technical-direct-v1179"',
    'parsed.path == "/llm/chat"',
]
required_remote = [
    'VERSION = "0.11.7.9"',
    'bridge_post("/llm/remote-chat"',
    'timeout=85',
    'def run_remote_chat_command(',
    '"command_accepted"',
    'for page in range(1, 101)',
]

for marker in required_bridge:
    assert marker in bridge, f"Bridge marker missing: {marker}"
for marker in required_remote:
    assert marker in remote, f"Remote marker missing: {marker}"

# The remote-only route must be bounded and must not inherit the full foreground
# memory/research stack. It should call Ollama directly and return one compact reply.
start = bridge.index('def _remote_partner_chat(')
end = bridge.index('\n\ndef ', start + 5)
func = bridge[start:end]
assert 'OLLAMA_BASE' in func
assert '/api/chat' in func
assert 'stream' in func and 'False' in func
assert 'num_predict' in func
assert '70.0' in func
assert '_memory_' not in func
assert 'web_search(' not in func

print("v0.11.7.9 remote chat return-path source checks passed")
