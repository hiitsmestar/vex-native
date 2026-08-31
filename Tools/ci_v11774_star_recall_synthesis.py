#!/usr/bin/env python3
from pathlib import Path

source_path = Path("Tools/ci_v11771_self_repair_natural_recall.py")
source = source_path.read_text(encoding="utf-8")

if "0.11.7.71" not in source:
    raise SystemExit("v0.11.7.74 expected .71 build identity missing")
source = source.replace("0.11.7.71", "0.11.7.74")
source = source.replace(
    'Vex-Agent-Runtime-v0.11.7.74-SelfRepair-NaturalRecall',
    'Vex-Agent-Runtime-v0.11.7.74-StarRecallSynthesis',
)
source = source.replace(
    'Vex Agent Runtime v0.11.7.74 Self Repair + Natural Grounded Recall',
    'Vex Agent Runtime v0.11.7.74 Star Recall Synthesis',
)

# Use the exact embedded patch-list representation already proven by the green
# .73 build harness, then append only the new .74 patch.
anchor = '''        '        \\\"Tools/apply_v11771_self_repair_natural_recall.py\\\",\\\\n'\n'''
addition = anchor + '''        '        \\\"Tools/apply_v11772_installer_remote_handoff.py\\\",\\\\n'\n        '        \\\"Tools/apply_v11773_recall_routing_hardening.py\\\",\\\\n'\n        '        \\\"Tools/apply_v11774_star_recall_synthesis.py\\\",\\\\n'\n'''
if anchor not in source:
    raise SystemExit("v0.11.7.74 nested .71 patch anchor missing")
source = source.replace(anchor, addition, 1)

globals_dict = {
    "__name__": "__main__",
    "__file__": str(source_path),
    "__package__": None,
}
exec(compile(source, str(source_path) + "[v11774]", "exec"), globals_dict)
