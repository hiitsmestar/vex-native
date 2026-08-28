#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

source_path = Path("Tools/ci_v11749_greenline.py")
source = source_path.read_text(encoding="utf-8")

# Start from the proven .49 Greenline driver, then apply the already-field-proven
# .50 locale layer followed by the narrow .51 memory-write layer.
replacements = {
    'PKG_NAME = "Vex-Agent-Runtime-v0.11.7.49-Greenline"': 'PKG_NAME = "Vex-Agent-Runtime-v0.11.7.51-MemoryWrite"',
    '        "Tools/apply_v11749_agent_runtime_foundation.py",\n': '        "Tools/apply_v11749_agent_runtime_foundation.py",\n        "Tools/apply_v11750_windows_locale_hotfix.py",\n        "Tools/apply_v11751_explicit_memory_write.py",\n',
    '\'"agent_runtime_bundle": "0.11.7.49"\'': '\'"agent_runtime_bundle": "0.11.7.51"\'',
    'Install-Vex-Agent-Runtime-v0.11.7.49': 'Install-Vex-Agent-Runtime-v0.11.7.51',
}
for old, new in replacements.items():
    if old not in source:
        raise SystemExit(f"v0.11.7.51 CI anchor missing: {old}")
    source = source.replace(old, new)

# Keep the exact legacy Windows text-codec regression that .50 fixed.  .51 is not
# allowed to regress the field-proven Bridge startup while changing memory routing.
locale_anchor = '    env = isolated_env("VexAgentBridgeSmoke")\n'
locale_replace = (
    '    env = isolated_env("VexAgentBridgeSmoke")\n'
    '    env["PYTHONUTF8"] = "0"\n'
    '    env["PYTHONIOENCODING"] = "cp1252"\n'
)
if locale_anchor not in source:
    raise SystemExit("v0.11.7.51 Bridge smoke locale anchor missing")
source = source.replace(locale_anchor, locale_replace, 1)

# Execute the full proven runtime proof.  A separate workflow step then performs
# an end-to-end explicit write/readback regression against the packaged worker.
globals_dict = {
    "__name__": "__main__",
    "__file__": str(source_path),
    "__package__": None,
}
exec(compile(source, str(source_path) + "[v11751]", "exec"), globals_dict)
