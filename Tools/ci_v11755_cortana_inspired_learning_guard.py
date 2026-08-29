#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

# Build .55 from the exact field-proven .54 assembler, adding only the learning
# state-machine guard and interactive Windows inventory recovery on top.
source_path = Path("Tools/ci_v11754_windows_native_autolearn_remote.py")
source = source_path.read_text(encoding="utf-8")

replacements = {
    'PKG_NAME = "Vex-Agent-Runtime-v0.11.7.54-WindowsNative-AutolearnRemote"':
        'PKG_NAME = "Vex-Agent-Runtime-v0.11.7.55-CortanaInspired-LearningGuard"',
    '        "Tools/apply_v11754_installer_self_home_hotfix.py",\\n': (
        '        "Tools/apply_v11754_installer_self_home_hotfix.py",\\n'
        '        "Tools/apply_v11755_cortana_inspired_learning_guard.py",\\n'
    ),
    '\\'"agent_runtime_bundle": "0.11.7.54"\\'': '\\'"agent_runtime_bundle": "0.11.7.55"\\'',
    'Install-Vex-Agent-Runtime-v0.11.7.54': 'Install-Vex-Agent-Runtime-v0.11.7.55',
    'Vex Agent Runtime v0.11.7.54 Windows Native + Autolearn Remote':
        'Vex Agent Runtime v0.11.7.55 Cortana-Inspired Windows + Learning Guard',
    'autolearn.get("version") == "0.11.7.53"': 'autolearn.get("version") == "0.11.7.55"',
    'autolearn.get("mode") != "autonomous-source-grounded-project-learning"':
        'autolearn.get("mode") != "autonomous-source-grounded-project-learning-guarded"',
    'native.get("version") == "0.11.7.54"': 'native.get("version") == "0.11.7.55"',
}
for old, new in replacements.items():
    if old not in source:
        raise SystemExit(f"v0.11.7.55 CI anchor missing: {old}")
    source = source.replace(old, new, 1)

# Strengthen production smoke: a build is not green unless the anti-spam guard
# and Windows interactive-session diagnostics are actually present at runtime.
autolearn_log = '                log(f"Autonomous learning status: {autolearn}")\\n'
autolearn_guard = (
    '                if autolearn.get("proposal_dedupe") is not True or autolearn.get("evidence_change_required") is not True:\\n'
    '                    raise RuntimeError(f"Autonomous proposal guard missing: {autolearn}")\\n'
    '                if int(autolearn.get("per_task_proposal_cap") or 0) != 6:\\n'
    '                    raise RuntimeError(f"Autonomous proposal cap mismatch: {autolearn}")\\n'
    '                log(f"Autonomous learning status: {autolearn}")\\n'
)
if autolearn_log not in source:
    raise SystemExit("v0.11.7.55 autolearn smoke log anchor missing")
source = source.replace(autolearn_log, autolearn_guard, 1)

native_log = '                log(f"Windows-native capabilities: {native}")\\n'
native_guard = (
    '                if native.get("supported_windows_primitives") is not True:\\n'
    '                    raise RuntimeError(f"Supported Windows primitive marker missing: {native}")\\n'
    '                if "interactive_session_match" not in native or "input_desktop_accessible" not in native or "window_inventory_method" not in native:\\n'
    '                    raise RuntimeError(f"Windows interactive-session diagnostics missing: {native}")\\n'
    '                if native.get("cortana_private_api_dependency") is not False:\\n'
    '                    raise RuntimeError(f"Retired/private Cortana dependency detected: {native}")\\n'
    '                log(f"Windows-native capabilities: {native}")\\n'
)
if native_log not in source:
    raise SystemExit("v0.11.7.55 Windows-native smoke log anchor missing")
source = source.replace(native_log, native_guard, 1)

# Extend package notes with the field fixes and the non-destructive compaction rule.
readme_anchor = '        "The Windows-native layer does not depend on the retired Cortana app or private Cortana interfaces.\\\\n"\\n'
readme_new = (
    '        "The Windows-native layer does not depend on the retired Cortana app or private Cortana interfaces.\\\\n"\\n'
    '        "v0.11.7.55 preserves terminal autonomous-task states so approval-required/staged work cannot be re-seeded into proposal loops.\\\\n"\\n'
    '        "Repeated project proposals require materially changed source evidence, use a six-hour cooldown and are capped at six per task.\\\\n"\\n'
    '        "Existing duplicate proposal rows are non-destructively marked superseded-duplicate; personal memory and source evidence are untouched.\\\\n"\\n'
    '        "Windows inventory falls back to supported PowerShell MainWindowHandle discovery and reports interactive-session/input-desktop health without publishing raw titles.\\\\n"\\n'
)
if readme_anchor not in source:
    raise SystemExit("v0.11.7.55 README anchor missing")
source = source.replace(readme_anchor, readme_new, 1)

globals_dict = {
    "__name__": "__main__",
    "__file__": str(source_path),
    "__package__": None,
}
exec(compile(source, str(source_path) + "[v11755]", "exec"), globals_dict)
