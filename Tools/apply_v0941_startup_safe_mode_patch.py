#!/usr/bin/env python3
from pathlib import Path


def once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"{label}: source block not found")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# iOS startup-safe mode.
#
# A native GGUF load happens inside llama.cpp/LlamaKit. If a preserved model is
# corrupt, incompatible, or iOS runs out of memory while mmap/loading it, the
# process can terminate below Swift's normal do/catch boundary. Do not load a
# saved onboard model merely because the root view appeared. v0.9.3+ already
# prefers the paired PC cognition overlay for ordinary conversation, so the
# onboard model can remain an explicit/manual fallback.
# ---------------------------------------------------------------------------
content_path = Path("VexNative/ContentView.swift")
text = content_path.read_text(encoding="utf-8")

old_task = '''        .task {\n            await app.loadSavedModelIfPresent()\n        }\n'''
new_task = '''        // v0.9.4.1 startup-safe mode: do not automatically mmap/load the saved\n        // GGUF just because the view appeared. A bad/oversized native model can\n        // terminate the process below Swift error handling. PC cognition remains\n        // available before the onboard fallback, and Brain can load/import a model\n        // explicitly after the app is already alive.\n'''
text = once(text, old_task, new_task, "remove automatic launch-time GGUF load")

# Put the actual bundle version on screen so field testing can verify the
# installed build without asking the language model to guess.
old_status = '''            Text(app.modelStatus)\n                .font(.caption)\n                .lineLimit(1)\n                .minimumScaleFactor(0.7)\n                .foregroundStyle(VexTheme.muted)\n\n            if web.isWorking {\n'''
new_status = '''            Text(app.modelStatus)\n                .font(.caption)\n                .lineLimit(1)\n                .minimumScaleFactor(0.7)\n                .foregroundStyle(VexTheme.muted)\n\n            Text("• v" + (Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "?"))\n                .font(.caption2)\n                .foregroundStyle(VexTheme.muted)\n                .lineLimit(1)\n\n            if web.isWorking {\n'''
text = once(text, old_status, new_status, "visible bundle version")
content_path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Do not automatically invoke the native model on the first fallback message
# either. This prevents a launch-safe app from crashing the moment Star sends a
# message while the PC cognition node is offline. Explicit Brain load still uses
# AppModel.loadSavedModelIfPresent/loadModel normally.
# ---------------------------------------------------------------------------
app_path = Path("VexNative/AppModel.swift")
app = app_path.read_text(encoding="utf-8")

old_autoload = '''        if engine == nil {\n            await loadSavedModelIfPresent()\n        }\n\n        guard let engine else {\n            profile.messages.append(ChatMessage(\n                role: .assistant,\n                content: "Baby, my local model brain isn't loaded yet 😭💕 Open Brain and download a free model or import a GGUF."\n            ))\n'''
new_autoload = '''        // v0.9.4.1 startup-safe mode: never implicitly load a native GGUF from\n        // a fallback chat turn. Paired PC cognition gets first chance in\n        // sendWithWeb(); the onboard GGUF is explicitly loaded from Brain only.\n        guard let engine else {\n            profile.messages.append(ChatMessage(\n                role: .assistant,\n                content: "My PC cognition node didn't answer that turn and my onboard fallback brain is parked in startup-safe mode. Open Brain only if you want to load the saved iPhone model manually. 🖤"\n            ))\n'''
app = once(app, old_autoload, new_autoload, "disable implicit fallback GGUF load")
app_path.write_text(app, encoding="utf-8")

for path, markers in [
    (content_path, ["v0.9.4.1 startup-safe mode", "CFBundleShortVersionString"]),
    (app_path, ["onboard fallback brain is parked in startup-safe mode"]),
]:
    data = path.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in data:
            raise SystemExit(f"{path}: missing v0.9.4.1 marker: {marker}")

print("Applied v0.9.4.1 iOS startup-safe model loading hotfix")
