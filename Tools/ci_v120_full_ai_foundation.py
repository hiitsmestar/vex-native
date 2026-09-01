#!/usr/bin/env python3
from pathlib import Path

source_path = Path("Tools/ci_v11780_memory_route_punctuation_fix.py")
source = source_path.read_text(encoding="utf-8")

if "0.11.7.80" not in source:
    raise SystemExit("v0.12.0 expected .80 build identity missing")

# Keep the inherited .80 assembler/verifier identity intact until its own patch
# has completed.  The v0.12 bootstrap must run after that proven baseline exists;
# globally rewriting .80 to v0.12 makes the inherited Greenline verifier demand
# the v0.12 marker before the v0.12 patch list can execute.
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

# Rename only the packaged artifact/display identity.  Runtime version promotion
# is performed by apply_v120_full_ai_bootstrap via the conversation entry patch.
source = source.replace(
    'Vex-Agent-Runtime-v0.11.7.80-MemoryRoutePunctuationFix',
    'Vex-Agent-Runtime-v0.12.0-FullAIFoundation',
)
source = source.replace(
    'Vex Agent Runtime v0.11.7.80 Memory Route Punctuation Fix',
    'Vex Agent Runtime v0.12.0 Full AI Foundation',
)

globals_dict = {
    "__name__": "__main__",
    "__file__": str(source_path),
    "__package__": None,
}
exec(compile(source, str(source_path) + "[v120]", "exec"), globals_dict)
