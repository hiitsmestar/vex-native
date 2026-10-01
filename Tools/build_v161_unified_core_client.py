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

run("Tools/build_v160_a2a_roaming_fallback.py")
run("Tools/apply_v161_unified_core_client.py")

content = (ROOT / "VexNative" / "ContentView.swift").read_text(encoding="utf-8")
for marker in [
    'V161_UNIFIED_CORE_CLIENT = "v0.16.1-unified-core-client-v1"',
    "static let shared = VexNativeA2AClient()",
    "func answer(_ message: String, quiet: Bool = false)",
    '@StateObject private var core = VexNativeA2AClient.shared',
    "V160_A2A_ROAMING_FALLBACK",
]:
    if marker not in content:
        raise SystemExit(f"missing v0.16.1 marker: {marker}")
print("PASS v0.16.1 cumulative build chain")
