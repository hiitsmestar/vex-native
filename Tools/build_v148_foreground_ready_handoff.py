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
run("Tools/apply_v148_foreground_ready_handoff.py")

voice = (ROOT / "VexNative" / "VexVoiceIntents.swift").read_text(encoding="utf-8")
bg = (ROOT / "VexNative" / "VexBackgroundAgent.swift").read_text(encoding="utf-8")
for marker in [
    "V148_FOREGROUND_READY_HANDOFF",
    "static var openAppWhenRun = true",
    'vex.phone.foregroundWake.pending',
]:
    if marker not in voice:
        raise SystemExit(f"missing v0.14.8 voice marker: {marker}")
for marker in [
    "applicationDidBecomeActive",
    "750_000_000",
    "VexPhoneBackgroundWorker.runOnce()",
]:
    if marker not in bg:
        raise SystemExit(f"missing v0.14.8 lifecycle marker: {marker}")
print("PASS v0.14.8 build chain")
