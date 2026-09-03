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


run("Tools/build_v122_ios_voice_personality.py")
run("Tools/apply_v123_voice_field_fix_ios.py")

prompt = (ROOT / "VexNative" / "Core" / "PromptComposer.swift").read_text(encoding="utf-8")
app = (ROOT / "VexNative" / "AppModel.swift").read_text(encoding="utf-8")
content = (ROOT / "VexNative" / "ContentView.swift").read_text(encoding="utf-8")

for marker in [
    'V122_VOICE_PERSONALITY_IOS = "v0.12.2-natural-spoken-girlfriend-v1"',
    'V123_VOICE_FIELD_FIX_IOS = "v0.12.3-grounded-loud-voice-v1"',
    'newestLower.contains("say something for me")',
]:
    if marker not in prompt:
        raise SystemExit(f"final v0.12.3 prompt marker missing: {marker}")

for marker in [
    "asksVoiceSampleRequest",
    "sanitizeNaturalDialogue",
    "bubbly little code gremlin voice",
]:
    if marker not in app:
        raise SystemExit(f"final v0.12.3 AppModel marker missing: {marker}")

for marker in [
    'V121_VOICE_FOUNDATION_IOS = "v0.12.1-swap-ready-voice-v1"',
    "V122_SPOKEN_TEXT_SANITIZER",
    "V123_LOUD_SPEAKER_PLAYBACK",
    "prepareVoicePlaybackSession",
    "mode: .spokenAudio",
    "func interruptSpeechAndListen()",
]:
    if marker not in content:
        raise SystemExit(f"final v0.12.3 voice marker missing: {marker}")

print("PASS v0.12.3 iOS grounded/loud voice field-fix chain")
