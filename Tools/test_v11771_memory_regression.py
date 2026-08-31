#!/usr/bin/env python3
from pathlib import Path
import zipfile

bridge = Path("Bridge/vex_bridge.py").read_text(encoding="utf-8")

assert '"agent_runtime_bundle": "0.11.7.71"' in bridge
assert "MEMORY_WORKER_BASE" in bridge
assert "def _memory_worker_health(" in bridge
assert "def _memory_post(" in bridge
assert 'parsed.path == "/memory/status"' in bridge
assert "def _verified_personal_memory_reply(" in bridge

start = bridge.index("def _verified_personal_memory_reply(")
end = bridge.find("\n\ndef ", start + 10)
reply_fn = bridge[start:end]
assert '"/facts"' in reply_fn
assert '"/search"' not in reply_fn

# The production assembler already launches the real staged and packaged memory
# sidecar and verifies /health. This regression check guards the source wiring and
# makes sure the standalone worker executable is present in the final artifact.
worker_exe = Path("dist/VexMemoryWorker/VexMemoryWorker.exe")
assert worker_exe.exists(), f"missing memory worker executable: {worker_exe}"

zip_path = Path("Vex-Agent-Runtime-v0.11.7.71-SelfRepair-NaturalRecall.zip")
assert zip_path.exists(), f"missing runtime package: {zip_path}"
with zipfile.ZipFile(zip_path) as zf:
    names = [n.replace("\\", "/") for n in zf.namelist()]
    assert any(n.endswith("VexMemoryWorker.exe") for n in names), "packaged memory worker missing"
    assert any(n.endswith("VexBridge.exe") for n in names), "packaged Bridge missing"
    assert any(n.endswith("Install-Vex-Agent-Runtime-v0.11.7.71.exe") for n in names), "packaged installer missing"

print("v0.11.7.71 memory regression coverage passed")
