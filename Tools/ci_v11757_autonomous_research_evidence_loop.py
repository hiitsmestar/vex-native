#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

# Build .57 from the exact field-proven .54 production assembler. Preserve the
# complete .55 anti-spam guard and .56 Doctor/startup recovery, then add only the
# project-linked autonomous research/evidence receipt layer on top.
source_path = Path("Tools/ci_v11754_windows_native_autolearn_remote.py")
source = source_path.read_text(encoding="utf-8")

if "0.11.7.54" not in source:
    raise SystemExit("v0.11.7.57 expected .54 assembler identity missing")
source = source.replace("0.11.7.54", "0.11.7.57")

source = source.replace(
    'Vex-Agent-Runtime-v0.11.7.57-WindowsNative-AutolearnRemote',
    'Vex-Agent-Runtime-v0.11.7.57-AutonomousResearch-EvidenceLoop',
)
source = source.replace(
    'Vex Agent Runtime v0.11.7.57 Windows Native + Autolearn Remote',
    'Vex Agent Runtime v0.11.7.57 Autonomous Research + Evidence Loop',
)

# Insert .55, .56 and .57 after the inherited .54 installer self-home hotfix.
patch_anchor = """        '        \"Tools/apply_v11754_installer_self_home_hotfix.py\",\\n'
"""
patch_new = patch_anchor + """        '        \"Tools/apply_v11755_cortana_inspired_learning_guard.py\",\\n'
        '        \"Tools/apply_v11756_remote_doctor_startup_probe_hotfix.py\",\\n'
        '        \"Tools/apply_v11757_autonomous_research_evidence_loop.py\",\\n'
"""
if patch_anchor not in source:
    raise SystemExit("v0.11.7.57 nested .54 patch-list anchor missing")
source = source.replace(patch_anchor, patch_new, 1)

# Production smoke must see the new evidence-loop identity after all carried layers.
old_autolearn_version = 'autolearn.get("version") == "0.11.7.53"'
if old_autolearn_version not in source:
    raise SystemExit("v0.11.7.57 autolearn version smoke anchor missing")
source = source.replace(old_autolearn_version, 'autolearn.get("version") == "0.11.7.57"', 1)

old_mode = 'autolearn.get("mode") != "autonomous-source-grounded-project-learning"'
if old_mode not in source:
    raise SystemExit("v0.11.7.57 autolearn mode smoke anchor missing")
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
exec(compile(source, str(source_path) + "[v11757]", "exec"), globals_dict)
