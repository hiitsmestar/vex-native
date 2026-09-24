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

run("Tools/build_v150_foreground_result_grace.py")
run("Tools/apply_v151_preopen_relay_ack.py")

bg = (ROOT / "VexNative" / "VexBackgroundAgent.swift").read_text(encoding="utf-8")
for marker in ["V151_PREOPEN_RELAY_ACK", "foregroundOpenURL", "opening it on the iPhone"]:
    if marker not in bg:
        raise SystemExit(f"missing v0.15.1 marker: {marker}")
print("PASS v0.15.1 build chain")
