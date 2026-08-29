#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

path = Path("Tools/VexRemoteSupport.py")
text = path.read_text(encoding="utf-8")
compile(text, str(path), "exec")

required = [
    'VERSION = "0.11.7.58"',
    'total = integer(issue.get("comments"))',
    'last_page = max(1, (total + 99) // 100)',
    'pages = sorted({max(1, last_page - 1), last_page})',
    'comments?per_page=100&page={page}',
    'comments.sort(key=lambda item: integer(item.get("id")))',
]
for marker in required:
    if marker not in text:
        raise SystemExit(f"missing v0.11.7.58 relay regression marker: {marker}")

if 'def fetch_comments() -> list[dict]:\n    data = gh_api([f"repos/{REPO}/issues/{ISSUE_NUMBER}/comments?per_page=100"]' in text:
    raise SystemExit("first-page-only relay poll still present")

# Structural sanity: exactly one active fetch_comments function.
tree = ast.parse(text)
fetch_defs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "fetch_comments"]
if len(fetch_defs) != 1:
    raise SystemExit(f"expected one fetch_comments definition, got {len(fetch_defs)}")

print("v0.11.7.58 Remote Support relay-tail regression PASS")
