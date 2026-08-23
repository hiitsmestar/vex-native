#!/usr/bin/env python3
from pathlib import Path
import json

bridge = Path("Bridge/vex_bridge.py").read_text(encoding="utf-8")
full = Path("Bridge/vex_bridge_full.py").read_text(encoding="utf-8")
art = Path("Tools/VexArtWorker.py").read_text(encoding="utf-8")
manifest = json.loads(Path("Tools/VexToolManifest.json").read_text(encoding="utf-8"))

# v0.10.8 keeps the v0.10.7 standalone Art Worker adapter contract, then layers
# PC cognition grounding and render-priority fixes on top. Verify capabilities
# instead of rejecting the build merely because bundle versions advanced.
for marker in [
    "def _art_worker_exe",
    "VexArtWorker.exe",
    "--result-file",
    "VexArtAdapter-",
    "bridge_role\": \"broker-only",
    "def _adapter_release_cognition_memory",
    "_ART_COGNITION_WAS_RELEASED = True",
    "PC COGNITION GROUNDING",
    "_ollama_chat(history, message, context)",
    "BELOW_NORMAL_PRIORITY_CLASS",
]:
    if marker not in bridge:
        raise SystemExit(f"Bridge v0.10.8 verifier missing: {marker}")

for marker in [
    'VERSION = "0.10.8"',
    '--result-file',
    'target.write_text(json.dumps(result',
    'smart_prompt=not args.raw_prompt',
    'OMP_NUM_THREADS',
    'MKL_NUM_THREADS',
    'BELOW_NORMAL_PRIORITY_CLASS',
]:
    if marker not in art:
        raise SystemExit(f"Art Worker v0.10.8 verifier missing: {marker}")

if 'VERSION = "0.10.8"' not in full:
    raise SystemExit("Bridge launcher is not v0.10.8")

if manifest.get("version") != "0.10.8":
    raise SystemExit("tool manifest is not v0.10.8")

art_entry = next((x for x in manifest.get("tools", []) if x.get("id") == "art"), None)
if not art_entry:
    raise SystemExit("art tool missing from manifest")
if art_entry.get("adapter") != "complete" or art_entry.get("bridge_role") != "broker-only":
    raise SystemExit("art manifest adapter state is not complete/broker-only")
if art_entry.get("followup_view_routing") is not True:
    raise SystemExit("art manifest missing follow-up view routing flag")
if art_entry.get("resource_priority") != "below-normal-on-cpu":
    raise SystemExit("art manifest missing v0.10.8 resource priority")
if any("VexArtWorker adapter" in str(x) for x in manifest.get("planned_extractions", [])):
    raise SystemExit("Art Worker adapter still listed as planned")

# The iPhone contract remains stable across the extraction.
for route in ['/art/generate', '/art/status', '/art/result']:
    if route not in bridge:
        raise SystemExit(f"legacy iPhone art route missing: {route}")

print("VexBridge v0.10.8 standalone Art Worker + cognition stability checks OK")
