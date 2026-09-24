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

run("Tools/build_v145_roaming_persistence.py")

voice = (ROOT / "VexNative" / "VexVoiceIntents.swift").read_text(encoding="utf-8")
for marker in [
    "V146_FOREGROUND_COMMAND_HANDOFF",
    "struct VexVoiceCommandIntent: AppIntent",
    "static var openAppWhenRun = true",
]:
    if marker not in voice:
        raise SystemExit(f"missing v0.14.6 marker: {marker}")

quick = voice.split("struct VexQuickActionIntent: AppIntent", 1)[1].split("struct VexVoiceCommandIntent: AppIntent", 1)[0]
if "static var openAppWhenRun = false" not in quick:
    raise SystemExit("quick actions must remain background-capable")

print("PASS v0.14.6 foreground command handoff")

# retrigger after inherited check fix
