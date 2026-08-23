#!/usr/bin/env python3
from pathlib import Path

path = Path("Tools/VexRemoteSupport.py")
text = path.read_text(encoding="utf-8")
bad = 'usage = shutil.disk_usage(Path.home().anchor or r"C:\\")'
good = 'usage = shutil.disk_usage(Path.home().anchor or "C:\\\\")'
if bad not in text:
    raise SystemExit("remote support Windows-root syntax marker missing")
path.write_text(text.replace(bad, good, 1), encoding="utf-8")
print("Fixed VexRemoteSupport Windows root literal")
