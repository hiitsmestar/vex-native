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

run("Tools/build_v149_serialized_foreground_wake.py")
run("Tools/apply_v150_foreground_result_grace.py")

bg = (ROOT / "VexNative" / "VexBackgroundAgent.swift").read_text(encoding="utf-8")
for marker in [
    "V150_FOREGROUND_RESULT_GRACE",
    "foregroundWakeBackgroundTaskIdentifier",
    "VexForegroundWakeResult",
]:
    if marker not in bg:
        raise SystemExit(f"missing v0.15.0 marker: {marker}")
print("PASS v0.15.0 build chain")
