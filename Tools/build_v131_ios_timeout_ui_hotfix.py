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

run("Tools/build_v130_ios_control_surface.py")
run("Tools/apply_v131_ios_timeout_ui_hotfix.py")

content = (ROOT / "VexNative" / "ContentView.swift").read_text(encoding="utf-8")
brain = (ROOT / "VexNative" / "Views" / "BrainView.swift").read_text(encoding="utf-8")
app = (ROOT / "VexNative" / "VexNativeApp.swift").read_text(encoding="utf-8")
app_model = (ROOT / "VexNative" / "AppModel.swift").read_text(encoding="utf-8")

for marker in [
    'V131_TIMEOUT_UI_HOTFIX = "v0.13.1-timeout-ui-v1"',
    "struct VexChatView: View",
    "PCArtRouter.tryHandle",
    "PhoneToolRouter.tryHandle",
    "import Vision",
    "CameraCaptureView",
    ".dynamicTypeSize(.small ... .large)",
]:
    if marker not in content:
        raise SystemExit(f"v0.13.1 inherited/UI marker missing: {marker}")

if "V131_BRAIN_DYNAMIC_TYPE_CAP" not in brain or ".dynamicTypeSize(.small ... .large)" not in brain:
    raise SystemExit("v0.13.1 Brain scaling cap missing")

for marker in [
    'path == "/llm/chat"',
    "configuration.timeoutIntervalForRequest = 95",
    "configuration.timeoutIntervalForResource = 100",
    'path.hasPrefix("/art/")',
    "configuration.timeoutIntervalForRequest = 180",
    "configuration.timeoutIntervalForResource = 240",
]:
    if marker not in app:
        raise SystemExit(f"v0.13.1 transport marker missing: {marker}")

if "request.timeoutInterval = 90" not in content:
    raise SystemExit("PC cognition request timeout regressed")
if 'V127_INLINE_STAGE_DIRECTION_FIX_IOS = "v0.12.7-inline-stage-direction-v1"' not in app_model:
    raise SystemExit("v0.12.7 dialogue fix missing")

print("PASS v0.13.1 VexNative timeout/UI hotfix chain")
