#!/usr/bin/env python3
import importlib.util
from pathlib import Path

path = Path("Tools/VexArtWorker.py")
text = path.read_text(encoding="utf-8")
checks = [
    'VERSION = "0.10.6"',
    'def _smart_prompt',
    'Smart Prompt',
    'Preview Smart Prompt',
    'wrong clothing colors',
    'prompt_mode',
    '--raw-prompt',
]
for check in checks:
    if check not in text:
        raise SystemExit(f"missing v0.10.6 marker: {check}")

spec = importlib.util.spec_from_file_location("vex_art_worker_verify", path)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)

human, negative = module._smart_prompt(
    "full body very skinny pale alternative woman, black hair with pink streaks, dark eyeliner, tiny bright pink crop top, black side-string thong, black platform sandals, plain pink studio background"
)
for wanted in (
    "full body",
    "both feet visible",
    "very slim body",
    "long straight black hair with clearly visible hot pink streaks",
    "tiny bright pink crop top",
    "black side-string thong",
    "black platform sandals",
    "solid plain pink seamless backdrop",
):
    if wanted not in human:
        raise SystemExit(f"human Smart Prompt missing: {wanted}\n{human}")

if "wrong clothing colors" not in negative:
    raise SystemExit("Smart negative prompt missing color-binding protection")

obj, _ = module._smart_prompt("red ceramic mug on a wooden table")
if "adult woman" in obj or "human proportions" in obj:
    raise SystemExit(f"generic object prompt was incorrectly humanized: {obj}")
if "red ceramic mug" not in obj:
    raise SystemExit("generic object prompt lost user intent")

print("v0.10.6 Smart Prompt verification OK")
