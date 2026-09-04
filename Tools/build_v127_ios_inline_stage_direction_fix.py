#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(path: str) -> None:
    print(f"==> {path}", flush=True)
    result = subprocess.run([sys.executable, path], cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


run("Tools/build_v126_ios_concise_grounded_dialogue.py")
run("Tools/apply_v127_inline_stage_direction_fix_ios.py")

app = (ROOT / "VexNative" / "AppModel.swift").read_text(encoding="utf-8")
content = (ROOT / "VexNative" / "ContentView.swift").read_text(encoding="utf-8")

for marker in [
    'V127_INLINE_STAGE_DIRECTION_FIX_IOS = "v0.12.7-inline-stage-direction-v1"',
    "V127_INLINE_STAGE_DIRECTION_FILTER",
    '"snaps fingers"',
    "enforceCompletedVisibleReply",
]:
    if marker not in app:
        raise SystemExit(f"final v0.12.7 app marker missing: {marker}")
for marker in [
    'V123_LOUD_SPEAKER_PLAYBACK = "v0.12.3-media-speaker-session-v1"',
    'V121_VOICE_FOUNDATION_IOS = "v0.12.1-swap-ready-voice-v1"',
    "func interruptSpeechAndListen()",
]:
    if marker not in content:
        raise SystemExit(f"final v0.12.7 inherited voice marker missing: {marker}")

print("PASS v0.12.7 inline stage-direction cleanup chain")
