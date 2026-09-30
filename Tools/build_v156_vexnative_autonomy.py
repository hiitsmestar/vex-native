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

run("Tools/build_v155_local_direct_brain.py")
run("Tools/apply_v156_vexnative_autonomy.py")

text = (ROOT / "VexNative" / "ContentView.swift").read_text(encoding="utf-8")
for marker in [
    'V156_VEXNATIVE_AUTONOMY = "v0.15.6-vexnative-autonomy-v1"',
    'parts.port = 8771',
    'path: "/vexnative/status"',
    'path: "/vexnative/autonomy"',
    'Send goal to VexNative',
    'LOCAL DIRECT MODE — V155_LOCAL_DIRECT_BRAIN',
    'V132_PHONE_COMMAND_RELAY = "v0.13.2-phone-command-relay-v1"',
]:
    if marker not in text:
        raise SystemExit(f"missing v0.15.6 marker: {marker}")

print("PASS v0.15.6 build chain")
