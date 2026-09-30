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

run("Tools/build_v158_iphone_a2a_client.py")
run("Tools/apply_v159_iphone_a2a_autonomy.py")

content = (ROOT / "VexNative" / "ContentView.swift").read_text(encoding="utf-8")
for marker in [
    'V159_IPHONE_A2A_AUTONOMY = "v0.15.9-iphone-a2a-autonomy-v1"',
    'V158_IPHONE_A2A_CLIENT',
    'path: "/vexnative/status"',
    'path: "/vexnative/send"',
    'path: "/vexnative/autonomy"',
    '"action": "create_goal"',
    'Label("Resume", systemImage: "play.fill")',
    'Label("Pause", systemImage: "pause.fill")',
    'TextField("Give VexNative a new goal"',
]:
    if marker not in content:
        raise SystemExit(f"missing v0.15.9 marker: {marker}")

print("PASS v0.15.9 iPhone A2A autonomy chain")
