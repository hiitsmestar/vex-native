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
# the guarded status identity. Production smoke must verify the wrapper, not .53.
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

# Strengthen production smoke: a build is not green unless the anti-spam guard
# and Windows interactive-session diagnostics are actually present at runtime.
autolearn_log = '                log(f"Autonomous learning status: {autolearn}")\n'
autolearn_guard = (
    '                if autolearn.get("proposal_dedupe") is not True or autolearn.get("evidence_change_required") is not True:\n'
    '                    raise RuntimeError(f"Autonomous proposal guard missing: {autolearn}")\n'
    '                if int(autolearn.get("per_task_proposal_cap") or 0) != 6:\n'
    '                    raise RuntimeError(f"Autonomous proposal cap mismatch: {autolearn}")\n'
    '                log(f"Autonomous learning status: {autolearn}")\n'
)
if autolearn_log not in source:
    raise SystemExit("v0.11.7.55 autolearn smoke log anchor missing")
source = source.replace(autolearn_log, autolearn_guard, 1)

native_log = '                log(f"Windows-native capabilities: {native}")\n'
native_guard = (
    '                if native.get("supported_windows_primitives") is not True:\n'
    '                    raise RuntimeError(f"Supported Windows primitive marker missing: {native}")\n'
    '                if "interactive_session_match" not in native or "input_desktop_accessible" not in native or "window_inventory_method" not in native:\n'
    '                    raise RuntimeError(f"Windows interactive-session diagnostics missing: {native}")\n'
    '                if native.get("cortana_private_api_dependency") is not False:\n'
    '                    raise RuntimeError(f"Retired/private Cortana dependency detected: {native}")\n'
    '                log(f"Windows-native capabilities: {native}")\n'
)
if native_log not in source:
    raise SystemExit("v0.11.7.55 Windows-native smoke log anchor missing")
source = source.replace(native_log, native_guard, 1)

# Keep an explicit build-time note in the assembler source. Runtime/tests enforce
# these rules; this comment prevents accidental loss during future chain edits.
notes_anchor = "globals_dict = {\n"
notes = '''# v0.11.7.55 field rules enforced by runtime/tests:\n# - terminal autonomous-task states cannot be re-seeded into proposal loops;\n# - repeated proposals require changed source evidence and are capped per task;\n# - duplicate rows are non-destructively superseded, never deleted;\n# - Windows window discovery uses supported APIs/fallbacks, never private Cortana.\n\n'''
if notes_anchor not in source:
    raise SystemExit("v0.11.7.55 assembler globals anchor missing")
source = source.replace(notes_anchor, notes + notes_anchor, 1)

globals_dict = {
    "__name__": "__main__",
    "__file__": str(source_path),
    "__package__": None,
}
exec(compile(source, str(source_path) + "[v11755]", "exec"), globals_dict)
