#!/usr/bin/env python3
from pathlib import Path
import json
import re

VERSION = "0.11.0"

# The build chain mutates these source files through many historical adapters.
# This last patch owns the package-visible version after all earlier mutations.
for filename in ["Bridge/vex_bridge_full.py", "Tools/VexRemoteSupport.py"]:
    path = Path(filename)
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(r'(?m)^VERSION\s*=\s*"[^"]+"', f'VERSION = "{VERSION}"', text, count=1)
    if count != 1:
        raise SystemExit(f"could not set VERSION in {filename}")
    path.write_text(updated, encoding="utf-8")

manifest_path = Path("Tools/VexToolManifest.json")
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest["version"] = VERSION
manifest["philosophy"] = (
    "Vex keeps cognition and routing lightweight. Durable personal memory lives in a separate local worker; "
    "heavy or specialized capabilities remain independent on-demand tools so one failure cannot take down Vex."
)
tools = [tool for tool in manifest.get("tools", []) if tool.get("id") != "memory"]
tools.append({
    "id": "memory",
    "name": "Vex Personal Memory",
    "executable": "VexMemoryWorker.exe",
    "mode": "local-persistent-service",
    "capabilities": [
        "long-term-memory",
        "chat-history",
        "persona-continuity",
        "relationship-continuity",
        "provenance",
        "retrieval"
    ],
    "always_running": False,
    "auto_start_on_use": True,
    "data_root": "%LOCALAPPDATA%\\VexNative\\Memory"
})
manifest["tools"] = tools
manifest["planned_extractions"] = [
    value for value in manifest.get("planned_extractions", [])
    if str(value).lower() not in {"vexmemory", "vex memory", "personal memory worker"}
]
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

print("Applied VexNative v0.11.0 package versions and personal-memory manifest")
