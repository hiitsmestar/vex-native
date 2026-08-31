#!/usr/bin/env python3
from pathlib import Path
import re
import zipfile

bridge = Path("Bridge/vex_bridge.py").read_text(encoding="utf-8")
remote = Path("Tools/VexRemoteSupport.py").read_text(encoding="utf-8")

assert '"agent_runtime_bundle": "0.11.7.71"' in bridge
assert '"version": "0.11.7.39"' in bridge  # protocol identity stays proven .39
assert 'def _v11771_render_verified_facts(' in bridge
assert 'def _v11771_memory_probe(' in bridge
assert 'def _v11771_art_probe(' in bridge
assert 'include_art=True' in bridge
assert '"pc-memory-facts-v11771"' in bridge
assert 'VERSION = "0.11.7.69"' in remote  # do not regress persistent relay

start = bridge.index('def _verified_personal_memory_reply(')
end = bridge.find('\n\ndef ', start + 10)
reply_fn = bridge[start:end]
assert '"/facts"' in reply_fn, "personal recall must read authoritative /facts"
assert '"/search"' not in reply_fn, "verified foreground recall must not read episodes/search"
assert '_ollama_chat' not in reply_fn and 'OLLAMA_BASE' not in reply_fn, "foreground recall must not wait on Ollama"
assert 'lines.append(f"{index}. {fact}")' not in bridge, "numbered clipboard renderer survived"

render_start = bridge.index('def _v11771_render_verified_facts(')
render_end = bridge.find('\n\ndef ', render_start + 10)
render_fn = bridge[render_start:render_end]
assert 'clean[0]' in render_fn
assert 'intros' in render_fn
assert 'shift = variant % len(clean)' in render_fn, "repeated recall should vary verified fact order"

# The packaged runtime must still contain the separate Memory Worker and current relay.
zip_path = Path('Vex-Agent-Runtime-v0.11.7.71-SelfRepair-NaturalRecall.zip')
assert zip_path.exists(), f"missing package {zip_path}"
with zipfile.ZipFile(zip_path) as zf:
    names = [n.replace('\\', '/') for n in zf.namelist()]
    assert any(n.endswith('/VexMemoryWorker.exe') or n.endswith('VexMemoryWorker.exe') for n in names)
    assert any('VexRemoteSupport' in n and n.endswith('.exe') for n in names)

print('v0.11.7.71 self-repair + grounded recall acceptance tests passed')
