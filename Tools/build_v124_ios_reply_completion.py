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


run("Tools/build_v123_ios_voice_field_fix.py")
run("Tools/apply_v124_reply_completion_ios.py")

app = (ROOT / "VexNative" / "AppModel.swift").read_text(encoding="utf-8")
content = (ROOT / "VexNative" / "ContentView.swift").read_text(encoding="utf-8")

for marker in [
    'V124_REPLY_COMPLETION_IOS = "v0.12.4-complete-spoken-replies-v1"',
    "finishReplyAtNaturalBoundary",
    "finalAnswer = finishReplyAtNaturalBoundary(finalAnswer)",
]:
    if marker not in app:
        raise SystemExit(f"final v0.12.4 reply marker missing: {marker}")
if "webGroundedTurn ? 240 : 128" not in app and "maxNewTokens = 128" not in app:
    raise SystemExit("final v0.12.4 conversational token budget missing")
for marker in [
    'V123_LOUD_SPEAKER_PLAYBACK = "v0.12.3-media-speaker-session-v1"',
    'V121_VOICE_FOUNDATION_IOS = "v0.12.1-swap-ready-voice-v1"',
    "func interruptSpeechAndListen()",
]:
    if marker not in content:
        raise SystemExit(f"final v0.12.4 inherited voice marker missing: {marker}")

print("PASS v0.12.4 iOS complete spoken reply chain")
