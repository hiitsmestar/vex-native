#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
content = (ROOT / "VexNative" / "ContentView.swift").read_text(encoding="utf-8")
app = (ROOT / "VexNative" / "VexNativeApp.swift").read_text(encoding="utf-8")

checks = [
    ("races cognition endpoints", "await withTaskGroup(of: CognitionResult.self)" in content and "group.cancelAll()" in content),
    ("keeps diagnostics", "bridge token rejected" in content and "timeout waiting for Bridge" in content),
    ("keeps last-good retry", "lastCognition" in content and "vex.pc.cognition.lastGoodEndpoint.v1" in content),
    ("compacts request history", "profile.messages.suffix(12)" in content and "String(message.content.prefix(2800))" in content),
    ("compacts persona/profile", "profile.persona.prefix(3600)" in content and "profile.userProfile.prefix(1800)" in content),
    ("compacts current message", "String(original.prefix(3500))" in content),
    ("extends request timeout", "request.timeoutInterval = 125" in content),
    ("extends transport timeout", "configuration.timeoutIntervalForRequest = 130" in app and "configuration.timeoutIntervalForResource = 145" in app),
]

failed = [name for name, ok in checks if not ok]
if failed:
    for name in failed:
        print(f"FAIL {name}")
    raise SystemExit(1)

for name, _ in checks:
    print(f"PASS {name}")
print("v0.11.7.48 PC cognition timeout recovery verified")
