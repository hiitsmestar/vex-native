#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

source_path = Path("Tools/ci_v11749_greenline.py")
source = source_path.read_text(encoding="utf-8")

replacements = {
    'PKG_NAME = "Vex-Agent-Runtime-v0.11.7.49-Greenline"': 'PKG_NAME = "Vex-Agent-Runtime-v0.11.7.50-FieldHotfix"',
    '        "Tools/apply_v11749_agent_runtime_foundation.py",\n': '        "Tools/apply_v11749_agent_runtime_foundation.py",\n        "Tools/apply_v11750_windows_locale_hotfix.py",\n',
    '\'"agent_runtime_bundle": "0.11.7.49"\'': '\'"agent_runtime_bundle": "0.11.7.50"\'',
    'Install-Vex-Agent-Runtime-v0.11.7.49': 'Install-Vex-Agent-Runtime-v0.11.7.50',
}
for old, new in replacements.items():
    if old not in source:
        raise SystemExit(f"v0.11.7.50 CI anchor missing: {old}")
    source = source.replace(old, new)

# Force the Bridge integration smoke into the same legacy Windows text-codec
# conditions observed on the real field host. The hotfix must stay alive here.
locale_anchor = '    env = isolated_env("VexAgentBridgeSmoke")\n'
locale_replace = (
    '    env = isolated_env("VexAgentBridgeSmoke")\n'
    '    env["PYTHONUTF8"] = "0"\n'
    '    env["PYTHONIOENCODING"] = "cp1252"\n'
)
if locale_anchor not in source:
    raise SystemExit("v0.11.7.50 Bridge smoke locale anchor missing")
source = source.replace(locale_anchor, locale_replace, 1)

# Execute the proven .49 driver with only the deliberate .50 deltas above.
globals_dict = {
    "__name__": "__main__",
    "__file__": str(source_path),
    "__package__": None,
}
exec(compile(source, str(source_path) + "[v11750]", "exec"), globals_dict)
