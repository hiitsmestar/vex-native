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

run("Tools/build_v152_chatgpt_recall.py")
run("Tools/apply_v153_full_recall_prompt.py")

bg = (ROOT / "VexNative" / "VexBackgroundAgent.swift").read_text(encoding="utf-8")
for marker in ["V153_FULL_RECALL_PROMPT", "UIPasteboard.general.string = remote.command", 'URLQueryItem(name: "prompt", value: command)']:
    if marker not in bg:
        raise SystemExit(f"missing v0.15.3 marker: {marker}")
print("PASS v0.15.3 build chain")
