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

run("Tools/build_v144_github_roaming_bootstrap.py")
run("Tools/apply_v145_roaming_persistence.py")

bg = (ROOT / "VexNative" / "VexBackgroundAgent.swift").read_text(encoding="utf-8")
for marker in [
    "V145_ROAMING_PERSISTENCE",
    'relayURLs(path: "/phone/wait")',
    "request.timeoutInterval = 35",
    "AVAudioSession.routeChangeNotification",
    "AVAudioSession.mediaServicesWereResetNotification",
]:
    if marker not in bg:
        raise SystemExit(f"missing v0.14.5 marker: {marker}")
print("PASS v0.14.5 build chain")
