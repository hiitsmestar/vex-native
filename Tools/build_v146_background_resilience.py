#!/usr/bin/env python3
from __future__ import annotations
import subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def run(path):
    print(f"==> {path}", flush=True)
    r = subprocess.run([sys.executable, path], cwd=ROOT)
    if r.returncode:
        raise SystemExit(r.returncode)

run("Tools/build_v145_erosion_bad_query_fix.py")
run("Tools/apply_v146_background_resilience.py")

combined = "\n".join([
    (ROOT/"VexNative"/"VexBackgroundAgent.swift").read_text(encoding="utf-8"),
    (ROOT/"VexNative"/"VexErosionBadQuery.c").read_text(encoding="utf-8"),
    (ROOT/"VexNative"/"VexErosionBadQueryDiagnostics.swift").read_text(encoding="utf-8"),
])

for required in [
    "V146_BACKGROUND_RESILIENCE",
    "startResilienceWatchdog()",
    "watchdogHeartbeat",
    "V144_GITHUB_ROAMING_BOOTSTRAP",
    "v0.14.5-erosion-bad-query-readonly-v1",
]:
    if required not in combined:
        raise SystemExit(f"missing {required}")

print("PASS v0.14.6 build chain")
