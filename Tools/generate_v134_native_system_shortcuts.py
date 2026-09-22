#!/usr/bin/env python3
from __future__ import annotations

import plistlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "Artifacts" / "VexNativeShortcuts"
OUT.mkdir(parents=True, exist_ok=True)

def make_shortcut(filename: str, name: str, setting: str) -> None:
    payload = {
        "WFWorkflowClientVersion": "2607.0.3",
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowIcon": {
            "WFWorkflowIconGlyphNumber": 59641,
            "WFWorkflowIconStartColor": 3980825855,
        },
        "WFWorkflowImportQuestions": [],
        "WFWorkflowInputContentItemClasses": [],
        "WFWorkflowOutputContentItemClasses": [],
        "WFWorkflowTypes": [],
        "WFQuickActionSurfaces": [],
        "WFWorkflowHasOutputFallback": False,
        "WFWorkflowHasShortcutInputVariables": False,
        "WFWorkflowName": name,
        "WFWorkflowActions": [
            {
                "WFWorkflowActionIdentifier": "is.workflow.actions.flashlight",
                "WFWorkflowActionParameters": {
                    "WFFlashlightSetting": setting,
                },
            }
        ],
    }
    path = OUT / filename
    with path.open("wb") as f:
        plistlib.dump(payload, f, fmt=plistlib.FMT_XML, sort_keys=False)
    print(path)

make_shortcut(
    "Hey Vex turn on the flashlight.shortcut",
    "Hey Vex turn on the flashlight",
    "On",
)
make_shortcut(
    "Hey Vex turn off the flashlight.shortcut",
    "Hey Vex turn off the flashlight",
    "Off",
)
