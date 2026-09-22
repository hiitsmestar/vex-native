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

run("Tools/build_v138_background_agent_foundation.py")
run("Tools/apply_v139_agent_lifecycle_keepalive.py")

bg = (ROOT / "VexNative" / "VexBackgroundAgent.swift").read_text(encoding="utf-8")
for marker in [
    'V139_AGENT_LIFECYCLE_KEEPALIVE = "v0.13.9-agent-lifecycle-keepalive-v1"',
    "applicationDidBecomeActive",
    "startForegroundLoop()",
    'beginBackgroundTask(withName: "VexPhoneAgentGrace")',
    "application.backgroundTimeRemaining > 5",
    "BGTaskScheduler.shared.register",
    "VexPhoneBackgroundWorker.runOnce",
]:
    if marker not in bg:
        raise SystemExit(f"v0.13.9 lifecycle marker missing: {marker}")

print("PASS v0.13.9 agent lifecycle keepalive chain")
