#!/usr/bin/env python3
from __future__ import annotations

import runpy
from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
bridge = BRIDGE.read_text(encoding="utf-8")

# The cumulative assembler can hand this entry point a .79 or .80 Bridge.
# Promote it to the complete v0.12 agent layer first, then apply the routing fix.
if '"agent_runtime_bundle": "0.12.0"' not in bridge:
    runpy.run_path("Tools/apply_v120_full_ai_bootstrap.py", run_name="__main__")
    bridge = BRIDGE.read_text(encoding="utf-8")

if '"agent_runtime_bundle": "0.12.0"' not in bridge:
    raise SystemExit("v0.12.0 conversation entry failed to bootstrap the agent runtime")

runpy.run_path("Tools/apply_v120_conversation_route_fix.py", run_name="__main__")

bridge = BRIDGE.read_text(encoding="utf-8")
for marker in [
    'def _v120_agent_owns_turn(message: str) -> bool:',
    'if _personal_memory_fact_question(message) and not _v120_agent_owns_turn(message):',
    'if _runtime_fact_question(message) and not _v120_agent_owns_turn(message):',
    'RESPONSE CONTRACT FOR THIS TURN',
    'RUNTIME IDENTITY',
]:
    if marker not in bridge:
        raise SystemExit(f"v0.12.0 conversation entry verifier missing: {marker}")

print("Applied self-bootstrapping v0.12 conversation route repair")
