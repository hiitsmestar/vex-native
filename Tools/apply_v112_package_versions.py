#!/usr/bin/env python3
from pathlib import Path
import json
import re

VERSION = "0.11.2"

for filename in ["Bridge/vex_bridge_full.py", "Tools/VexRemoteSupport.py", "Tools/VexMemoryWorker.py"]:
    path = Path(filename)
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(r'(?m)^VERSION\s*=\s*"[^"]+"', f'VERSION = "{VERSION}"', text, count=1)
    if count != 1:
        raise SystemExit(f"could not set VERSION in {filename}")
    path.write_text(updated, encoding="utf-8")

manifest_path = Path("Tools/VexToolManifest.json")
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest["version"] = VERSION
for tool in manifest.get("tools", []):
    if tool.get("id") == "memory":
        tool["name"] = "Vex Personal Memory"
        caps = list(tool.get("capabilities") or [])
        for cap in ["verified-personal-recall", "latency-aware-retrieval"]:
            if cap not in caps:
                caps.append(cap)
        tool["capabilities"] = caps
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print("Applied VexNative v0.11.2 package versions")
