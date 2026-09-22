#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "Tools"
APP = ROOT / "VexNative"

for src_name, dst_name in [
    ("VexBadQueryProbeV136.c", "VexBadQueryProbe.c"),
    ("VexBadQueryDiagnosticsV136.swift", "VexBadQueryDiagnostics.swift"),
]:
    src = TOOLS / src_name
    dst = APP / dst_name
    if not src.exists():
        raise SystemExit(f"missing {src}")
    shutil.copyfile(src, dst)

probe = (APP / "VexBadQueryProbe.c").read_text(encoding="utf-8")
diag = (APP / "VexBadQueryDiagnostics.swift").read_text(encoding="utf-8")
for marker in [
    "vex_bad_query_grant_read_stage",
    'buildMarker = "v0.13.6-read-only-stage-diagnostics-v1"',
    "MobileGestalt /private",
    "Applications /private",
    "stage token",
]:
    if marker == "stage token":
        if 'return "token"' not in diag:
            raise SystemExit("stage mapping missing")
    elif marker not in probe + "\n" + diag:
        raise SystemExit(f"v0.13.6 marker missing: {marker}")
for forbidden in ["O_WRONLY","O_RDWR","unlink(","rename(","removeItem(","createFile(","replaceItem(",".write(to:"]:
    if forbidden in probe or forbidden in diag:
        raise SystemExit(f"mutation primitive forbidden: {forbidden}")
print("PASS v0.13.6 staged read-only diagnostics patch")
