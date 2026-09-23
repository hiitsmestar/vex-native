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

run("Tools/build_v144_github_roaming_bootstrap.py")
run("Tools/apply_v145_erosion_bad_query_fix.py")

combined = "\n".join([
    (ROOT/"VexNative"/"VexErosionBadQuery.c").read_text(encoding="utf-8"),
    (ROOT/"VexNative"/"VexErosionBadQueryDiagnostics.swift").read_text(encoding="utf-8"),
    (ROOT/"VexNative"/"ContentView.swift").read_text(encoding="utf-8"),
    (ROOT/"VexNative"/"VexNativeApp.swift").read_text(encoding="utf-8"),
])
for marker in [
    "v0.14.5-erosion-bad-query-readonly-v1",
    "vex_bad_query_list",
    "VexErosionBadQueryProbeView()",
    "VEX_EROSION_BAD_QUERY_AUTORUN",
    "V144_GITHUB_ROAMING_BOOTSTRAP",
]:
    if marker not in combined:
        raise SystemExit(f"missing {marker}")
print("PASS v0.14.5 build chain")
