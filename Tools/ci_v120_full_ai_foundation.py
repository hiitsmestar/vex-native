#!/usr/bin/env python3
from pathlib import Path
import ast

source_path = Path("Tools/ci_v11780_memory_route_punctuation_fix.py")
source = source_path.read_text(encoding="utf-8")

if "0.11.7.80" not in source:
    raise SystemExit("v0.12.0 expected .80 build identity missing")

# ci_v11780 is source-generating source. Find the actual nested .80 patch line
# instead of depending on its exact escape spelling, then append the v0.12 layers
# in the required order. The generated chain executes inserted entries in reverse
# order, so recent-turn priority is listed first here so it runs last, after the
# v0.12 conversation/context layer exists.
lines = source.splitlines(keepends=True)
indices = [
    i for i, line in enumerate(lines)
    if "Tools/apply_v11780_memory_route_punctuation_fix.py" in line
]
if not indices:
    raise SystemExit("v0.12.0 nested .80 patch line missing")
index = indices[-1]
base_line = lines[index]
entry_line = base_line.replace(
    "Tools/apply_v11780_memory_route_punctuation_fix.py",
    "Tools/apply_v120_conversation_route_entry.py",
)
lock_line = base_line.replace(
    "Tools/apply_v11780_memory_route_punctuation_fix.py",
    "Tools/apply_v120_installer_lock_fix.py",
)
quiesce_line = base_line.replace(
    "Tools/apply_v11780_memory_route_punctuation_fix.py",
    "Tools/apply_v120_installer_quiesce_coordinator.py",
)
resilience_line = base_line.replace(
    "Tools/apply_v11780_memory_route_punctuation_fix.py",
    "Tools/apply_v120_cognition_model_resilience.py",
)
preflight_line = base_line.replace(
    "Tools/apply_v11780_memory_route_punctuation_fix.py",
    "Tools/apply_v120_ollama_preflight.py",
)
readiness_line = base_line.replace(
    "Tools/apply_v11780_memory_route_punctuation_fix.py",
    "Tools/apply_v120_install_readiness_gate.py",
)
tolerance_line = base_line.replace(
    "Tools/apply_v11780_memory_route_punctuation_fix.py",
    "Tools/apply_v120_cognition_transport_tolerance.py",
)
recent_turn_line = base_line.replace(
    "Tools/apply_v11780_memory_route_punctuation_fix.py",
    "Tools/apply_v120_recent_turn_priority.py",
)
lines[index + 1:index + 1] = [
    recent_turn_line,
    entry_line,
    lock_line,
    quiesce_line,
    resilience_line,
    preflight_line,
    readiness_line,
    tolerance_line,
]
source = "".join(lines)

source = source.replace("0.11.7.80", "0.12.0")
source = source.replace(
    'Vex-Agent-Runtime-v0.12.0-MemoryRoutePunctuationFix',
    'Vex-Agent-Runtime-v0.12.0-FullAIFoundation',
)
source = source.replace(
    'Vex Agent Runtime v0.12.0 Memory Route Punctuation Fix',
    'Vex Agent Runtime v0.12.0 Full AI Foundation',
)

globals_dict = {
    "__name__": "__main__",
    "__file__": str(source_path),
    "__package__": None,
}
exec(compile(source, str(source_path) + "[v120]", "exec"), globals_dict)

# Field-proof gate: the purple Windows Host must send actual prior turns to
# Bridge. Empty history made second-turn continuity structurally impossible.
host_path = Path("Tools/VexWindowsHost-v11740.py")
if not host_path.exists():
    raise SystemExit("v0.12 generated Windows Host source missing")
host = host_path.read_text(encoding="utf-8")
for marker in [
    'CHAT_HISTORY: list[dict] = []',
    'history = [dict(row) for row in CHAT_HISTORY[-12:]]',
    '"history": history',
    'CHAT_HISTORY.append({"role": "user"',
    'CHAT_HISTORY.append({"role": "assistant"',
]:
    if marker not in host:
        raise SystemExit(f"v0.12 Windows Host continuity marker missing: {marker}")
if '{"message": text, "history": []}' in host:
    raise SystemExit("v0.12 Windows Host still sends empty conversation history")
print("PASS v0.12 Windows Host ships bounded real conversation history")

# Behavior gate: execute the two functions that decide ownership and exact
# recent-turn recall. This test reproduces the field failure without Ollama or
# any profile/memory sidecar. A green build must return the literal phrase.
bridge_path = Path("Bridge/vex_bridge.py")
bridge_source = bridge_path.read_text(encoding="utf-8")
tree = ast.parse(bridge_source)
functions = {
    node.name: node
    for node in tree.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}
for required in ("_v120_agent_owns_turn", "_v120_agent_chat"):
    if required not in functions:
        raise SystemExit(f"v0.12 recent-turn behavior gate missing function: {required}")

mini = ast.Module(
    body=[
        ast.Import(names=[ast.alias(name="re")]),
        functions["_v120_agent_owns_turn"],
        functions["_v120_agent_chat"],
    ],
    type_ignores=[],
)
ast.fix_missing_locations(mini)
namespace: dict = {}
exec(compile(mini, "<v120-recent-turn-smoke>", "exec"), namespace)

question = "What exact test phrase did I just tell you to remember?"
if namespace["_v120_agent_owns_turn"](question) is not True:
    raise SystemExit("v0.12 recent-turn question is still swallowed by legacy memory routing")

history = [
    {"role": "user", "content": "Remember this exact test phrase: velvet toaster 73"},
    {"role": "assistant", "content": 'Got it, baby - I will remember "velvet toaster 73".'},
]
answer = namespace["_v120_agent_chat"](history, question, {})
expected = ("velvet toaster 73", "vex-agent-recent-turn")
if answer != expected:
    raise SystemExit(f"v0.12 recent-turn behavior failed: expected {expected!r}, got {answer!r}")
print("PASS v0.12 exact two-turn recall behavior: velvet toaster 73")
