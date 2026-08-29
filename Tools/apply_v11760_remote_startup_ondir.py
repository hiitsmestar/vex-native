#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

REMOTE = Path("Tools/VexRemoteSupport.py")
remote = REMOTE.read_text(encoding="utf-8")

if 'VERSION = "0.11.7.59"' not in remote:
    raise SystemExit("v0.11.7.60 expected v0.11.7.59 Remote Support identity")
remote = re.sub(r'^VERSION = "0\.11\.7\.59"', 'VERSION = "0.11.7.60"', remote, count=1, flags=re.M)

# Preserve the existing v0.11.7.23 startup wrapper, but make a frozen failure
# tell us the actual NameError symbol instead of only the exception class.
old_log = 'crash.write_text(f"{datetime.now(timezone.utc).isoformat()} {exc.__class__.__name__}: {str(exc)[:500]}\\n", "utf-8")'
new_log = 'crash.write_text(f"{datetime.now(timezone.utc).isoformat()} {exc.__class__.__name__}: {str(exc)[:1000]}\\n", "utf-8")'
if old_log not in remote:
    raise SystemExit("v0.11.7.60 startup crash-log anchor missing")
remote = remote.replace(old_log, new_log, 1)

old_dialog = '_mb.showerror("Vex Remote Support", f"Startup failed: {exc.__class__.__name__}")'
new_dialog = '_mb.showerror("Vex Remote Support", f"Startup failed: {exc.__class__.__name__}: {str(exc)[:240]}")'
if old_dialog not in remote:
    raise SystemExit("v0.11.7.60 startup dialog anchor missing")
remote = remote.replace(old_dialog, new_dialog, 1)

REMOTE.write_text(remote, encoding="utf-8")
compile(remote, str(REMOTE), "exec")
for marker in [
    'VERSION = "0.11.7.60"',
    'startup-crash.log',
    'Startup failed: {exc.__class__.__name__}: {str(exc)[:240]}',
]:
    if marker not in remote:
        raise SystemExit(f"v0.11.7.60 marker missing: {marker}")
print("Applied v0.11.7.60 frozen-startup diagnostics + onedir identity")
