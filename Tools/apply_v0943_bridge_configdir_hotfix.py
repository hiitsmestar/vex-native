#!/usr/bin/env python3
from pathlib import Path

path = Path("Bridge/vex_bridge.py")
text = path.read_text(encoding="utf-8")

old = '    return CONFIG_DIR / "learned_skills.json"\n'
new = '    return CONFIG_PATH.parent / "learned_skills.json"\n'

if old in text:
    text = text.replace(old, new, 1)
elif new not in text:
    raise SystemExit("Bridge skill-path block not found; refusing to build an unverified hotfix")

path.write_text(text, encoding="utf-8")

patched = path.read_text(encoding="utf-8")
if 'return CONFIG_PATH.parent / "learned_skills.json"' not in patched:
    raise SystemExit("CONFIG_DIR hotfix did not apply")
if "CONFIG_DIR" in patched:
    raise SystemExit("Unexpected CONFIG_DIR reference remains in patched Bridge")

print("Applied v0.9.4.3 Bridge learned-skills CONFIG_DIR crash hotfix")
