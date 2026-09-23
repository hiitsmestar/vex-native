#!/usr/bin/env python3
from __future__ import annotations
import subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def run(p):
    print(f"==> {p}", flush=True)
    r = subprocess.run([sys.executable, p], cwd=ROOT)
    if r.returncode:
        raise SystemExit(r.returncode)

run("Tools/build_v144_github_roaming_bootstrap.py")
run("Tools/apply_v145_background_resilience.py")

checks = {
    "VexNative/VexBackgroundAgent.swift": [
        "V144_GITHUB_ROAMING_BOOTSTRAP",
        "refreshRoamingBootstrap()",
        "remote-relay.json",
        "V145_BACKGROUND_RESILIENCE",
        "startResilienceWatchdog()",
        "routeChangeNotification",
        "watchdogHeartbeat",
        "VexPhoneBackgroundWorker.runOnce()",
    ]
}

for filename, markers in checks.items():
    text = (ROOT / filename).read_text(encoding="utf-8")
    for marker in markers:
        if marker not in text:
            raise SystemExit(f"missing {marker} in {filename}")

print("PASS v0.14.5 build chain")
