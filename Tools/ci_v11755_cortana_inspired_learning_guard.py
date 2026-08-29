#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

# Build .55 from the exact field-proven .54 assembler, adding only the learning
# state-machine guard and interactive Windows inventory recovery on top.
source_path = Path("Tools/ci_v11754_windows_native_autolearn_remote.py")
source = source_path.read_text(encoding="utf-8")

# The .54 assembler is itself a source-transformer. Advancing its dotted bundle
# identity is safe here because the actual .54 patch files still run unchanged
# before the .55 patch is applied.
if "0.11.7.54" not in source:
    raise SystemExit("v0.11.7.55 expected .54 assembler identity missing")
source = source.replace("0.11.7.54", "0.11.7.55")

# Give the deliverable its own clear name rather than inheriting .54's suffix.
source = source.replace(
    'Vex-Agent-Runtime-v0.11.7.55-WindowsNative-AutolearnRemote',
    'Vex-Agent-Runtime-v0.11.7.55-CortanaInspired-LearningGuard',
)
source = source.replace(
    'Vex Agent Runtime v0.11.7.55 Windows Native + Autolearn Remote',
    'Vex Agent Runtime v0.11.7.55 Cortana-Inspired Windows + Learning Guard',
)

# Insert the .55 patch into the nested Greenline patch-list string used by the
# .54 assembler. This anchor includes the outer Python string literal itself.
patch_anchor = """        '        \"Tools/apply_v11754_installer_self_home_hotfix.py\",\\n'
"""
patch_new = patch_anchor + """        '        \"Tools/apply_v11755_cortana_inspired_learning_guard.py\",\\n'
"""
if patch_anchor not in source:
    raise SystemExit("v0.11.7.55 nested .54 hotfix patch-list anchor missing")
source = source.replace(patch_anchor, patch_new, 1)

# The underlying supervisor component began life as .53; .55 wraps it and exposes
# the guarded status identity. The inherited production smoke must expect .55.
old_autolearn_version = 'autolearn.get("version") == "0.11.7.53"'
if old_autolearn_version not in source:
    raise SystemExit("v0.11.7.55 autolearn version smoke anchor missing")
source = source.replace(old_autolearn_version, 'autolearn.get("version") == "0.11.7.55"', 1)

old_mode = 'autolearn.get("mode") != "autonomous-source-grounded-project-learning"'
if old_mode not in source:
    raise SystemExit("v0.11.7.55 autolearn mode smoke anchor missing")
source = source.replace(
    old_mode,
    'autolearn.get("mode") != "autonomous-source-grounded-project-learning-guarded"',
    1,
)

# Dedicated .55 regression tests immediately follow the production assembler in
# CI and prove proposal dedupe/caps, evidence fingerprints, Windows fallback,
# session diagnostics, privacy boundaries, installer self-home safety and memory.

globals_dict = {
    "__name__": "__main__",
    "__file__": str(source_path),
    "__package__": None,
}
exec(compile(source, str(source_path) + "[v11755]", "exec"), globals_dict)
