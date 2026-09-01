#!/usr/bin/env python3
from pathlib import Path

source_path = Path("Tools/ci_v11780_memory_route_punctuation_fix.py")
source = source_path.read_text(encoding="utf-8")

if "0.11.7.80" not in source:
    raise SystemExit("v0.12.0 expected .80 build identity missing")

# The .80 harness itself is source-generating source. Clone its exact nested patch
# line rather than depending on brittle hand-counted escaping.
lines = source.splitlines(keepends=True)
inserted = False
for index, line in enumerate(list(lines)):
    if "Tools/apply_v11780_memory_route_punctuation_fix.py" in line:
        lines.insert(index + 1, line.replace(
            "Tools/apply_v11780_memory_route_punctuation_fix.py",
            "Tools/apply_v120_full_ai_foundation.py",
        ))
        inserted = True
        break
if not inserted:
    raise SystemExit("v0.12.0 nested .80 patch line missing")
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
