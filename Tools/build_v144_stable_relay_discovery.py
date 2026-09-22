#!/usr/bin/env python3
from __future__ import annotations
import subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run(p):
    print(f"==> {p}", flush=True)
    r=subprocess.run([sys.executable,p],cwd=ROOT)
    if r.returncode: raise SystemExit(r.returncode)
run("Tools/build_v143_roaming_relay_fallback.py")
run("Tools/apply_v144_stable_relay_discovery.py")
bg=(ROOT/"VexNative"/"VexBackgroundAgent.swift").read_text(encoding="utf-8")
for m in ["V144_STABLE_RELAY_DISCOVERY","remoteRelayDiscoveryURL","refreshRemoteRelayDiscovery()","reloadIgnoringLocalAndRemoteCacheData"]:
    if m not in bg: raise SystemExit(f"missing v0.14.4 marker {m}")
print("PASS v0.14.4 build chain")
