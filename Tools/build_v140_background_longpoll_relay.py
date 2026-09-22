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

run("Tools/build_v139_agent_lifecycle_keepalive.py")
run("Tools/apply_v140_background_longpoll_relay.py")

bg = (ROOT / "VexNative" / "VexBackgroundAgent.swift").read_text(encoding="utf-8")
for marker in [
    'V140_BACKGROUND_LONGPOLL_RELAY = "v0.13.10-background-longpoll-relay-v1"',
    "URLSessionConfiguration.background(withIdentifier: Self.identifier)",
    'parts.path = "/phone/wait"',
    "handleEventsForBackgroundURLSession",
    "sessionSendsLaunchEvents = true",
]:
    if marker not in bg:
        raise SystemExit(f"v0.13.10 build marker missing: {marker}")

print("PASS v0.13.10 background long-poll chain")
