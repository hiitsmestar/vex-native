#!/usr/bin/env python3
from pathlib import Path

path = Path("VexNative/ContentView.swift")
text = path.read_text(encoding="utf-8")

old = "        let deadline = Date().addingTimeInterval(450)\n"
new = "        let deadline = Date().addingTimeInterval(1200)\n"
if old not in text:
    if new not in text:
        raise SystemExit("PCArtRouter 450-second deadline marker missing")
else:
    text = text.replace(old, new, 1)

# Keep explicit natural image requests from requiring the exact verbs generate/create.
old_guard = '''        return createWords.contains(where: { lower.contains($0) }) &&\n            imageWords.contains(where: { lower.contains($0) })\n'''
new_guard = '''        let directVisualRequests = [\n            "show me a picture", "show me a pic", "show me a photo", "show me an image",\n            "send me a picture", "send me a pic", "send me a photo", "send me an image"\n        ]\n        if directVisualRequests.contains(where: { lower.contains($0) }) { return true }\n        return createWords.contains(where: { lower.contains($0) }) &&\n            imageWords.contains(where: { lower.contains($0) })\n'''
if old_guard in text:
    text = text.replace(old_guard, new_guard, 1)
elif "directVisualRequests" not in text:
    raise SystemExit("PCArtRouter intent guard marker missing")

for marker in ["Date().addingTimeInterval(1200)", "directVisualRequests", 'path: "/art/generate"', 'path: "/art/status"', 'path: "/art/result"']:
    if marker not in text:
        raise SystemExit(f"v0.10.7 iOS art adapter marker missing: {marker}")
path.write_text(text, encoding="utf-8")
print("Applied v0.10.7 iPhone standalone Art Worker timeout/routing patch")
