#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

# Build .71 from the same proven .54 production assembler used through .57.
# Carry the complete autonomous-learning chain, the field-proven persistent .69
# Remote Support relay, then apply only the self-proposed .71 repair/renderer patch.
source_path = Path("Tools/ci_v11754_windows_native_autolearn_remote.py")
source = source_path.read_text(encoding="utf-8")

if "0.11.7.54" not in source:
    raise SystemExit("v0.11.7.71 expected .54 assembler identity missing")
source = source.replace("0.11.7.54", "0.11.7.71")

source = source.replace(
    'Vex-Agent-Runtime-v0.11.7.71-WindowsNative-AutolearnRemote',
    'Vex-Agent-Runtime-v0.11.7.71-SelfRepair-NaturalRecall',
)
source = source.replace(
    'Vex Agent Runtime v0.11.7.71 Windows Native + Autolearn Remote',
    'Vex Agent Runtime v0.11.7.71 Self Repair + Natural Grounded Recall',
)

patch_anchor = """        '        \"Tools/apply_v11754_installer_self_home_hotfix.py\",\\n'
"""
patch_new = patch_anchor + """        '        \"Tools/apply_v11755_cortana_inspired_learning_guard.py\",\\n'
        '        \"Tools/apply_v11756_remote_doctor_startup_probe_hotfix.py\",\\n'
        '        \"Tools/apply_v11757_autonomous_research_evidence_loop.py\",\\n'
        '        \"Tools/apply_v11758_remote_relay_tail_pagination.py\",\\n'
        '        \"Tools/apply_v11759_remote_command_ledger.py\",\\n'
        '        \"Tools/apply_v11760_remote_startup_ondir.py\",\\n'
        '        \"Tools/apply_v11761_remote_single_instance_definition.py\",\\n'
        '        \"Tools/apply_v11762_remote_recent_command_poll.py\",\\n'
        '        \"Tools/apply_v11767_persistent_remote_session.py\",\\n'
        '        \"Tools/apply_v11768_relay_http_poll.py\",\\n'
        '        \"Tools/apply_v11769_self_improvement_inspection.py\",\\n'
        '        \"Tools/apply_v11771_self_repair_natural_recall.py\",\\n'
"""
if patch_anchor not in source:
    raise SystemExit("v0.11.7.71 nested patch-list anchor missing")
source = source.replace(patch_anchor, patch_new, 1)

# .57 remains the project-learning engine identity; .71 changes the surrounding
# runtime repair/rendering behavior, not the evidence-loop protocol itself.
old_autolearn_version = 'autolearn.get("version") == "0.11.7.53"'
if old_autolearn_version not in source:
    raise SystemExit("v0.11.7.71 autolearn version smoke anchor missing")
source = source.replace(old_autolearn_version, 'autolearn.get("version") == "0.11.7.57"', 1)

old_mode = 'autolearn.get("mode") != "autonomous-source-grounded-project-learning"'
if old_mode not in source:
    raise SystemExit("v0.11.7.71 autolearn mode smoke anchor missing")
source = source.replace(
    old_mode,
    'autolearn.get("mode") != "autonomous-source-grounded-project-learning-evidence-loop"',
    1,
)

globals_dict = {
    "__name__": "__main__",
    "__file__": str(source_path),
    "__package__": None,
}
exec(compile(source, str(source_path) + "[v11771]", "exec"), globals_dict)
