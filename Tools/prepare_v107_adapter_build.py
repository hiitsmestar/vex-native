#!/usr/bin/env python3
from pathlib import Path

path = Path("Bridge/vex_bridge_full.py")
text = path.read_text(encoding="utf-8")
# v0.10.2's modular Art Worker patch advances the launcher marker after v0.9.8.
# The v0.10.7 adapter patch was authored against the v0.9.8 modular boundary, so
# normalize only the build marker here; no runtime logic is reverted.
if 'VERSION = "0.10.2"' in text:
    text = text.replace('VERSION = "0.10.2"', 'VERSION = "0.9.8"', 1)
elif 'VERSION = "0.9.8"' not in text:
    raise SystemExit("expected v0.10.2/v0.9.8 Bridge launcher marker missing")
path.write_text(text, encoding="utf-8")
print("Prepared Bridge launcher marker for v0.10.7 adapter patch")
