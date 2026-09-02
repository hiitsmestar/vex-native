#!/usr/bin/env python3
from pathlib import Path

HOST = Path("Tools/VexWindowsHost-v11740.py")
BRIDGE = Path("Bridge/vex_bridge.py")

if not HOST.exists() or not BRIDGE.exists():
    raise SystemExit("v0.12 wants field fingerprint requires generated Host + Bridge")

host = HOST.read_text(encoding="utf-8")
bridge = BRIDGE.read_text(encoding="utf-8")

# Make the field artifact unmistakable. The title is inspected from the actual
# frozen EXE in CI and is also visible to Star after installation.
title_old = '        self.title(f"Vex Windows {VERSION}")\n'
title_new = '        self.title(f"Vex Windows {VERSION} | wants71")\n'
if "wants71" not in host:
    if title_old not in host:
        raise SystemExit("v0.12 wants fingerprint missing Host title anchor")
    host = host.replace(title_old, title_new, 1)

# Give the request viewer its own full-width bar so it cannot be squeezed out
# of the existing chat-control button row on older/smaller displays.
bar_anchor = '        row = ttk.Frame(self)\n'
bar_code = '''        wantsbar = ttk.Frame(self)\n        wantsbar.pack(fill="x", padx=18, pady=(0, 8))\n        ttk.Button(wantsbar, text="Vex wants / upgrade requests", command=self.show_vex_wants).pack(fill="x")\n\n'''
if 'text="Vex wants / upgrade requests"' not in host:
    if bar_anchor not in host:
        raise SystemExit("v0.12 wants fingerprint missing Host control-row anchor")
    host = host.replace(bar_anchor, bar_code + bar_anchor, 1)

# Expose a harmless build fingerprint through local Bridge status so Remote
# Support can prove which field artifact is actually running without exposing
# private request contents.
status_anchor = '"agent_runtime_bundle": "0.12.0",'
status_new = status_anchor + '\n        "vex_wants_field_build": "71",'
if '"vex_wants_field_build": "71"' not in bridge:
    if status_anchor not in bridge:
        raise SystemExit("v0.12 wants fingerprint missing Bridge bundle-status anchor")
    bridge = bridge.replace(status_anchor, status_new, 1)

HOST.write_text(host, encoding="utf-8")
BRIDGE.write_text(bridge, encoding="utf-8")
compile(host, str(HOST), "exec")
compile(bridge, str(BRIDGE), "exec")

for marker in [
    'wants71',
    'text="Vex wants / upgrade requests"',
    'command=self.show_vex_wants',
]:
    if marker not in host:
        raise SystemExit(f"v0.12 wants field Host marker missing: {marker}")
if '"vex_wants_field_build": "71"' not in bridge:
    raise SystemExit("v0.12 wants field Bridge fingerprint missing")

print("Applied field-visible Vex wants bar + wants71 frozen-build fingerprint")
