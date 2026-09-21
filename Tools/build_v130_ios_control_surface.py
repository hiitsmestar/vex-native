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

run("Tools/build_v127_ios_inline_stage_direction_fix.py")
run("Tools/apply_v130_ios_control_surface.py")

content = (ROOT / "VexNative" / "ContentView.swift").read_text(encoding="utf-8")
app = (ROOT / "VexNative" / "AppModel.swift").read_text(encoding="utf-8")

for marker in [
    'V130_CONTROL_SURFACE = "v0.13.0-control-surface-v1"',
    "struct VexChatView: View",
    "struct ContentView: View",
    'Text("VEXNATIVE")',
    'Label("Chat"',
    'Label("System"',
    'Label("Art"',
    'Label("Memory"',
    'Label("Phone"',
    '"/adaptive/status"',
    '"/autonomy/requests"',
    '"/memory/status"',
    '"/art/health"',
    '"/art/generate"',
    "UNUserNotificationCenter",
]:
    if marker not in content:
        raise SystemExit(f"final v0.13.0 content marker missing: {marker}")

if 'LOCAL GIRLFRIEND ENGINE' in content:
    raise SystemExit("legacy girlfriend-engine title survived v0.13.0")

for marker in [
    'V127_INLINE_STAGE_DIRECTION_FIX_IOS = "v0.12.7-inline-stage-direction-v1"',
    "V127_INLINE_STAGE_DIRECTION_FILTER",
    "enforceCompletedVisibleReply",
]:
    if marker not in app:
        raise SystemExit(f"v0.12.7 inherited marker missing: {marker}")

print("PASS v0.13.0 VexNative control-surface chain")