#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

# Build .56 from the exact field-proven .54 production assembler, preserving the
# complete .55 guard layer and adding only the Doctor/startup-probe hotfix on top.
source_path = Path("Tools/ci_v11754_windows_native_autolearn_remote.py")
source = source_path.read_text(encoding="utf-8")

if "0.11.7.54" not in source:
    raise SystemExit("v0.11.7.56 expected .54 assembler identity missing")
source = source.replace("0.11.7.54", "0.11.7.56")

source = source.replace(
    'Vex-Agent-Runtime-v0.11.7.56-WindowsNative-AutolearnRemote',
    'Vex-Agent-Runtime-v0.11.7.56-RemoteDoctor-StartupProbe-Hotfix',
)
source = source.replace(
    'Vex Agent Runtime v0.11.7.56 Windows Native + Autolearn Remote',
    'Vex Agent Runtime v0.11.7.56 Remote Doctor + Startup Probe Hotfix',
)

# Insert .55 and .56 after the inherited .54 installer self-home hotfix.
patch_anchor = """        '        \"Tools/apply_v11754_installer_self_home_hotfix.py\",\\n'
"""
patch_new = patch_anchor + """        '        \"Tools/apply_v11755_cortana_inspired_learning_guard.py\",\\n'
        '        \"Tools/apply_v11756_remote_doctor_startup_probe_hotfix.py\",\\n'
"""
if patch_anchor not in source:
    raise SystemExit("v0.11.7.56 nested .54 patch-list anchor missing")
source = source.replace(patch_anchor, patch_new, 1)

# .56 keeps the guarded .55 behavior and only advances its exposed status identity.
old_autolearn_version = 'autolearn.get("version") == "0.11.7.53"'
if old_autolearn_version not in source:
    raise SystemExit("v0.11.7.56 autolearn version smoke anchor missing")
source = source.replace(old_autolearn_version, 'autolearn.get("version") == "0.11.7.56"', 1)

old_mode = 'autolearn.get("mode") != "autonomous-source-grounded-project-learning"'
if old_mode not in source:
    raise SystemExit("v0.11.7.56 autolearn mode smoke anchor missing")
source = source.replace(
    old_mode,
    'autolearn.get("mode") != "autonomous-source-grounded-project-learning-guarded"',
    1,
)

globals_dict = {
    "__name__": "__main__",
    "__file__": str(source_path),
    "__package__": None,
}
exec(compile(source, str(source_path) + "[v11756]", "exec"), globals_dict)
