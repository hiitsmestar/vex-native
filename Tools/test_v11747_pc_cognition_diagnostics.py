#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
content = (ROOT / "VexNative" / "ContentView.swift").read_text(encoding="utf-8")
app = (ROOT / "VexNative" / "AppModel.swift").read_text(encoding="utf-8")

start = content.find("@MainActor\nprivate enum PCCognitionOverlay {")
end = content.find("\n// MARK: - Vex Housekeeper v0.9.6 active maintenance", start)
if start < 0 or end < 0:
    raise SystemExit("PCCognitionOverlay block not found")
overlay = content[start:end]

exclusion_start = overlay.find("let exclusions = [")
exclusion_end = overlay.find("        ]", exclusion_start)
if exclusion_start < 0 or exclusion_end < 0:
    raise SystemExit("PC cognition exclusion block not found")
exclusions = overlay[exclusion_start:exclusion_end]

checks = [
    ("diagnostic result enum", "private enum CognitionResult: Sendable" in overlay),
    ("nonisolated worker helpers", "nonisolated private static func networkFailure" in overlay and "nonisolated private static func httpFailure" in overlay),
    ("sanitized HTTP status diagnostics", "httpFailure(status: http.statusCode, data: data)" in overlay),
    ("token rejection diagnostic", "bridge token rejected" in overlay),
    ("route missing diagnostic", '"/llm/chat route missing"' in overlay),
    ("no model diagnostic", '"no local cognition model"' in overlay),
    ("timeout diagnostic", '"timeout waiting for Bridge"' in overlay),
    ("TLS diagnostic", '"TLS handshake failed"' in overlay),
    ("last-good cognition retry", "lastCognition" in overlay and "vex.pc.cognition.lastGoodEndpoint.v1" in overlay),
    ("memory sync stays Bridge-only", "guard isBridgeEndpoint(endpoint), let url = endpointURL(endpoint, path: \"/memory/sync\")" in overlay),
    ("computer questions not excluded", '"computer"' not in exclusions and '" pc"' not in exclusions),
    ("phone questions not excluded", '"iphone"' not in exclusions and '"phone"' not in exclusions),
    ("fallback reports stored reason", "I couldn't use the PC cognition path for that turn" in app),
]

failed = [name for name, ok in checks if not ok]
if failed:
    for name in failed:
        print(f"FAIL {name}")
    raise SystemExit(1)

for name, _ in checks:
    print(f"PASS {name}")
print("v0.11.7.47 PC cognition diagnostics verified")
