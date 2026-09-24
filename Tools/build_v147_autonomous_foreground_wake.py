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

run("Tools/build_v145_roaming_persistence.py")
run("Tools/apply_v147_autonomous_foreground_wake.py")

voice = (ROOT / "VexNative" / "VexVoiceIntents.swift").read_text(encoding="utf-8")
for marker in [
    "V147_AUTONOMOUS_FOREGROUND_WAKE",
    "static var openAppWhenRun = true",
    'wake == "wake and check remote relay"',
    "await VexPhoneBackgroundWorker.runOnce()",
]:
    if marker not in voice:
        raise SystemExit(f"missing v0.14.7 marker: {marker}")
print("PASS v0.14.7 build chain")
