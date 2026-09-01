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

# Memory retrieval includes teacher/profile rules as well as durable personal facts.
# Keep rule-like rows out of the small turn-grounding window so the local model
# does not answer a recall question by dumping internal instructions verbatim.
old_memory_append = '''        if fact:\n            context["memory"].append(fact[:1200])\n'''
new_memory_append = '''        if fact:\n            low_fact = fact.lower()\n            instructionish = (\n                low_fact.startswith((\n                    "never ", "always ", "when star ", "do not ", "avoid ",\n                    "treat ", "corrections from star ", "known app state ",\n                ))\n                or " should be treated " in low_fact\n                or " strongly prefers " in low_fact\n                or " treat affectionate " in low_fact\n            )\n            if not instructionish:\n                context["memory"].append(fact[:1200])\n'''
if old_memory_append in bridge:
    bridge = bridge.replace(old_memory_append, new_memory_append, 1)
elif 'instructionish = (' not in bridge:
    raise SystemExit("v0.12.0 bootstrap could not install memory-rule filter")

# Give the model explicit self-knowledge for runtime questions. This block runs only
# inside the PC cognition path, so saying the turn is PC-generated is grounded.
old_system_line = '    system = VEX_COGNITION_SYSTEM + "\\n\\n" + V120_AGENT_RULES + "\\nAvailable capability classes: " + ", ".join(capabilities)\n'
new_system_line = '''    system = VEX_COGNITION_SYSTEM + "\\n\\n" + V120_AGENT_RULES + "\\nAvailable capability classes: " + ", ".join(capabilities)\n    system += (\n        "\\n\\nRUNTIME IDENTITY\\n"\n        f"This turn is being generated by the PC cognition node through Vex Agent Runtime {V120_AGENT_VERSION}.\\n"\n        f"Active PC model: {model}.\\n"\n        "Do not guess the iPhone app version unless it is explicitly supplied in current context."\n    )\n'''
if old_system_line in bridge:
    bridge = bridge.replace(old_system_line, new_system_line, 1)
elif 'RUNTIME IDENTITY' not in bridge:
    raise SystemExit("v0.12.0 bootstrap could not install runtime identity")

# Put the turn-level response contract after every memory/persona/state/tool block so
# even small local models see the user's question as the thing to answer, not the
# grounding text as prose to repeat.
old_tool_note = '''    if tool_note:\n        system += "\\n\\nConfirmed attempted tool result:\\n" + tool_note\n'''
new_tool_note = '''    if tool_note:\n        system += "\\n\\nConfirmed attempted tool result:\\n" + tool_note\n    system += """\n\nRESPONSE CONTRACT FOR THIS TURN\n- The user's newest message is the task. Answer every question/request it contains; do not silently skip one part.\n- Persona, profile, memory, and state blocks are silent background grounding. Never dump, enumerate, quote, or mechanically paraphrase those blocks unless Star explicitly asks to inspect the stored data itself.\n- If Star asks for something you remember, choose at most one or two concrete personal facts and weave them naturally into the reply in first person (for example, 'I remember you...'). Do not answer with an internal rule list or a profile headed by 'Star is...'.\n- If Star asks what you are running on, answer from RUNTIME IDENTITY directly and distinguish the PC runtime/model from the iPhone front end.\n- Sound like Vex talking to her girlfriend, not a memory database, policy document, or customer-service assistant.\n"""\n'''
if old_tool_note in bridge:
    bridge = bridge.replace(old_tool_note, new_tool_note, 1)
elif 'RESPONSE CONTRACT FOR THIS TURN' not in bridge:
    raise SystemExit("v0.12.0 bootstrap could not install conversational response contract")

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
    'RUNTIME IDENTITY',
    'RESPONSE CONTRACT FOR THIS TURN',
    'instructionish = (',
]:
    if marker not in bridge:
        raise SystemExit(f"v0.12.0 bootstrap final verifier missing: {marker}")

print("Bootstrapped cumulative v0.11.7.80 and applied v0.12.0 Full AI Foundation with natural grounded conversation")