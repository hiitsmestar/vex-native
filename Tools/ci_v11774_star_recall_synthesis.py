#!/usr/bin/env python3
from pathlib import Path

source_path = Path("Tools/ci_v11773_recall_routing_hardening.py")
source = source_path.read_text(encoding="utf-8")

if "0.11.7.73" not in source:
    raise SystemExit("v0.11.7.74 expected .73 build identity missing")
source = source.replace("0.11.7.73", "0.11.7.74")
source = source.replace(
    'Vex-Agent-Runtime-v0.11.7.74-RecallRoutingHardening',
    'Vex-Agent-Runtime-v0.11.7.74-StarRecallSynthesis',
)

anchor = '''        '        \\\"Tools/apply_v11773_recall_routing_hardening.py\\\",\\\\n'\n'''
addition = anchor + '''        '        \\\"Tools/apply_v11774_star_recall_synthesis.py\\\",\\\\n'\n'''
if anchor not in source:
    raise SystemExit("v0.11.7.74 nested .73 patch anchor missing")
source = source.replace(anchor, addition, 1)

globals_dict = {
    "__name__": "__main__",
    "__file__": str(source_path),
    "__package__": None,
}
exec(compile(source, str(source_path) + "[v11774]", "exec"), globals_dict)
