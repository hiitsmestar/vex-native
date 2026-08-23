#!/usr/bin/env python3
from pathlib import Path
import json

bridge = Path("Bridge/vex_bridge.py").read_text(encoding="utf-8")
full = Path("Bridge/vex_bridge_full.py").read_text(encoding="utf-8")
art = Path("Tools/VexArtWorker.py").read_text(encoding="utf-8")
manifest = json.loads(Path("Tools/VexToolManifest.json").read_text(encoding="utf-8"))

# v0.10.9 keeps the proven v0.10.8 standalone Art Worker adapter contract and
# layers adaptive PC cognition on top. Verify capabilities, not one frozen bundle
# number, so future cognition-only releases cannot accidentally weaken art checks.
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
        raise SystemExit(f"Bridge adapter verifier missing: {marker}")

for marker in [
    '--result-file',
    'target.write_text(json.dumps(result',
    'smart_prompt=not args.raw_prompt',
    'OMP_NUM_THREADS',
    'MKL_NUM_THREADS',
    'BELOW_NORMAL_PRIORITY_CLASS',
]:
    if marker not in art:
        raise SystemExit(f"Art Worker adapter verifier missing: {marker}")

valid_versions = {'0.10.8', '0.10.9'}
if not any(f'VERSION = "{version}"' in art for version in valid_versions):
    raise SystemExit("Art Worker version is not an approved v0.10.8+ adapter release")
if not any(f'VERSION = "{version}"' in full for version in valid_versions):
    raise SystemExit("Bridge launcher version is not an approved v0.10.8+ adapter release")
if str(manifest.get("version") or "") not in valid_versions:
    raise SystemExit("tool manifest is not an approved v0.10.8+ adapter release")

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

for route in ['/art/generate', '/art/status', '/art/result']:
    if route not in bridge:
        raise SystemExit(f"legacy iPhone art route missing: {route}")

print("VexBridge v0.10.8+ standalone Art Worker adapter contract checks OK")
