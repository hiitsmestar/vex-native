#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

# Build .74 directly from the proven .71 production assembler, preserving the
# full autonomous-learning/remote-support chain and appending .72-.74 in order.
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

anchor = """        '        \\"Tools/apply_v11774_self_repair_natural_recall.py\\",\\n'
"""
# The global version replacement above renames the .71 patch reference inside
# the embedded patch list. Restore the actual .71 patch file and append .72-.74.
replacement = """        '        \\"Tools/apply_v11771_self_repair_natural_recall.py\\",\\n'
        '        \\"Tools/apply_v11772_installer_remote_handoff.py\\",\\n'
        '        \\"Tools/apply_v11773_recall_routing_hardening.py\\",\\n'
        '        \\"Tools/apply_v11774_star_recall_synthesis.py\\",\\n'
"""
if anchor not in source:
    raise SystemExit("v0.11.7.74 embedded .71 patch anchor missing")
source = source.replace(anchor, replacement, 1)

# .57 remains the Windows-native/autolearn implementation identity.
source = source.replace('native.get("version") == "0.11.7.74"', 'native.get("version") == "0.11.7.57"')
source = source.replace('autolearn.get("version") == "0.11.7.53"', 'autolearn.get("version") == "0.11.7.57"')

globals_dict = {
    "__name__": "__main__",
    "__file__": str(source_path),
    "__package__": None,
}
exec(compile(source, str(source_path) + "[v11774]", "exec"), globals_dict)
