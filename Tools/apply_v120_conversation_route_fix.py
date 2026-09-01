#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
INSTALLER = Path("Tools/VexAgentRuntimeInstall.py")
bridge = BRIDGE.read_text(encoding="utf-8")
installer = INSTALLER.read_text(encoding="utf-8")

for marker in [
    '"agent_runtime_bundle": "0.12.0"',
    'def _v120_agent_chat(',
    'RESPONSE CONTRACT FOR THIS TURN',
    'RUNTIME IDENTITY',
    'def _personal_memory_fact_question(',
    'def _runtime_fact_question(',
]:
    if marker not in bridge:
        raise SystemExit(f"v0.12.0 conversation-route fix expected marker missing: {marker}")
if 'BUNDLE_VERSION = "0.12.0"' not in installer:
    raise SystemExit("v0.12.0 conversation-route fix expected installer bundle identity")

# v0.11.7.49 originally stamped the Agent Runtime identity into only the first
# status payload containing local_control_protocol. The installer probes the
# dedicated local-control listener, whose /status payload can therefore have the
# correct Bridge core version but no bundle identity. Stamp every status payload
# that advertises vex-local-v1, without duplicating an already-correct marker.
status_protocol = '"local_control_protocol": "vex-local-v1",'
bundle_marker = '"agent_runtime_bundle": "0.12.0",'
protocol_count = bridge.count(status_protocol)
if protocol_count < 1:
    raise SystemExit("v0.12.0 local-control status protocol marker missing")
lines = bridge.splitlines(keepends=True)
rebuilt: list[str] = []
for index, line in enumerate(lines):
    rebuilt.append(line)
    if status_protocol not in line:
        continue
    next_line = lines[index + 1] if index + 1 < len(lines) else ""
    if bundle_marker in next_line:
        continue
    indent = line[: len(line) - len(line.lstrip())]
    rebuilt.append(f'{indent}{bundle_marker}\n')
bridge = "".join(rebuilt)
if bridge.count(bundle_marker) < protocol_count:
    raise SystemExit("v0.12.0 could not stamp every local-control status payload with bundle identity")

helper = r'''def _v120_agent_owns_turn(message: str) -> bool:
    """Keep legacy verified shortcuts narrow; give compound/broad conversation to v0.12."""
    text = re.sub(r"\s+", " ", str(message or "")).strip().lower().replace("’", "'")
    if not text:
        return False

    recall_cues = (
        "remember", "memory", "memories", "know about me", "know about us",
        "know me", "tell me about me", "what do you know about me",
    )
    runtime_cues = (
        "running on", "what are you running", "what're you running", "pc brain",
        "brain right now", "which model", "what model", "runtime", "cognition node",
    )
    broad_recall = (
        "tell me something you remember", "tell me what you remember",
        "what do you remember about me", "what do you know about me",
        "tell me about me", "what have you learned about me",
        "what have you got saved about me",
    )

    has_recall = any(cue in text for cue in recall_cues)
    has_runtime = any(cue in text for cue in runtime_cues)
    if any(cue in text for cue in broad_recall):
        return True
    if has_recall and has_runtime:
        return True

    # A conjunction/question boundary around two distinct asks is conversational,
    # even when one clause happens to match a legacy verified shortcut.
    parts = [p.strip(" ,;.!?") for p in re.split(r"(?:\?|;|,?\s+and\s+)", text) if p.strip(" ,;.!?")]
    question_heads = ("what ", "which ", "where ", "who ", "when ", "how ", "do ", "am ", "have ", "did ", "tell ")
    asks = sum(1 for part in parts if part.startswith(question_heads) or " you " in (" " + part + " "))
    return len(parts) >= 2 and asks >= 2 and (has_recall or has_runtime)


'''
agent_anchor = "def _v120_agent_chat("
if "def _v120_agent_owns_turn(message: str) -> bool:" not in bridge:
    pos = bridge.find(agent_anchor)
    if pos < 0:
        raise SystemExit("v0.12.0 conversation-route helper insertion anchor missing")
    bridge = bridge[:pos] + helper + bridge[pos:]

# Legacy memory/runtime shortcuts predate the v0.12 agent. Keep them for truly
# narrow verified lookups, but never let them swallow a compound/broad turn.
if "if _personal_memory_fact_question(message) and not _v120_agent_owns_turn(message):" not in bridge:
    bridge, changed = re.subn(
        r"(?m)^(?P<indent>\s*)if _personal_memory_fact_question\(message\):\s*$",
        r"\g<indent>if _personal_memory_fact_question(message) and not _v120_agent_owns_turn(message):",
        bridge,
        count=1,
    )
    if changed != 1:
        raise SystemExit("v0.12.0 conversation-route could not gate legacy memory shortcut")

if "if _runtime_fact_question(message) and not _v120_agent_owns_turn(message):" not in bridge:
    bridge, changed = re.subn(
        r"(?m)^(?P<indent>\s*)if _runtime_fact_question\(message\):\s*$",
        r"\g<indent>if _runtime_fact_question(message) and not _v120_agent_owns_turn(message):",
        bridge,
        count=1,
    )
    if changed != 1:
        raise SystemExit("v0.12.0 conversation-route could not gate legacy runtime shortcut")

# Installer readiness must prove the agent bundle that the phone will actually hit,
# not merely the long-lived Bridge core protocol/version.
old_ready = '''            if str(value.get("version") or "") == BRIDGE_VERSION and str(value.get("local_control_protocol") or "") == "vex-local-v1":
                return value
'''
new_ready = '''            if (
                str(value.get("version") or "") == BRIDGE_VERSION
                and str(value.get("local_control_protocol") or "") == "vex-local-v1"
                and str(value.get("agent_runtime_bundle") or "") == BUNDLE_VERSION
            ):
                return value
'''
if old_ready in installer:
    installer = installer.replace(old_ready, new_ready, 1)
elif 'str(value.get("agent_runtime_bundle") or "") == BUNDLE_VERSION' not in installer:
    raise SystemExit("v0.12.0 installer bundle-liveness anchor missing")

old_last = '            last = f"unexpected identity {value.get(\'version\')}"\n'
new_last = '            last = f"unexpected identity bridge={value.get(\'version\')} bundle={value.get(\'agent_runtime_bundle\')}"\n'
if old_last in installer:
    installer = installer.replace(old_last, new_last, 1)
elif 'bundle={value.get(\'agent_runtime_bundle\')}' not in installer:
    raise SystemExit("v0.12.0 installer detailed identity diagnostic anchor missing")

# Stop naming a stale phone build in the success dialog. Pairing is what matters.
installer = re.sub(
    r'"Keep VexNative v0\.11\.7\.\d+ on the iPhone; its working PC-routing\\n"\s*\n\s*"pairing is preserved\."',
    '"Keep your current VexNative iPhone app; its working PC-routing\\n"\n            "pairing is preserved."',
    installer,
    count=1,
)

BRIDGE.write_text(bridge, encoding="utf-8")
INSTALLER.write_text(installer, encoding="utf-8")
compile(bridge, str(BRIDGE), "exec")
compile(installer, str(INSTALLER), "exec")

for marker in [
    'def _v120_agent_owns_turn(message: str) -> bool:',
    'if _personal_memory_fact_question(message) and not _v120_agent_owns_turn(message):',
    'if _runtime_fact_question(message) and not _v120_agent_owns_turn(message):',
    '"tell me something you remember"',
]:
    if marker not in bridge:
        raise SystemExit(f"v0.12.0 conversation-route final verifier missing: {marker}")
if bridge.count(bundle_marker) < bridge.count(status_protocol):
    raise SystemExit("v0.12.0 local-control status bundle identity coverage regressed")
if 'str(value.get("agent_runtime_bundle") or "") == BUNDLE_VERSION' not in installer:
    raise SystemExit("v0.12.0 installer no longer proves agent bundle liveness")

print("Applied v0.12.0 conversational routing + local status bundle identity verification")
