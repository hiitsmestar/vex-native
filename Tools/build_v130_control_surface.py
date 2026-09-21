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
run("Tools/apply_v130_control_surface.py")

content = (ROOT / "VexNative" / "ContentView.swift").read_text(encoding="utf-8")
models = (ROOT / "VexNative" / "Core" / "BrainModels.swift").read_text(encoding="utf-8")

for marker in [
    'V130_CONTROL_SURFACE = "v0.13.0-control-surface-v1"',
    "struct VexChatView: View",
    "struct ContentView: View",
    'Label("System", systemImage: "network")',
    'Label("Art", systemImage: "sparkles.rectangle.stack")',
    'Label("Memory", systemImage: "brain.head.profile")',
    'Label("Phone", systemImage: "iphone")',
    "/autonomy/requests",
    "/adaptive/status",
    "/art/health",
    "PCArtRouter.tryHandle",
    "PhoneToolRouter.tryHandle",
]:
    if marker not in content:
        raise SystemExit(f"final v0.13.0 marker missing: {marker}")

if content.count("struct ContentView: View") != 1:
    raise SystemExit("v0.13.0 must expose exactly one ContentView shell")
if content.count("struct VexChatView: View") != 1:
    raise SystemExit("v0.13.0 must preserve exactly one VexChatView")
if 'Text("LOCAL GIRLFRIEND ENGINE")' in content:
    raise SystemExit("old girlfriend-engine title survived v0.13.0 redesign")
if "enum MemoryKind: String, Codable, Sendable, CaseIterable" not in models:
    raise SystemExit("MemoryKind CaseIterable upgrade missing")

print("PASS v0.13.0 VexNative control-surface build chain")
