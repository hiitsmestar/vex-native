#!/usr/bin/env python3
from __future__ import annotations
import subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run(p):
    print(f"==> {p}", flush=True)
    r=subprocess.run([sys.executable,p],cwd=ROOT)
    if r.returncode: raise SystemExit(r.returncode)
run("Tools/build_v142_remote_roaming_relay.py")
run("Tools/apply_v143_roaming_relay_fallback.py")
for f,m in {
 "VexNative/VexBackgroundAgent.swift":["V143_ROAMING_RELAY_FALLBACK","relayURLs(path:","primaryToken"],
 "VexNative/ContentView.swift":["V143_ROAMING_RELAY_FALLBACK","primaryToken"],
}.items():
    t=(ROOT/f).read_text(encoding="utf-8")
    for x in m:
        if x not in t: raise SystemExit(f"missing {x} in {f}")
print("PASS v0.14.3 build chain")
