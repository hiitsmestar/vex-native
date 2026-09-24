#!/usr/bin/env python3
from __future__ import annotations
import subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def run(path: str) -> None:
    print(f"==> {path}", flush=True)
    result = subprocess.run([sys.executable, path], cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(result.returncode)

run("Tools/build_v147_autonomous_foreground_wake.py")
run("Tools/apply_v148_active_lifecycle_drain.py")

bg = (ROOT / "VexNative" / "VexBackgroundAgent.swift").read_text(encoding="utf-8")
for marker in [
    "V148_ACTIVE_FOREGROUND_COMMAND_GATE",
    "requiresForeground(remote.command)",
    "UIApplication.shared.applicationState == .active",
    "Foreground activation timed out.",
]:
    if marker not in bg:
        raise SystemExit(f"missing v0.14.8 marker: {marker}")
print("PASS v0.14.8 build chain")
