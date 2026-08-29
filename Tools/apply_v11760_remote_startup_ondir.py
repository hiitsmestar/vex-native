#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

REMOTE = Path("Tools/VexRemoteSupport.py")
remote = REMOTE.read_text(encoding="utf-8")

if 'VERSION = "0.11.7.59"' not in remote:
    raise SystemExit("v0.11.7.60 expected v0.11.7.59 Remote Support identity")
remote = re.sub(r'^VERSION = "0\.11\.7\.59"', 'VERSION = "0.11.7.60"', remote, count=1, flags=re.M)

# Harden startup diagnostics without changing relay semantics. The field failure
# was a frozen startup NameError; write the exact exception class/name locally
# and keep the normal UI path unchanged when startup succeeds.
main_tail = '''if __name__ == "__main__":\n    raise SystemExit(main())\n'''
if main_tail not in remote:
    raise SystemExit("v0.11.7.60 main tail anchor missing")
replacement = '''def _write_startup_failure(exc: BaseException) -> None:\n    try:\n        path = app_root() / "startup-error-v11760.txt"\n        detail = f"{exc.__class__.__name__}: {exc}"\n        path.write_text(detail[:1200], encoding="utf-8")\n    except Exception:\n        pass\n\n\nif __name__ == "__main__":\n    try:\n        raise SystemExit(main())\n    except SystemExit:\n        raise\n    except Exception as exc:\n        _write_startup_failure(exc)\n        try:\n            import tkinter as _tk\n            from tkinter import messagebox as _messagebox\n            _root = _tk.Tk()\n            _root.withdraw()\n            _messagebox.showerror("Vex Remote Support", f"Startup failed: {exc.__class__.__name__}: {str(exc)[:240]}")\n            _root.destroy()\n        except Exception:\n            pass\n        raise SystemExit(1)\n'''
remote = remote.replace(main_tail, replacement, 1)

REMOTE.write_text(remote, encoding="utf-8")
compile(remote, str(REMOTE), "exec")
for marker in [
    'VERSION = "0.11.7.60"',
    'startup-error-v11760.txt',
    'Startup failed: {exc.__class__.__name__}:',
]:
    if marker not in remote:
        raise SystemExit(f"v0.11.7.60 marker missing: {marker}")
print("Applied v0.11.7.60 frozen-startup diagnostics + onedir identity")
