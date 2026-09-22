#!/usr/bin/env python3
from __future__ import annotations
import subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def run(path: str) -> None:
    print(f"==> {path}", flush=True)
    r = subprocess.run([sys.executable, path], cwd=ROOT)
    if r.returncode != 0:
        raise SystemExit(r.returncode)

run("Tools/build_v141_phone_commander_surface.py")
run("Tools/apply_v142_remote_roaming_relay.py")

for file, markers in {
    "VexNative/VexNativeApp.swift": ["V142_REMOTE_ROAMING_RELAY", "isRemoteRelayURL", ".trycloudflare.com"],
    "VexNative/ContentView.swift": ["V142_REMOTE_ROAMING_RELAY", "parts.port = nil"],
}.items():
    text=(ROOT/file).read_text(encoding="utf-8")
    for marker in markers:
        if marker not in text:
            raise SystemExit(f"missing v0.14.2 marker {marker} in {file}")
print("PASS v0.14.2 remote roaming relay chain")
