#!/usr/bin/env python3
from __future__ import annotations
import subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def run(path: str) -> None:
    print(f"==> {path}", flush=True)
    r = subprocess.run([sys.executable, path], cwd=ROOT)
    if r.returncode != 0:
        raise SystemExit(r.returncode)

run("Tools/build_v140_persistent_phone_agent.py")
run("Tools/apply_v141_phone_commander_surface.py")

content=(ROOT/"VexNative"/"ContentView.swift").read_text(encoding="utf-8")
for marker in [
    'V141_PHONE_COMMANDER_SURFACE = "v0.14.1-phone-commander-surface-v1"',
    "browserSearchQuery",
    "fetchPageText",
    "downloadToDocuments",
    "listDocuments",
    "readDocument",
]:
    if marker not in content:
        raise SystemExit(f"missing v0.14.1 marker: {marker}")
print("PASS v0.14.1 phone commander surface chain")
