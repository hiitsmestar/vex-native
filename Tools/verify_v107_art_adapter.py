#!/usr/bin/env python3
from pathlib import Path
import json

bridge = Path("Bridge/vex_bridge.py").read_text(encoding="utf-8")
full = Path("Bridge/vex_bridge_full.py").read_text(encoding="utf-8")
art = Path("Tools/VexArtWorker.py").read_text(encoding="utf-8")
manifest = json.loads(Path("Tools/VexToolManifest.json").read_text(encoding="utf-8"))

for marker in [
    "def _art_worker_exe",
    "VexArtWorker.exe",
    "--result-file",
    "VexArtAdapter-",
    "bridge_role\": \"broker-only",
    "def _adapter_release_cognition_memory",
    "_ART_COGNITION_WAS_RELEASED = True",
    '"version": "0.10.7"',
]:
    if marker not in bridge:
        raise SystemExit(f"Bridge adapter verifier missing: {marker}")

for marker in [
    'VERSION = "0.10.7"',
    '--result-file',
    'target.write_text(json.dumps(result',
    'smart_prompt=not args.raw_prompt',
]:
    if marker not in art:
        raise SystemExit(f"Art Worker adapter verifier missing: {marker}")

if 'VERSION = "0.10.7"' not in full:
    raise SystemExit("Bridge launcher is not v0.10.7")

art_entry = next((x for x in manifest.get("tools", []) if x.get("id") == "art"), None)
if not art_entry:
    raise SystemExit("art tool missing from manifest")
if art_entry.get("adapter") != "complete" or art_entry.get("bridge_role") != "broker-only":
    raise SystemExit("art manifest adapter state is not complete/broker-only")
if any("VexArtWorker adapter" in str(x) for x in manifest.get("planned_extractions", [])):
    raise SystemExit("Art Worker adapter still listed as planned")

# The legacy API contract is intentionally preserved for the current iPhone app.
for route in ['/art/generate', '/art/status', '/art/result']:
    if route not in bridge:
        raise SystemExit(f"legacy iPhone art route missing: {route}")

print("VexBridge v0.10.7 standalone Art Worker adapter checks OK")
