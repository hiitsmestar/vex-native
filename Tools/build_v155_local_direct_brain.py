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
run("Tools/apply_v155_local_direct_brain.py")

checks = {
    "VexNative/Storage/ModelLibrary.swift": [
        "V155_LOCAL_DIRECT_BRAIN",
        "qwen3-0.6b-abliterated-q4_k_m.gguf",
    ],
    "VexNative/AppModel.swift": [
        "maxNewTokens = 160",
        "temperature = 0.60",
        "topK = 20",
    ],
    "VexNative/Core/PromptComposer.swift": [
        "LOCAL DIRECT MODE — V155_LOCAL_DIRECT_BRAIN",
    ],
    "VexNative/ContentView.swift": [
        "LOCAL DIRECT MODE — V155_LOCAL_DIRECT_BRAIN",
        'URLQueryItem(name: "safesearch", value: "0")',
    ],
}
for rel, markers in checks.items():
    text = (ROOT / rel).read_text(encoding="utf-8")
    for marker in markers:
        if marker not in text:
            raise SystemExit(f"missing v0.15.5 marker {marker!r} in {rel}")
print("PASS v0.15.5 build chain")
