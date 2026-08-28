#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

# Build .53 from the field-proven Greenline assembler. Keep every narrow field fix
# in order, then add only the autonomous project-learning supervisor.
source_path = Path("Tools/ci_v11749_greenline.py")
source = source_path.read_text(encoding="utf-8")

replacements = {
    'PKG_NAME = "Vex-Agent-Runtime-v0.11.7.49-Greenline"': 'PKG_NAME = "Vex-Agent-Runtime-v0.11.7.53-AutonomousLearning"',
    '        "Tools/apply_v11749_agent_runtime_foundation.py",\n': (
        '        "Tools/apply_v11749_agent_runtime_foundation.py",\n'
        '        "Tools/apply_v11750_windows_locale_hotfix.py",\n'
        '        "Tools/apply_v11751_explicit_memory_write.py",\n'
        '        "Tools/apply_v11752_memory_correction.py",\n'
        '        "Tools/apply_v11752_explicit_key_hotfix.py",\n'
        '        "Tools/apply_v11752_recall_hotfix.py",\n'
        '        "Tools/apply_v11752_variant_state_hotfix.py",\n'
        '        "Tools/apply_v11753_autonomous_learning_supervisor.py",\n'
    ),
    '\'"agent_runtime_bundle": "0.11.7.49"\'': '\'"agent_runtime_bundle": "0.11.7.53"\'',
    'Install-Vex-Agent-Runtime-v0.11.7.49': 'Install-Vex-Agent-Runtime-v0.11.7.53',
    'Vex Agent Runtime v0.11.7.49 Greenline': 'Vex Agent Runtime v0.11.7.53 Autonomous Learning',
    'Production-shaped Agent Runtime around the proven v0.11.7.39 PC cognition Bridge and working v0.11.7.48 iPhone pairing.': 'Production-shaped Agent Runtime around the proven v0.11.7.39 PC cognition Bridge and working v0.11.7.49 iPhone PC-routing hotfix.',
    'Includes persistent memory, adaptive learning, autonomous improvement, initiative scheduling, Remote Support, Windows Host, Node Agent and diagnostics.': 'Includes persistent memory/correction, source-aware research, adaptive learning, autonomous project-learning proposals, initiative scheduling, Remote Support, Windows Host, Node Agent and diagnostics.',
}
for old, new in replacements.items():
    if old not in source:
        raise SystemExit(f"v0.11.7.53 CI anchor missing: {old}")
    source = source.replace(old, new)

# Preserve the exact old-Windows locale regression that .50 fixed.
locale_anchor = '    env = isolated_env("VexAgentBridgeSmoke")\n'
locale_replace = (
    '    env = isolated_env("VexAgentBridgeSmoke")\n'
    '    env["PYTHONUTF8"] = "0"\n'
    '    env["PYTHONIOENCODING"] = "cp1252"\n'
)
if locale_anchor not in source:
    raise SystemExit("v0.11.7.53 Bridge smoke locale anchor missing")
source = source.replace(locale_anchor, locale_replace, 1)

# Strengthen the production Bridge smoke: .53 is not green merely because the
# process starts. The autonomous learner must answer its authenticated status route.
adaptive_return = '''            if adaptive.get("ok") and adaptive.get("worker_started") and adaptive.get("worker_alive"):\n                log(f"Adaptive status: {adaptive}")\n                return\n'''
autolearn_return = '''            if adaptive.get("ok") and adaptive.get("worker_started") and adaptive.get("worker_alive"):\n                log(f"Adaptive status: {adaptive}")\n                autolearn = local_control_request(config_path, "/autolearn/status")\n                if not (autolearn.get("ok") and autolearn.get("version") == "0.11.7.53"):\n                    raise RuntimeError(f"Autonomous learning supervisor status failed: {autolearn}")\n                if autolearn.get("mode") != "autonomous-source-grounded-project-learning":\n                    raise RuntimeError(f"Autonomous learning mode mismatch: {autolearn}")\n                log(f"Autonomous learning status: {autolearn}")\n                return\n'''
if adaptive_return not in source:
    raise SystemExit("v0.11.7.53 adaptive smoke anchor missing")
source = source.replace(adaptive_return, autolearn_return, 1)

# Package README must spell out the trust boundary so a field artifact cannot be
# mistaken for unrestricted binary self-rewriting.
readme_anchor = '        "No paid API or cloud inference is introduced. Private pairing, profile and memory data remain local.\\n"\n'
readme_new = (
    '        "No paid API or cloud inference is introduced. Private pairing, profile and memory data remain local.\\n"\n'
    '        "Autonomous internet learning stores public-source evidence separately from personal memory and produces privacy-scrubbed local improvement proposals.\\n"\n'
    '        "Install/delete/security/deploy/protected-runtime changes remain approval-gated; the learner does not blindly rewrite or deploy the running runtime.\\n"\n'
)
if readme_anchor not in source:
    raise SystemExit("v0.11.7.53 README boundary anchor missing")
source = source.replace(readme_anchor, readme_new, 1)

globals_dict = {
    "__name__": "__main__",
    "__file__": str(source_path),
    "__package__": None,
}
exec(compile(source, str(source_path) + "[v11753]", "exec"), globals_dict)
