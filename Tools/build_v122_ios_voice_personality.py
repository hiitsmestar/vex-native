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


run("Tools/build_v121_ios_voice_foundation.py")
run("Tools/apply_v122_voice_personality_ios.py")

prompt = (ROOT / "VexNative" / "Core" / "PromptComposer.swift").read_text(encoding="utf-8")
content = (ROOT / "VexNative" / "ContentView.swift").read_text(encoding="utf-8")

for marker in [
    'V122_VOICE_PERSONALITY_IOS = "v0.12.2-natural-spoken-girlfriend-v1"',
    "let asksVoiceTest",
    "NATURAL SPOKEN GIRLFRIEND VOICE",
    "Never claim a memory, past experience",
    "bright, bubbly, quick, playful, slightly ditzy e-girl energy",
]:
    if marker not in prompt:
        raise SystemExit(f"final v0.12.2 prompt marker missing: {marker}")

for marker in [
    'V121_VOICE_FOUNDATION_IOS = "v0.12.1-swap-ready-voice-v1"',
    "case automatic",
    "func interruptSpeechAndListen()",
    "V122_SPOKEN_TEXT_SANITIZER",
    '"glittery eyes"',
]:
    if marker not in content:
        raise SystemExit(f"final v0.12.2 voice marker missing: {marker}")

print("PASS v0.12.2 iOS natural voice personality chain")
