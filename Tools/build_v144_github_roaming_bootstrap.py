#!/usr/bin/env python3
from __future__ import annotations
import subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def run(p):
    print(f"==> {p}", flush=True)
    r = subprocess.run([sys.executable,p],cwd=ROOT)
    if r.returncode:
        raise SystemExit(r.returncode)

run("Tools/build_v143_roaming_relay_fallback.py")
run("Tools/apply_v144_github_roaming_bootstrap.py")

text=(ROOT/"VexNative"/"VexBackgroundAgent.swift").read_text(encoding="utf-8")
for marker in [
    "V144_GITHUB_ROAMING_BOOTSTRAP",
    "refreshRoamingBootstrap()",
    "remote-relay.json",
]:
    if marker not in text:
        raise SystemExit(f"missing {marker}")
print("PASS v0.14.4 build chain")
