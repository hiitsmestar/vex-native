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
run("Tools/apply_v140_persistent_phone_agent.py")

bg = (ROOT / "VexNative" / "VexBackgroundAgent.swift").read_text(encoding="utf-8")
for marker in [
    'V140_PERSISTENT_PHONE_AGENT = "v0.14.0-persistent-phone-agent-v1"',
    "AVAudioSession.sharedInstance()",
    "AVAudioPlayerNode()",
    "audioPlayer.scheduleBuffer",
    "options: [.loops]",
    "startPersistentAgent()",
    "VexPhoneBackgroundWorker.runOnce()",
]:
    if marker not in bg:
        raise SystemExit(f"v0.14.0 persistent marker missing: {marker}")

print("PASS v0.14.0 persistent phone agent chain")
