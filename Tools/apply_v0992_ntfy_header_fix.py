#!/usr/bin/env python3
from pathlib import Path

path = Path("Tools/VexRemoteSupport.py")
text = path.read_text(encoding="utf-8")

if 'VERSION = "0.9.9.2"' in text:
    print("v0.9.9.2 ntfy fix already applied")
    raise SystemExit(0)

if 'VERSION = "0.9.9.1"' not in text:
    raise SystemExit("v0.9.9.1 marker missing")

text = text.replace('VERSION = "0.9.9.1"', 'VERSION = "0.9.9.2"', 1)

old = '"Title": f"Vex • {label}",'
if old not in text:
    raise SystemExit("ntfy title header marker missing")
# HTTP header values are encoded as latin-1 by requests/urllib3 on Windows.
# U+2022 BULLET cannot be encoded there, so the request failed before it left the PC.
text = text.replace(old, '"Title": f"Vex - {label}",', 1)

old_test = '''        if send_ntfy("Test notification — Vex can ping this phone when a job finishes."):\n            messagebox.showinfo("Vex Remote Support", "Test ping sent. Check the ntfy app on your iPhone.")\n        else:\n            messagebox.showwarning("Vex Remote Support", "The test ping did not send. Check internet access and the topic.")\n'''
new_test = '''        if send_ntfy("Test notification - Vex can ping this phone when a job finishes."):\n            messagebox.showinfo("Vex Remote Support", "Test ping sent. Check the ntfy app on your iPhone.")\n        else:\n            messagebox.showwarning("Vex Remote Support", "The test ping did not send. The topic is saved; if this persists, Remote Support will still work through GitHub while ntfy is repaired.")\n'''
if old_test not in text:
    raise SystemExit("ntfy test marker missing")
text = text.replace(old_test, new_test, 1)

for marker in ['VERSION = "0.9.9.2"', '"Title": f"Vex - {label}"', 'Test notification - Vex can ping']:
    if marker not in text:
        raise SystemExit(f"missing v0.9.9.2 marker: {marker}")

path.write_text(text, encoding="utf-8")
print("Applied Vex Remote Support v0.9.9.2 ntfy header fix")
