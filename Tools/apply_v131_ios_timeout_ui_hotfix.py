#!/usr/bin/env python3
from pathlib import Path
import runpy

CONTENT = Path("VexNative/ContentView.swift")
BRAIN = Path("VexNative/Views/BrainView.swift")
APP = Path("VexNative/VexNativeApp.swift")
MARKER = 'V131_TIMEOUT_UI_HOTFIX = "v0.13.1-timeout-ui-v1"'

app_before = APP.read_text(encoding="utf-8")
if "v0.9.4.4: cognition and local rendering" not in app_before:
    runpy.run_path("Tools/apply_v0944_bridge_long_request_timeout_patch.py", run_name="__main__")

text = CONTENT.read_text(encoding="utf-8")
if MARKER not in text:
    replacements = [
        ("            VexSystemView()\n                .tag(VexMainTab.system)",
         "            VexSystemView()\n                .dynamicTypeSize(.small ... .large)\n                .tag(VexMainTab.system)"),
        ("            VexArtStudioView(onOpenChat: { tab = .chat })\n                .tag(VexMainTab.art)",
         "            VexArtStudioView(onOpenChat: { tab = .chat })\n                .dynamicTypeSize(.small ... .large)\n                .tag(VexMainTab.art)"),
        ("            VexMemoryView()\n                .tag(VexMainTab.memory)",
         "            VexMemoryView()\n                .dynamicTypeSize(.small ... .large)\n                .tag(VexMainTab.memory)"),
        ("            VexPhoneView(onOpenChat: { tab = .chat })\n                .tag(VexMainTab.phone)",
         "            VexPhoneView(onOpenChat: { tab = .chat })\n                .dynamicTypeSize(.small ... .large)\n                .tag(VexMainTab.phone)"),
    ]
    for old, new in replacements:
        if old not in text:
            raise SystemExit("v0.13.1 control-surface tab anchor missing")
        text = text.replace(old, new, 1)
    text = text.replace(
        'private let V130_CONTROL_SURFACE = "v0.13.0-control-surface-v1"',
        'private let V130_CONTROL_SURFACE = "v0.13.0-control-surface-v1"\nprivate let V131_TIMEOUT_UI_HOTFIX = "v0.13.1-timeout-ui-v1"',
        1,
    )
    CONTENT.write_text(text, encoding="utf-8")

brain = BRAIN.read_text(encoding="utf-8")
brain_marker = "// V131_BRAIN_DYNAMIC_TYPE_CAP"
if brain_marker not in brain:
    anchor = '        // V128_RUNTIME_WANTS_AUTREFRESH = "v0.12.8-brain-open-refresh-v1"\n'
    if anchor not in brain:
        raise SystemExit("v0.13.1 BrainView modifier anchor missing")
    brain = brain.replace(
        anchor,
        '        .dynamicTypeSize(.small ... .large)\n'
        '        // V131_BRAIN_DYNAMIC_TYPE_CAP\n'
        + anchor,
        1,
    )
    BRAIN.write_text(brain, encoding="utf-8")

final_content = CONTENT.read_text(encoding="utf-8")
final_brain = BRAIN.read_text(encoding="utf-8")
final_app = APP.read_text(encoding="utf-8")

for marker in [
    MARKER,
    "VexSystemView()\n                .dynamicTypeSize(.small ... .large)",
    "VexArtStudioView(onOpenChat: { tab = .chat })\n                .dynamicTypeSize(.small ... .large)",
    "VexMemoryView()\n                .dynamicTypeSize(.small ... .large)",
    "VexPhoneView(onOpenChat: { tab = .chat })\n                .dynamicTypeSize(.small ... .large)",
]:
    if marker not in final_content:
        raise SystemExit(f"v0.13.1 UI invariant missing: {marker}")

if ".dynamicTypeSize(.small ... .large)" not in final_brain or brain_marker not in final_brain:
    raise SystemExit("v0.13.1 Brain dynamic type cap missing")

for marker in [
    'path == "/llm/chat"',
    "configuration.timeoutIntervalForRequest = 95",
    "configuration.timeoutIntervalForResource = 100",
    'path.hasPrefix("/art/")',
    "configuration.timeoutIntervalForRequest = 180",
    "configuration.timeoutIntervalForResource = 240",
]:
    if marker not in final_app:
        raise SystemExit(f"v0.13.1 transport invariant missing: {marker}")

print("PASS v0.13.1 iPhone timeout + UI hotfix")
