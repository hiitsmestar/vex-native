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

# The branch now stores the cumulative v0.16.1 source directly.
# apply_v161 remains idempotent and verifies the required v0.16.0 lineage.
run("Tools/apply_v161_unified_core_client.py")

content_view = (ROOT / "VexNative" / "ContentView.swift").read_text(encoding="utf-8")
app_source = (ROOT / "VexNative" / "VexNativeApp.swift").read_text(encoding="utf-8")
project = (ROOT / "VexNative.xcodeproj" / "project.pbxproj").read_text(encoding="utf-8")
for required in ["VexVoiceIntents.swift", "VexBackgroundAgent.swift"]:
    path = ROOT / "VexNative" / required
    if not path.exists() or path.stat().st_size < 1000:
        raise SystemExit(f"missing v0.16.1 source file: {required}")

for marker in [
    'V161_UNIFIED_CORE_CLIENT = "v0.16.1-unified-core-client-v1"',
    "static let shared = VexNativeA2AClient()",
    "func answer(_ message: String, quiet: Bool = false)",
    "func streamAnswer(_ message: String)",
    'relayURLs(path: "/vexnative/send/stream")',
    "func cancelActiveWork()",
    "func retryFailedWork()",
    '@StateObject private var core = VexNativeA2AClient.shared',
    "V160_A2A_ROAMING_FALLBACK",
]:
    if marker not in content_view:
        raise SystemExit(f"missing v0.16.1 ContentView marker: {marker}")

for marker in [
    "static func streamLines(",
    "URLSession.shared.bytes(for: request)",
    "isRemoteRelayURL",
]:
    if marker not in app_source:
        raise SystemExit(f"missing v0.16.1 transport marker: {marker}")

for marker in [
    "MARKETING_VERSION = 0.16.1;",
    "CURRENT_PROJECT_VERSION = 161;",
]:
    if marker not in project:
        raise SystemExit(f"missing v0.16.1 build lineage marker: {marker}")

# coherent source snapshot v2: UI, app model, storage, memory and views are synced together.
print("PASS v0.16.1 cumulative unified-core source verification")

support_checks = {
    "VexNative/AppModel.swift": ["pcBrainConnected", "pcBrainStatus", "pendingPhotoData", "pendingPhotoContext"],
    "VexNative/Storage/LocalStore.swift": ["saveAttachment", "attachmentData"],
    "VexNative/Core/BrainModels.swift": ["imageFilename", "CaseIterable"],
}
for rel, markers in support_checks.items():
    source = (ROOT / rel).read_text(encoding="utf-8")
    for marker in markers:
        if marker not in source:
            raise SystemExit(f"missing v0.16.1 support marker {marker} in {rel}")
print("PASS v0.16.1 support-source coherence")
