#!/usr/bin/env python3
from pathlib import Path

path = Path("Tools/apply_v120_pc_health_autonomy.py")
text = path.read_text(encoding="utf-8")

# The health patch embeds generated Bridge source in one raw triple-quoted block.
# Its PowerShell probe needs the opposite quote delimiter so the patch script
# itself remains valid Python on a fresh checkout.
old_open = "    script = r'''$ErrorActionPreference='Stop'\n"
new_open = '    script = r"""$ErrorActionPreference=\'Stop\'\n'
old_close = "} | ConvertTo-Json -Depth 6 -Compress'''\n"
new_close = '} | ConvertTo-Json -Depth 6 -Compress"""\n'

if old_open in text:
    text = text.replace(old_open, new_open, 1)
if old_close in text:
    text = text.replace(old_close, new_close, 1)

# A raw generated Windows root written as r"C:\\" becomes the invalid r"C:\"
# once the outer raw layer is emitted. A forward-slash Windows root is accepted
# by pathlib/shutil and avoids that trailing-backslash syntax trap entirely.
bad_root = 'Path.home().anchor or r"C:\\"'
if bad_root in text:
    text = text.replace(bad_root, 'Path.home().anchor or "C:/"')

compile(text, str(path), "exec")
path.write_text(text, encoding="utf-8")
print("Prepared v0.12 PC health autonomy patch source")
