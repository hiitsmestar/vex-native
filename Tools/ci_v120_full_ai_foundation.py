#!/usr/bin/env python3
from pathlib import Path

source_path = Path("Tools/ci_v11780_memory_route_punctuation_fix.py")
source = source_path.read_text(encoding="utf-8")

if "0.11.7.80" not in source:
    raise SystemExit("v0.12.0 expected .80 build identity missing")

# The .80 harness is source-generating source and mentions its patch more than once.
# Keep the nested cumulative additions for the .80 recall path and installer hardening.
lines = source.splitlines(keepends=True)
indices = [i for i, line in enumerate(lines) if "Tools/apply_v11780_memory_route_punctuation_fix.py" in line]
if not indices:
    raise SystemExit("v0.12.0 nested .80 patch line missing")
index = indices[-1]
entry_line = lines[index].replace(
    "Tools/apply_v11780_memory_route_punctuation_fix.py",
    "Tools/apply_v120_conversation_route_entry.py",
)
lock_line = lines[index].replace(
    "Tools/apply_v11780_memory_route_punctuation_fix.py",
    "Tools/apply_v120_installer_lock_fix.py",
)
lines.insert(index + 1, entry_line)
lines.insert(index + 2, lock_line)
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

# ci_v11749_greenline verifies the Agent Runtime marker immediately after its
# top-level assemble_source() script list runs.  Source-version substitution turns
# that verifier into a v0.12.0 check, so the v0.12 bootstrap must be in that exact
# top-level list, not only in a nested generated patch list.
assembler_anchor = '        "Tools/apply_v11749_agent_runtime_foundation.py",\n'
assembler_addition = assembler_anchor + '        "Tools/apply_v120_conversation_route_entry.py",\n'
if assembler_anchor not in source:
    raise SystemExit("v0.12.0 top-level assembler anchor missing")
if '        "Tools/apply_v120_conversation_route_entry.py",\n' not in source:
    source = source.replace(assembler_anchor, assembler_addition, 1)


globals_dict = {
    "__name__": "__main__",
    "__file__": str(source_path),
    "__package__": None,
}
exec(compile(source, str(source_path) + "[v120]", "exec"), globals_dict)
