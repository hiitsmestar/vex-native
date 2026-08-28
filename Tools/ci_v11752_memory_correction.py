#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

# v0.11.7.52 CI rerun: includes verified-memory reply-variant state recovery.
source_path = Path("Tools/ci_v11749_greenline.py")
source = source_path.read_text(encoding="utf-8")

# Preserve the field-proven .50 locale fix, .51 explicit write path, then add
# only the narrow newest-correction-wins + authoritative recall layers.
replacements = {
    'PKG_NAME = "Vex-Agent-Runtime-v0.11.7.49-Greenline"': 'PKG_NAME = "Vex-Agent-Runtime-v0.11.7.52-MemoryCorrection"',
    '        "Tools/apply_v11749_agent_runtime_foundation.py",\n': '        "Tools/apply_v11749_agent_runtime_foundation.py",\n        "Tools/apply_v11750_windows_locale_hotfix.py",\n        "Tools/apply_v11751_explicit_memory_write.py",\n        "Tools/apply_v11752_memory_correction.py",\n        "Tools/apply_v11752_explicit_key_hotfix.py",\n        "Tools/apply_v11752_recall_hotfix.py",\n',
    '\'"agent_runtime_bundle": "0.11.7.49"\'': '\'"agent_runtime_bundle": "0.11.7.52"\'',
    'Install-Vex-Agent-Runtime-v0.11.7.49': 'Install-Vex-Agent-Runtime-v0.11.7.52',
}
for old, new in replacements.items():
    if old not in source:
        raise SystemExit(f"v0.11.7.52 CI anchor missing: {old}")
    source = source.replace(old, new)

# Keep the exact old-Windows locale regression that .50 fixed.
locale_anchor = '    env = isolated_env("VexAgentBridgeSmoke")\n'
locale_replace = (
    '    env = isolated_env("VexAgentBridgeSmoke")\n'
    '    env["PYTHONUTF8"] = "0"\n'
    '    env["PYTHONIOENCODING"] = "cp1252"\n'
)
if locale_anchor not in source:
    raise SystemExit("v0.11.7.52 Bridge smoke locale anchor missing")
source = source.replace(locale_anchor, locale_replace, 1)

globals_dict = {
    "__name__": "__main__",
    "__file__": str(source_path),
    "__package__": None,
}
exec(compile(source, str(source_path) + "[v11752]", "exec"), globals_dict)
