#!/usr/bin/env python3
from pathlib import Path

path = Path("Tools/VexRemoteSupport.py")
text = path.read_text(encoding="utf-8")

bad = 'usage = shutil.disk_usage(Path.home().anchor or r"C:\\")'
good = 'usage = shutil.disk_usage(Path.home().anchor or "C:\\\\")'

if bad in text:
    text = text.replace(bad, good, 1)
elif good not in text:
    raise SystemExit("Remote Support disk fallback marker missing")

path.write_text(text, encoding="utf-8")
compile(path.read_text(encoding="utf-8"), str(path), "exec")
print("Applied v0.10.9.1 Remote Support Windows path compile fix")
