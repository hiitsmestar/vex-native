#!/usr/bin/env python3
from pathlib import Path

path = Path("VexNative/VexNativeApp.swift")
text = path.read_text(encoding="utf-8")

old = '''        let configuration = URLSessionConfiguration.ephemeral\n        configuration.timeoutIntervalForRequest = 18\n        configuration.timeoutIntervalForResource = 24\n        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData\n        configuration.protocolClasses = []\n'''
new = '''        let configuration = URLSessionConfiguration.ephemeral\n        // v0.9.4.4: cognition and local rendering are intentionally long-running\n        // on CPU-only PCs. The old transport-level 18/24 second limits silently\n        // overrode the 90 second URLRequest timeout used by PCCognitionOverlay,\n        // causing VexNative to abandon a healthy PC before Ollama returned.\n        let path = bridgeRequest.url?.path.lowercased() ?? ""\n        if path == "/llm/chat" {\n            configuration.timeoutIntervalForRequest = 95\n            configuration.timeoutIntervalForResource = 100\n        } else if path.hasPrefix("/art/") {\n            configuration.timeoutIntervalForRequest = 180\n            configuration.timeoutIntervalForResource = 240\n        } else {\n            configuration.timeoutIntervalForRequest = 18\n            configuration.timeoutIntervalForResource = 24\n        }\n        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData\n        configuration.protocolClasses = []\n'''

if old not in text:
    raise SystemExit("VexBridgeNetworking timeout block not found")
text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")

for marker in [
    "v0.9.4.4: cognition and local rendering",
    'path == "/llm/chat"',
    "configuration.timeoutIntervalForResource = 100",
    'path.hasPrefix("/art/")',
]:
    if marker not in text:
        raise SystemExit(f"missing v0.9.4.4 marker: {marker}")

print("Applied v0.9.4.4 long-running Bridge request timeout fix")
