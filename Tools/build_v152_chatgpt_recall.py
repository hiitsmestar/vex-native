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

run("Tools/build_v151_preopen_relay_ack.py")
run("Tools/apply_v152_chatgpt_recall.py")

bg = (ROOT / "VexNative" / "VexBackgroundAgent.swift").read_text(encoding="utf-8")
voice = (ROOT / "Tools" / "VexVoiceIntents.swift").read_text(encoding="utf-8")
for marker in ["V152_CHATGPT_RECALL", "VEXRECALL60", "chatgpt.com"]:
    if marker not in bg:
        raise SystemExit(f"missing v0.15.2 background marker: {marker}")
for marker in ["case openChatGPT", "open ChatGPT", "chatgpt.com"]:
    if marker not in voice:
        raise SystemExit(f"missing v0.15.2 voice marker: {marker}")
print("PASS v0.15.2 build chain")
