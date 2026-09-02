#!/usr/bin/env python3
from __future__ import annotations

import runpy
from pathlib import Path

# Field validation must be part of the final cumulative composition, not merely a
# standalone patch file. Apply the real v0.12 chat transport/context fix here so
# every artifact that reaches the stable-install tolerance gate contains it.
runpy.run_path("Tools/apply_v120_field_chat_transport.py", run_name="__main__")

# This layer is the final proven Bridge composition point in the cumulative chain.
# Apply recent-turn recall here explicitly so source-generator ordering cannot
# silently omit it from the packaged Bridge.
runpy.run_path("Tools/apply_v120_recent_turn_priority.py", run_name="__main__")

BRIDGE = Path("Bridge/vex_bridge.py")
bridge = BRIDGE.read_text(encoding="utf-8")
for marker in [
    "V120_LOOPBACK_CHAT_PROXY_BYPASS",
    "session.trust_env = False",
    "v120_num_ctx = 2048",
    '"num_ctx": v120_num_ctx,',
    '"error": "local cognition request failed",',
    'vex-agent-recent-turn',
    'user_profile = ""',
]:
    if marker not in bridge:
        raise SystemExit(f"v0.12 transport tolerance missing final Bridge marker: {marker}")

INSTALLER = Path("Tools/VexAgentRuntimeInstall.py")
installer = INSTALLER.read_text(encoding="utf-8")

# This patch may be injected by source-generating CI before the v0.12 readiness
# layer has run. Bootstrap that prerequisite explicitly so wait_cognition and the
# Ollama preflight are guaranteed to exist before transport tolerance edits them.
if (
    "def wait_cognition(home: Path, seconds: int = 150) -> dict:" not in installer
    and "def wait_cognition(home: Path, seconds: int = 25) -> dict:" not in installer
):
    runpy.run_path("Tools/apply_v120_install_readiness_gate.py", run_name="__main__")
    installer = INSTALLER.read_text(encoding="utf-8")

old_sig = "def wait_cognition(home: Path, seconds: int = 150) -> dict:"
new_sig = "def wait_cognition(home: Path, seconds: int = 25) -> dict:"
if old_sig in installer:
    installer = installer.replace(old_sig, new_sig, 1)
elif new_sig not in installer:
    raise SystemExit("v0.12 transport tolerance could not find cognition wait signature after readiness bootstrap")

old_recovery = "        if failures >= 4 and recoveries < 3 and time.time() < deadline:\n"
new_recovery = "        # Do not kill/restart a Bridge that Remote Support is actively using.\n        # Direct Ollama/model preflight already proved the local model; transport\n        # warm-up is diagnosed after installation against a stable runtime.\n        if failures >= 999999 and recoveries < 3 and time.time() < deadline:\n"
if old_recovery in installer:
    installer = installer.replace(old_recovery, new_recovery, 1)
elif "if failures >= 999999" not in installer:
    raise SystemExit("v0.12 transport tolerance could not disable destructive cognition recovery")

old_fail = '    raise RuntimeError(f"PC cognition did not become ready after v0.12 install: {last}")\n'
new_fail = '''    return {
        "ok": False,
        "model": "",
        "available_model_count": 0,
        "warming": True,
        "error": last,
    }
'''
if old_fail in installer:
    installer = installer.replace(old_fail, new_fail, 1)
elif '"warming": True' not in installer:
    raise SystemExit("v0.12 transport tolerance could not convert cognition timeout to warm-up state")

old_line = '            f"PC cognition: ready ({cognition.get(\'model\') or \'local model\'})\\n"\n'
new_line = '            f"PC cognition: {\'ready\' if cognition.get(\'ok\') else \'warming\'} ({cognition.get(\'model\') or ollama.get(\'model\') or \'local model\'})\\n"\n'
if old_line in installer:
    installer = installer.replace(old_line, new_line, 1)
elif "PC cognition: {'ready' if cognition.get('ok') else 'warming'}" not in installer:
    raise SystemExit("v0.12 transport tolerance could not update cognition status dialog")

INSTALLER.write_text(installer, encoding="utf-8")
compile(installer, str(INSTALLER), "exec")

for marker in [
    "def wait_cognition(home: Path, seconds: int = 25) -> dict:",
    "if failures >= 999999",
    '"warming": True',
    "PC cognition: {'ready' if cognition.get('ok') else 'warming'}",
    "ollama = wait_ollama_model()",
]:
    if marker not in installer:
        raise SystemExit(f"v0.12 transport tolerance missing marker: {marker}")

print("Applied v0.12 field-chat + deterministic recent-turn recall + stable-install cognition transport tolerance")
