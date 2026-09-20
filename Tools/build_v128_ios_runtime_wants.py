#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def run(path: str) -> None:
    print(f"==> {path}", flush=True)
    result = subprocess.run([sys.executable, path], cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(result.returncode)

run("Tools/build_v127_ios_inline_stage_direction_fix.py")
run("Tools/apply_v128_runtime_wants_ios.py")

brain = (ROOT / "VexNative" / "Views" / "BrainView.swift").read_text(encoding="utf-8")
app = (ROOT / "VexNative" / "AppModel.swift").read_text(encoding="utf-8")

for marker in [
    'V128_RUNTIME_WANTS_IOS = "v0.12.8-runtime-wants-v1"',
    "V128_RUNTIME_WANTS_STATE",
    'Section("Vex runtime + wants")',
    'bridgeJSON(path: "/autonomy/requests")',
    "V128_RUNTIME_WANTS_AUTREFRESH",
]:
    if marker not in brain:
        raise SystemExit(f"final v0.12.8 Brain marker missing: {marker}")

for marker in [
    'V127_INLINE_STAGE_DIRECTION_FIX_IOS = "v0.12.7-inline-stage-direction-v1"',
    "enforceCompletedVisibleReply",
]:
    if marker not in app:
        raise SystemExit(f"final v0.12.8 inherited dialogue marker missing: {marker}")

print("PASS v0.12.8 live Runtime + Wants chain")
