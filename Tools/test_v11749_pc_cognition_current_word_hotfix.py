#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
content = (ROOT / "VexNative" / "ContentView.swift").read_text(encoding="utf-8")
start = content.find("    private static func shouldUse(_ text: String) -> Bool {")
end = content.find("    private static func configuredEndpoints()", start)
if start < 0 or end < 0:
    raise SystemExit("v0.11.7.49 test could not locate shouldUse()")
block = content[start:end]

# Parse the literal substring exclusions used by shouldUse().
strings = re.findall(r'\"([^\"]+)\"', block)

def would_decline_pc_cognition(text: str) -> bool:
    lower = text.lower()
    return any(value.lower() in lower for value in strings)

nyx = "Correction: my imaginary fox is named Nyx, not Mica. Replace the old fact and remember Nyx as the current name."
checks = [
    ("Nyx correction reaches PC cognition", not would_decline_pc_cognition(nyx)),
    ("ordinary current outfit reaches PC cognition", not would_decline_pc_cognition("My current outfit is black.")),
    ("ordinary current plan reaches PC cognition", not would_decline_pc_cognition("What is our current plan for the memory test?")),
    ("current weather stays specialized", would_decline_pc_cognition("What is the current weather?")),
    ("current news stays specialized", would_decline_pc_cognition("What is the current news?")),
    ("latest stays specialized", would_decline_pc_cognition("What is the latest update?")),
]

for name, ok in checks:
    print(("PASS " if ok else "FAIL ") + name)
missing = [name for name, ok in checks if not ok]
if missing:
    raise SystemExit("v0.11.7.49 current-word routing regression failed: " + ", ".join(missing))

print("v0.11.7.49 PC cognition current-word routing verified")
