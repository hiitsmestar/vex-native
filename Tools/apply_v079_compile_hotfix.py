#!/usr/bin/env python3
from pathlib import Path

path = Path("VexNative/ContentView.swift")
text = path.read_text(encoding="utf-8")

old = "            context.fill(rect)\n"
new = "            context.cgContext.fill(rect)\n"
if old not in text:
    raise SystemExit("v0.7.9 hotfix: renderer fill marker missing")
text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
print("Applied v0.7.9 compile hotfix")
