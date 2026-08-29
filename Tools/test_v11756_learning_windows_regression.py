#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

# Re-run the complete .55 anti-spam/evidence fingerprint/PowerShell fallback/
# privacy regression suite against the .56 exposed bundle identity. .56 changes
# field packaging/status identities only; the proven .55 raw local window-list
# helper is intentionally left untouched and is never exposed by Remote Support.
path = Path("Tools/test_v11755_cortana_inspired_learning_guard.py")
source = path.read_text(encoding="utf-8")

replacements = [
    ('\"agent_runtime_bundle\": \"0.11.7.55\"', '\"agent_runtime_bundle\": \"0.11.7.56\"'),
    ('VERSION = \"0.11.7.55\"', 'VERSION = \"0.11.7.56\"'),
    ('BUNDLE_VERSION = \"0.11.7.55\"', 'BUNDLE_VERSION = \"0.11.7.56\"'),
    ('REMOTE_VERSION = \"0.11.7.55\"', 'REMOTE_VERSION = \"0.11.7.56\"'),
    ('Vex Agent Runtime v0.11.7.55 installed.', 'Vex Agent Runtime v0.11.7.56 installed.'),
]
for old, new in replacements:
    if old not in source:
        raise SystemExit(f"v0.11.7.56 expected carried marker missing: {old}")
    source = source.replace(old, new)

exec(compile(source, str(path) + "[v11756]", "exec"), {"__name__": "__main__", "__file__": str(path)})
