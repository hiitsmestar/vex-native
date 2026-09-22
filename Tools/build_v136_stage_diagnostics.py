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

run("Tools/build_v135_bad_query_probe.py")
run("Tools/apply_v136_stage_diagnostics.py")

content=(ROOT/"VexNative"/"ContentView.swift").read_text(encoding="utf-8")
diag=(ROOT/"VexNative"/"VexBadQueryDiagnostics.swift").read_text(encoding="utf-8")
probe=(ROOT/"VexNative"/"VexBadQueryProbe.c").read_text(encoding="utf-8")
voice=(ROOT/"VexNative"/"VexVoiceIntents.swift").read_text(encoding="utf-8")
for marker in [
    "VexBadQueryProbeView()",
    'v0.13.6-read-only-stage-diagnostics-v1',
    "vex_bad_query_grant_read_stage",
    'V134_SIRI_HARDWARE_ROUTING = "v0.13.4-native-system-routing-v1"',
    "PhoneRemoteCommandRelay.shared.run(app: app)",
]:
    if marker not in content+"\n"+diag+"\n"+probe+"\n"+voice:
        raise SystemExit(f"v0.13.6 inherited/diagnostic marker missing: {marker}")
print("PASS v0.13.6 chain")
