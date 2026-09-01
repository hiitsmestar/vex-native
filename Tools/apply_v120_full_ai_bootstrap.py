#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import runpy

BRIDGE = Path("Bridge/vex_bridge.py")
INSTALLER = Path("Tools/VexAgentRuntimeInstall.py")

bridge = BRIDGE.read_text(encoding="utf-8")
installer = INSTALLER.read_text(encoding="utf-8")

# The cumulative production harness currently arrives at .79 before this layer.
# Promote through the proven .80 punctuation-route repair first when needed.
if '"agent_runtime_bundle": "0.11.7.80"' not in bridge:
    if '"agent_runtime_bundle": "0.11.7.79"' not in bridge:
        raise SystemExit("v0.12.0 bootstrap expected cumulative .79 or .80 runtime")
    runpy.run_path("Tools/apply_v11780_memory_route_punctuation_fix.py", run_name="__main__")
    bridge = BRIDGE.read_text(encoding="utf-8")
    installer = INSTALLER.read_text(encoding="utf-8")

if '"agent_runtime_bundle": "0.11.7.80"' not in bridge:
    raise SystemExit("v0.12.0 bootstrap failed to reach .80 Bridge identity")
if 'BUNDLE_VERSION = "0.11.7.80"' not in installer:
    raise SystemExit("v0.12.0 bootstrap failed to reach .80 installer identity")

runpy.run_path("Tools/apply_v120_full_ai_foundation.py", run_name="__main__")
print("Bootstrapped cumulative v0.11.7.80 and applied v0.12.0 Full AI Foundation")
