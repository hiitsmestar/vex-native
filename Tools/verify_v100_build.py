#!/usr/bin/env python3
from pathlib import Path

art = Path("Tools/VexArtWorker.py").read_text(encoding="utf-8")
remote = Path("Tools/VexRemoteSupport.py").read_text(encoding="utf-8")
checks = {
    "art version": 'VERSION = "0.10.0"' in art,
    "safe sampler": '"sampler_name": "euler"' in art,
    "render test UI": 'Render Test' in art,
    "busy render protection": 'not _BUSY and time.time() - _LAST_ACTIVITY > 600' in art,
    "remote version": 'VERSION = "0.10.0"' in remote,
    "remote render test": 'art_render_test' in remote,
    "remote worker status": 'art_worker_status' in remote,
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise SystemExit("Vex Art Worker v0.10.0 verification failed: " + ", ".join(failed))
print("Vex Art Worker v0.10.0 source checks OK")
