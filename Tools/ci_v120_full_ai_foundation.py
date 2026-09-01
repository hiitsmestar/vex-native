#!/usr/bin/env python3
from pathlib import Path

source_path = Path("Tools/ci_v11780_memory_route_punctuation_fix.py")
source = source_path.read_text(encoding="utf-8")

if "0.11.7.80" not in source:
    raise SystemExit("v0.12.0 expected .80 build identity missing")

# ci_v11780 is source-generating source. Find the actual nested .80 patch line
# instead of depending on its exact escape spelling, then append the v0.12 layers
# in the required order. This is the same line-based composition strategy that
# produced the previously green v0.12 build, with the readiness gate last.
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
resilience_line = base_line.replace(
    "Tools/apply_v11780_memory_route_punctuation_fix.py",
    "Tools/apply_v120_cognition_model_resilience.py",
)
readiness_line = base_line.replace(
    "Tools/apply_v11780_memory_route_punctuation_fix.py",
    "Tools/apply_v120_install_readiness_gate.py",
)
lines[index + 1:index + 1] = [entry_line, lock_line, resilience_line, readiness_line]
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
