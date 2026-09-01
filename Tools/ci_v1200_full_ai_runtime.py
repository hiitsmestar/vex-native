#!/usr/bin/env python3
from pathlib import Path

source_path = Path("Tools/ci_v11771_self_repair_natural_recall.py")
source = source_path.read_text(encoding="utf-8")

if "0.11.7.71" not in source:
    raise SystemExit("v0.12.0 expected .71 build identity missing")
source = source.replace("0.11.7.71", "0.12.0")
source = source.replace(
    'Vex-Agent-Runtime-v0.12.0-SelfRepair-NaturalRecall',
    'Vex-Agent-Runtime-v0.12.0-FullAI',
)
source = source.replace(
    'Vex Agent Runtime v0.12.0 Self Repair + Natural Grounded Recall',
    'Vex Agent Runtime v0.12.0 Full AI',
)

anchor = '''        '        \\\"Tools/apply_v11771_self_repair_natural_recall.py\\\",\\\\n'\n'''
addition = anchor + '''        '        \\\"Tools/apply_v11772_installer_remote_handoff.py\\\",\\\\n'\n        '        \\\"Tools/apply_v11773_recall_routing_hardening.py\\\",\\\\n'\n        '        \\\"Tools/apply_v11774_star_recall_synthesis.py\\\",\\\\n'\n        '        \\\"Tools/apply_v11775_star_memory_query.py\\\",\\\\n'\n        '        \\\"Tools/apply_v11776_windows_app_broker.py\\\",\\\\n'\n        '        \\\"Tools/apply_v11777_window_control_broker.py\\\",\\\\n'\n        '        \\\"Tools/apply_v11778_memory_facts_path.py\\\",\\\\n'\n        '        \\\"Tools/apply_v11779_inline_profile_recall.py\\\",\\\\n'\n        '        \\\"Tools/apply_v11780_memory_route_punctuation_fix.py\\\",\\\\n'\n        '        \\\"Tools/apply_v1200_full_ai_runtime.py\\\",\\\\n'\n'''
if anchor not in source:
    raise SystemExit("v0.12.0 nested .71 patch anchor missing")
source = source.replace(anchor, addition, 1)

globals_dict = {
    "__name__": "__main__",
    "__file__": str(source_path),
    "__package__": None,
}
exec(compile(source, str(source_path) + "[v1200]", "exec"), globals_dict)
