#!/usr/bin/env python3
from pathlib import Path

source_path = Path("Tools/ci_v11778_memory_facts_path.py")
source = source_path.read_text(encoding="utf-8")

if "0.11.7.78" not in source:
    raise SystemExit("v0.11.7.79 expected .78 build identity missing")
source = source.replace("0.11.7.78", "0.11.7.79")
source = source.replace(
    'Vex-Agent-Runtime-v0.11.7.79-MemoryFactsPath',
    'Vex-Agent-Runtime-v0.11.7.79-InlineProfileRecall',
)
source = source.replace(
    'Vex Agent Runtime v0.11.7.79 Memory Facts Path Repair',
    'Vex Agent Runtime v0.11.7.79 Inline Profile Recall',
)

anchor = '''        '        \\\"Tools/apply_v11778_memory_facts_path.py\\\",\\\\n'\n'''
addition = anchor + '''        '        \\\"Tools/apply_v11779_inline_profile_recall.py\\\",\\\\n'\n'''
if anchor not in source:
    raise SystemExit("v0.11.7.79 nested .78 patch anchor missing")
source = source.replace(anchor, addition, 1)

globals_dict = {
    "__name__": "__main__",
    "__file__": str(source_path),
    "__package__": None,
}
exec(compile(source, str(source_path) + "[v11779]", "exec"), globals_dict)
