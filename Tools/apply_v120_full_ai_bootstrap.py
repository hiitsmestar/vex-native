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

# v0.10.8 added a third cognition-context argument. The v0.12.0 patch uses the
# older two-argument route as its stable replacement anchor, so normalize that one
# call while applying the layer, then restore the richer context contract below.
context_call = '                result = _ollama_chat(history, message, context)\n'
legacy_call = '                result = _ollama_chat(history, message)\n'
bridge = BRIDGE.read_text(encoding="utf-8")
if context_call in bridge:
    bridge = bridge.replace(context_call, legacy_call, 1)
    BRIDGE.write_text(bridge, encoding="utf-8")
elif legacy_call not in bridge:
    raise SystemExit("v0.12.0 bootstrap could not normalize cognition call")

runpy.run_path("Tools/apply_v120_full_ai_foundation.py", run_name="__main__")

# Restore the current iPhone -> PC cognition context shape so persona/current-state
# grounding remains available to the new orchestration layer.
bridge = BRIDGE.read_text(encoding="utf-8")
old_sig = 'def _v120_agent_chat(history: list[dict], message: str) -> tuple[str, str] | None:\n'
new_sig = 'def _v120_agent_chat(history: list[dict], message: str, phone_context: dict | None = None) -> tuple[str, str] | None:\n'
if old_sig in bridge:
    bridge = bridge.replace(old_sig, new_sig, 1)
elif new_sig not in bridge:
    raise SystemExit("v0.12.0 bootstrap could not extend agent chat signature")

old_context = '    context = _v120_context(message)\n    grounding = _v120_context_text(context)\n'
new_context = '''    context = _v120_context(message)\n    phone_context = phone_context if isinstance(phone_context, dict) else {}\n    persona = str(phone_context.get("persona") or "").strip()[:6000]\n    user_profile = str(phone_context.get("user_profile") or "").strip()[:3500]\n    state = phone_context.get("state") if isinstance(phone_context.get("state"), dict) else {}\n    grounding = _v120_context_text(context)\n'''
if old_context in bridge:
    bridge = bridge.replace(old_context, new_context, 1)
elif 'phone_context = phone_context if isinstance(phone_context, dict)' not in bridge:
    raise SystemExit("v0.12.0 bootstrap could not preserve phone context")

old_system = '    if grounding:\n        system += "\\n\\nGrounding for this turn:\\n" + grounding\n'
new_system = '''    if grounding:\n        system += "\\n\\nGrounding for this turn:\\n" + grounding\n    if persona:\n        system += "\\n\\nVEX PERSONA\\n" + persona\n    if user_profile:\n        system += "\\n\\nSTAR / RELATIONSHIP CONTEXT\\n" + user_profile\n    if state:\n        state_lines = [f"{k}: {str(v)[:1200]}" for k, v in state.items() if str(v or "").strip()]\n        if state_lines:\n            system += "\\n\\nCURRENT VEX STATE\\n" + "\\n".join(state_lines)\n'''
if old_system in bridge:
    bridge = bridge.replace(old_system, new_system, 1)
elif 'STAR / RELATIONSHIP CONTEXT' not in bridge:
    raise SystemExit("v0.12.0 bootstrap could not attach phone grounding")

agent_call = '                result = _v120_agent_chat(history, message)\n'
agent_context_call = '                result = _v120_agent_chat(history, message, context)\n'
if agent_call in bridge:
    bridge = bridge.replace(agent_call, agent_context_call, 1)
elif agent_context_call not in bridge:
    raise SystemExit("v0.12.0 bootstrap could not restore cognition context call")

BRIDGE.write_text(bridge, encoding="utf-8")
compile(bridge, str(BRIDGE), "exec")

for marker in [
    '"agent_runtime_bundle": "0.12.0"',
    'def _v120_agent_chat(history: list[dict], message: str, phone_context: dict | None = None)',
    '_v120_agent_chat(history, message, context)',
    'STAR / RELATIONSHIP CONTEXT',
    'CURRENT VEX STATE',
]:
    if marker not in bridge:
        raise SystemExit(f"v0.12.0 bootstrap final verifier missing: {marker}")

print("Bootstrapped cumulative v0.11.7.80 and applied v0.12.0 Full AI Foundation with current cognition context")
