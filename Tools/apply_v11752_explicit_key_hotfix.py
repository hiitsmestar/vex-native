#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
bridge = BRIDGE.read_text(encoding="utf-8")

old = 'canonical_key = "iphone-memory:" + hashlib.sha256(old_text.encode("utf-8", "ignore")).hexdigest()'
new = 'canonical_key = "explicit:star:" + hashlib.sha256(old_text.encode("utf-8", "ignore")).hexdigest()[:20]'

if old not in bridge:
    if new in bridge:
        print("v0.11.7.52 explicit-key hotfix already applied")
        raise SystemExit(0)
    raise SystemExit("v0.11.7.52 explicit-key hotfix anchor missing")

bridge = bridge.replace(old, new, 1)

if new not in bridge:
    raise SystemExit("v0.11.7.52 explicit-key hotfix verification failed")
if '"agent_runtime_bundle": "0.11.7.52"' not in bridge:
    raise SystemExit("v0.11.7.52 bundle marker missing after explicit-key hotfix")

BRIDGE.write_text(bridge, encoding="utf-8")
compile(bridge, str(BRIDGE), "exec")
print("Applied v0.11.7.52 explicit-memory canonical-key hotfix")
