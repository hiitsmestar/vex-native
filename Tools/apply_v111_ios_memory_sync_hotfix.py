#!/usr/bin/env python3
from pathlib import Path

path = Path("VexNative/ContentView.swift")
text = path.read_text(encoding="utf-8")

replacements = {
    "            await syncPersonalMemory(endpoint: primary, app: app)\n": "            Task { await syncPersonalMemory(endpoint: primary, app: app) }\n",
    "                await syncPersonalMemory(endpoint: fallback, app: app)\n": "                Task { await syncPersonalMemory(endpoint: fallback, app: app) }\n",
}
for old, new in replacements.items():
    if old in text:
        text = text.replace(old, new, 1)
    elif new not in text:
        raise SystemExit(f"missing iOS memory sync anchor: {old.strip()}")

# Keep the archive backfill in the background, but yield briefly before it starts
# so the user's cognition request gets first use of Bridge/CPU resources.
old_func = '''    private static func syncPersonalMemory(endpoint: String, app: AppModel) async {
        let key = memoryEndpointKey(endpoint)
'''
new_func = '''    private static func syncPersonalMemory(endpoint: String, app: AppModel) async {
        try? await Task.sleep(nanoseconds: 750_000_000)
        let key = memoryEndpointKey(endpoint)
'''
if old_func in text:
    text = text.replace(old_func, new_func, 1)
elif "750_000_000" not in text:
    raise SystemExit("memory sync function anchor missing")

path.write_text(text, encoding="utf-8")
for marker in [
    "Task { await syncPersonalMemory(endpoint: primary, app: app) }",
    "Task { await syncPersonalMemory(endpoint: fallback, app: app) }",
    "750_000_000",
]:
    if marker not in text:
        raise SystemExit(f"missing v0.11.1 iOS marker: {marker}")
print("Applied v0.11.1 non-blocking iPhone personal-memory sync hotfix")
