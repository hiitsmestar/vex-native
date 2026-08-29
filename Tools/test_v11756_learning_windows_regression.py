#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

# Re-run the complete .55 anti-spam/evidence fingerprint/PowerShell fallback/
# privacy regression suite against the .56 exposed bundle identity. .56 changes
# only field packaging/telemetry lookup behavior; the underlying guards must stay.
path = Path("Tools/test_v11755_cortana_inspired_learning_guard.py")
source = path.read_text(encoding="utf-8")
if "0.11.7.55" not in source:
    raise SystemExit("v0.11.7.56 expected .55 regression identity missing")
source = source.replace("0.11.7.55", "0.11.7.56")
exec(compile(source, str(path) + "[v11756]", "exec"), {"__name__": "__main__", "__file__": str(path)})
