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

run("Tools/build_v159_iphone_a2a_autonomy.py")
run("Tools/apply_v160_a2a_roaming_fallback.py")

content = (ROOT / "VexNative" / "ContentView.swift").read_text(encoding="utf-8")
for marker in [
    'V160_A2A_ROAMING_FALLBACK = "v0.16.0-a2a-roaming-fallback-v1"',
    'private func relayURLs(path:',
    '"vex.phone.remoteRelay.discoveredEndpoint"',
    'isRemoteRelayURL',
    'let urls = relayURLs(path: path)',
    'V159_IPHONE_A2A_AUTONOMY',
]:
    if marker not in content:
        raise SystemExit(f"missing v0.16.0 marker: {marker}")

print("PASS v0.16.0 build chain")
