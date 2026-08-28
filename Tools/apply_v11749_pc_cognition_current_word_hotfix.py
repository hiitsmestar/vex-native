#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


CONTENT = Path("VexNative/ContentView.swift")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"v0.11.7.49 missing anchor: {label}")
    return text.replace(old, new, 1)


content = CONTENT.read_text(encoding="utf-8")

# v0.11.7.48 used the bare substring "current " as a PC-cognition exclusion.
# That incorrectly rejected ordinary personal conversation such as "current name",
# "current outfit", or "current plan" before any paired Bridge endpoint was tried.
# Specialized native routes already have specific intent markers (weather/news/etc.),
# so remove only the over-broad generic word while preserving those routes.
content = replace_once(
    content,
    '            "search the web", "search online", "look up ", "latest", "current ", "today",\n',
    '            "search the web", "search online", "look up ", "latest", "today",\n',
    "blanket current-word PC cognition exclusion",
)

CONTENT.write_text(content, encoding="utf-8")

# Build-time markers. The behavioral regression test separately parses the generated
# shouldUse() exclusion list and evaluates representative phrases.
should_use_start = content.find("    private static func shouldUse(_ text: String) -> Bool {")
configured_start = content.find("    private static func configuredEndpoints()", should_use_start)
if should_use_start < 0 or configured_start < 0:
    raise SystemExit("v0.11.7.49 verifier could not locate PC cognition shouldUse()")
block = content[should_use_start:configured_start]
checks = [
    ("blanket current exclusion removed", '"current "' not in block),
    ("weather route preserved", '"weather"' in block),
    ("news route preserved", '"news"' in block),
    ("latest route preserved", '"latest"' in block),
]
missing = [name for name, ok in checks if not ok]
if missing:
    raise SystemExit("v0.11.7.49 verifier failed: " + ", ".join(missing))

print("Applied VexNative v0.11.7.49 PC cognition current-word routing hotfix")
