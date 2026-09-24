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

run("Tools/build_v148_foreground_ready_handoff.py")
run("Tools/apply_v149_serialized_foreground_wake.py")

voice = (ROOT / "VexNative" / "VexVoiceIntents.swift").read_text(encoding="utf-8")
bg = (ROOT / "VexNative" / "VexBackgroundAgent.swift").read_text(encoding="utf-8")
for marker in ["V149_SERIALIZED_FOREGROUND_WAKE", "static var openAppWhenRun = true"]:
    if marker not in voice:
        raise SystemExit(f"missing v0.14.9 voice marker: {marker}")
for marker in ["foregroundWakeTask", "handleForegroundWake()", "guard foregroundWakeTask == nil"]:
    if marker not in bg:
        raise SystemExit(f"missing v0.14.9 background marker: {marker}")
print("PASS v0.14.9 build chain")
