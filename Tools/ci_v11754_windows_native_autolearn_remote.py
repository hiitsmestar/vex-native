#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

# Build .54 from the same field-proven Greenline assembler used by .53. Preserve
# every narrow field fix in order, then add only the Windows-native / Remote
# Support visibility layer on top of the proven .53 supervisor.
source_path = Path("Tools/ci_v11749_greenline.py")
source = source_path.read_text(encoding="utf-8")

replacements = {
    'PKG_NAME = "Vex-Agent-Runtime-v0.11.7.49-Greenline"': 'PKG_NAME = "Vex-Agent-Runtime-v0.11.7.54-WindowsNative-AutolearnRemote"',
    '        "Tools/apply_v11749_agent_runtime_foundation.py",\n': (
        '        "Tools/apply_v11749_agent_runtime_foundation.py",\n'
        '        "Tools/apply_v11750_windows_locale_hotfix.py",\n'
        '        "Tools/apply_v11751_explicit_memory_write.py",\n'
        '        "Tools/apply_v11752_memory_correction.py",\n'
        '        "Tools/apply_v11752_explicit_key_hotfix.py",\n'
        '        "Tools/apply_v11752_recall_hotfix.py",\n'
        '        "Tools/apply_v11752_variant_state_hotfix.py",\n'
        '        "Tools/apply_v11753_autonomous_learning_supervisor.py",\n'
        '        "Tools/apply_v11754_windows_native_autolearn_remote_v2.py",\n'
    ),
    '\'"agent_runtime_bundle": "0.11.7.49"\'': '\'"agent_runtime_bundle": "0.11.7.54"\'',
    'Install-Vex-Agent-Runtime-v0.11.7.49': 'Install-Vex-Agent-Runtime-v0.11.7.54',
    'Vex Agent Runtime v0.11.7.49 Greenline': 'Vex Agent Runtime v0.11.7.54 Windows Native + Autolearn Remote',
    'Production-shaped Agent Runtime around the proven v0.11.7.39 PC cognition Bridge and working v0.11.7.48 iPhone pairing.': 'Production-shaped Agent Runtime around the proven v0.11.7.39 PC cognition Bridge and working v0.11.7.49 iPhone PC-routing hotfix.',
    'Includes persistent memory, adaptive learning, autonomous improvement, initiative scheduling, Remote Support, Windows Host, Node Agent and diagnostics.': 'Includes persistent memory/correction, source-aware research, autonomous project-learning proposals, sanitized Remote Support controls, Windows-native capability discovery, initiative scheduling, Windows Host, Node Agent and diagnostics.',
}
for old, new in replacements.items():
    if old not in source:
        raise SystemExit(f"v0.11.7.54 CI anchor missing: {old}")
    source = source.replace(old, new)

# Preserve the exact old-Windows locale regression that .50 fixed.
locale_anchor = '    env = isolated_env("VexAgentBridgeSmoke")\n'
locale_replace = (
    '    env = isolated_env("VexAgentBridgeSmoke")\n'
    '    env["PYTHONUTF8"] = "0"\n'
    '    env["PYTHONIOENCODING"] = "cp1252"\n'
)
if locale_anchor not in source:
    raise SystemExit("v0.11.7.54 Bridge smoke locale anchor missing")
source = source.replace(locale_anchor, locale_replace, 1)

# Production smoke must prove the .53 supervisor is still alive and the new .54
# Windows-native authenticated capability route works on a real Windows runner.
adaptive_return = '''            if adaptive.get("ok") and adaptive.get("worker_started") and adaptive.get("worker_alive"):\n                log(f"Adaptive status: {adaptive}")\n                return\n'''
autolearn_native_return = '''            if adaptive.get("ok") and adaptive.get("worker_started") and adaptive.get("worker_alive"):\n                log(f"Adaptive status: {adaptive}")\n                autolearn = local_control_request(config_path, "/autolearn/status")\n                if not (autolearn.get("ok") and autolearn.get("version") == "0.11.7.53"):\n                    raise RuntimeError(f"Autonomous learning supervisor status failed: {autolearn}")\n                if autolearn.get("mode") != "autonomous-source-grounded-project-learning":\n                    raise RuntimeError(f"Autonomous learning mode mismatch: {autolearn}")\n                log(f"Autonomous learning status: {autolearn}")\n                native = local_control_request(config_path, "/windows/capabilities")\n                if not (native.get("ok") and native.get("version") == "0.11.7.54" and native.get("windows") is True):\n                    raise RuntimeError(f"Windows-native capability route failed: {native}")\n                for required in ["ui_automation_api", "msaa_accessibility_api", "shell_com_api", "windows_search_service", "windows_search_running", "sapi_speech", "powershell", "native_window_inventory", "visible_window_count"]:\n                    if required not in native:\n                        raise RuntimeError(f"Windows-native capability marker missing {required}: {native}")\n                if native.get("native_window_inventory") is not True:\n                    raise RuntimeError(f"Native window inventory is unavailable: {native}")\n                log(f"Windows-native capabilities: {native}")\n                return\n'''
if adaptive_return not in source:
    raise SystemExit("v0.11.7.54 adaptive smoke anchor missing")
source = source.replace(adaptive_return, autolearn_native_return, 1)

# Package README spells out both the privacy boundary and the supported Windows
# direction. No Cortana package/private API dependency is introduced.
readme_anchor = '        "No paid API or cloud inference is introduced. Private pairing, profile and memory data remain local.\\n"\n'
readme_new = (
    '        "No paid API or cloud inference is introduced. Private pairing, profile and memory data remain local.\\n"\n'
    '        "Autonomous internet learning stores public-source evidence separately from personal memory and produces privacy-scrubbed local improvement proposals.\\n"\n'
    '        "Install/delete/security/deploy/protected-runtime changes remain approval-gated; the learner does not blindly rewrite or deploy the running runtime.\\n"\n'
    '        "Windows-native discovery uses supported local Windows primitives; raw window titles stay behind the authenticated local Bridge and are never published by Remote Support.\\n"\n'
    '        "The Windows-native layer does not depend on the retired Cortana app or private Cortana interfaces.\\n"\n'
)
if readme_anchor not in source:
    raise SystemExit("v0.11.7.54 README boundary anchor missing")
source = source.replace(readme_anchor, readme_new, 1)

globals_dict = {
    "__name__": "__main__",
    "__file__": str(source_path),
    "__package__": None,
}
exec(compile(source, str(source_path) + "[v11754]", "exec"), globals_dict)
