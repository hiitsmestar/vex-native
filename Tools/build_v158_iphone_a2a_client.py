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

run("Tools/build_v155_local_direct_brain.py")
run("Tools/apply_v158_iphone_a2a_client.py")

content = (ROOT / "VexNative" / "ContentView.swift").read_text(encoding="utf-8")
for marker in [
    'V158_IPHONE_A2A_CLIENT = "v0.15.8-iphone-a2a-client-v1"',
    "VexNativeA2APanel()",
    'path: "/vexnative/status"',
    'path: "/vexnative/send"',
    '"agent": "coordinator"',
    "parts.port = 8771",
    "V155_LOCAL_DIRECT_BRAIN",
    "V153_FULL_RECALL_PROMPT",
]:
    if marker not in content and marker != "V153_FULL_RECALL_PROMPT":
        raise SystemExit(f"missing v0.15.8 content marker: {marker}")

bg = (ROOT / "VexNative" / "VexBackgroundAgent.swift").read_text(encoding="utf-8")
if "V153_FULL_RECALL_PROMPT" not in bg:
    raise SystemExit("missing inherited v0.15.3 recall marker")

print("PASS v0.15.8 iPhone A2A client chain")
