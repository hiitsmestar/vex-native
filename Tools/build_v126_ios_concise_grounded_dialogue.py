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


run("Tools/build_v125_ios_hard_reply_completion.py")
run("Tools/apply_v126_concise_grounded_dialogue_ios.py")

app = (ROOT / "VexNative" / "AppModel.swift").read_text(encoding="utf-8")
prompt = (ROOT / "VexNative" / "Core" / "PromptComposer.swift").read_text(encoding="utf-8")
content = (ROOT / "VexNative" / "ContentView.swift").read_text(encoding="utf-8")

for marker in [
    "enforceCompletedVisibleReply",
    "V126_STAGE_DIRECTION_LINE_FILTER",
]:
    if marker not in app:
        raise SystemExit(f"final v0.12.6 app marker missing: {marker}")
for marker in [
    'V126_CONCISE_GROUNDED_DIALOGUE_IOS = "v0.12.6-concise-grounded-dialogue-v1"',
    "Keep ordinary spoken replies compact: usually 2 to 4 complete sentences.",
    "Never invent a memory or past event.",
    "For questions about your own voice, behavior, feelings, or improvements, answer about Vex",
]:
    if marker not in prompt:
        raise SystemExit(f"final v0.12.6 prompt marker missing: {marker}")
if "webGroundedTurn ? 256 : 224" not in app and "maxNewTokens = 224" not in app:
    raise SystemExit("final v0.12.6 token budget missing")
for marker in [
    'V123_LOUD_SPEAKER_PLAYBACK = "v0.12.3-media-speaker-session-v1"',
    'V121_VOICE_FOUNDATION_IOS = "v0.12.1-swap-ready-voice-v1"',
    "func interruptSpeechAndListen()",
]:
    if marker not in content:
        raise SystemExit(f"final v0.12.6 inherited voice marker missing: {marker}")

print("PASS v0.12.6 concise grounded dialogue chain")
