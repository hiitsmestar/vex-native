#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
INSTALLER = Path("Tools/VexAgentRuntimeInstall.py")

bridge = BRIDGE.read_text(encoding="utf-8")
installer = INSTALLER.read_text(encoding="utf-8")

if '"version": "0.11.7.39"' not in bridge:
    raise SystemExit("v0.11.7.50 expected Bridge v0.11.7.39 generated source")
if 'BUNDLE_VERSION = "0.11.7.49"' not in installer:
    raise SystemExit("v0.11.7.50 expected Agent Runtime installer v0.11.7.49")

# Field failure on the real Windows 10 host: the frozen Bridge inherited a cp1252
# text stream and a startup message containing U+2192 crashed main() before the
# local-control socket could bind. Keep runtime output locale-independent.
# Replace the unsupported arrow in generated Bridge text and configure any live
# stdout/stderr wrappers for UTF-8 with replacement before the first startup print.
bridge = bridge.replace("→", "->")

helper_anchor = "\ndef main() -> None:\n"
helper = '''\ndef _vex_configure_text_io() -> None:\n    for stream_name in ("stdout", "stderr"):\n        try:\n            stream = getattr(sys, stream_name, None)\n            if stream is not None and hasattr(stream, "reconfigure"):\n                stream.reconfigure(encoding="utf-8", errors="replace")\n        except Exception:\n            pass\n\n\ndef main() -> None:\n    _vex_configure_text_io()\n'''
if "def _vex_configure_text_io() -> None:" not in bridge:
    if helper_anchor not in bridge:
        raise SystemExit("v0.11.7.50 Bridge main anchor missing")
    bridge = bridge.replace(helper_anchor, helper, 1)
elif "    _vex_configure_text_io()\n" not in bridge:
    raise SystemExit("v0.11.7.50 text-IO helper exists but main does not call it")

# Advertise the runtime bundle hotfix while deliberately preserving the proven
# Bridge protocol/version identity used by the iPhone pairing path.
bridge = bridge.replace('"agent_runtime_bundle": "0.11.7.49"', '"agent_runtime_bundle": "0.11.7.50"')
installer = installer.replace('BUNDLE_VERSION = "0.11.7.49"', 'BUNDLE_VERSION = "0.11.7.50"')
installer = installer.replace("Vex Agent Runtime v0.11.7.49 installed.", "Vex Agent Runtime v0.11.7.50 installed.")

BRIDGE.write_text(bridge, encoding="utf-8")
INSTALLER.write_text(installer, encoding="utf-8")
compile(bridge, str(BRIDGE), "exec")
compile(installer, str(INSTALLER), "exec")

# Regression guard for the exact field crash.
if "→" in bridge:
    raise SystemExit("v0.11.7.50 unsupported U+2192 remained in generated Bridge source")
for marker in [
    "def _vex_configure_text_io() -> None:",
    'stream.reconfigure(encoding="utf-8", errors="replace")',
    "    _vex_configure_text_io()",
    '"agent_runtime_bundle": "0.11.7.50"',
    '"version": "0.11.7.39"',
]:
    if marker not in bridge:
        raise SystemExit(f"v0.11.7.50 Bridge marker missing: {marker}")
if 'BUNDLE_VERSION = "0.11.7.50"' not in installer:
    raise SystemExit("v0.11.7.50 installer version marker missing")

print("Applied v0.11.7.50 Windows locale-safe Bridge field hotfix")
