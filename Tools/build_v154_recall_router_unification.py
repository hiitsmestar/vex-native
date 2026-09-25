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

run("Tools/build_v153_full_recall_prompt.py")
run("Tools/apply_v154_recall_router_unification.py")

content = (ROOT / "VexNative" / "ContentView.swift").read_text(encoding="utf-8")
for marker in [
    "V154_RECALL_ROUTER_UNIFICATION",
    'remote.command.lowercased().contains("vexrecall60")',
    'URLQueryItem(name: "prompt", value: remote.command)',
]:
    if marker not in content:
        raise SystemExit(f"missing v0.15.4 marker: {marker}")

print("PASS v0.15.4 build chain")
