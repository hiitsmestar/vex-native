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

run("Tools/build_v135_bad_query_probe.py")
run("Tools/apply_v136_vexnative_link.py")

content = (ROOT / "VexNative" / "ContentView.swift").read_text(encoding="utf-8")
bridge = (ROOT / "Bridge" / "vex_bridge.py").read_text(encoding="utf-8")

for marker in [
    'V136_VEXNATIVE_LINK = "v0.13.6.1-vexnative-relay-link-v2"',
    'path: "/vexnative/status"',
    'path: "/vexnative/autonomy"',
    "Send goal to VexNative",
    "setAutonomy(enabled:",
    "createGoal(title:",
    'V132_PHONE_COMMAND_RELAY = "v0.13.2-phone-command-relay-v1"',
    'buildMarker = "v0.13.5-read-only-bad-query-probe-v1"',
]:
    if marker not in content and marker != 'buildMarker = "v0.13.5-read-only-bad-query-probe-v1"':
        raise SystemExit(f"v0.13.6.1 content marker missing: {marker}")

diagnostics = (ROOT / "VexNative" / "VexBadQueryDiagnostics.swift").read_text(encoding="utf-8")
if 'buildMarker = "v0.13.5-read-only-bad-query-probe-v1"' not in diagnostics:
    raise SystemExit("v0.13.5 diagnostic inheritance missing")

for marker in [
    'V136_VEXNATIVE_PROXY = "v0.13.6.1-vexnative-proxy-v1"',
    'VEXNATIVE_LOCAL = "http://127.0.0.1:8796"',
    'parsed.path == "/vexnative/status"',
    'parsed.path == "/vexnative/autonomy"',
    'urllib.request.Request',
]:
    if marker not in bridge:
        raise SystemExit(f"v0.13.6.1 Bridge marker missing: {marker}")

print("PASS v0.13.6.1 VexNative phone link chain")
