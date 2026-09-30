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

run("Tools/build_v136_vexnative_link.py")
run("Tools/apply_v137_vexnative_relay.py")

content = (ROOT / "VexNative" / "ContentView.swift").read_text(encoding="utf-8")
for marker in [
    'V137_VEXNATIVE_RELAY = "v0.13.7-vexnative-relay-v1"',
    'parts.port = 8771',
    'let a2a = native["a2a"] as? [String: Any]',
    'path: "/vexnative/status"',
    'path: "/vexnative/autonomy"',
    'PhoneRemoteCommandRelay.shared.run(app: app)',
]:
    if marker not in content:
        raise SystemExit(f"v0.13.7 marker missing: {marker}")
print("PASS v0.13.7 VexNative relay chain")
