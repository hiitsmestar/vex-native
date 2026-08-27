#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

PATH = Path("Bridge/vex_bridge.py")
text = PATH.read_text(encoding="utf-8")

if '"version": "0.11.7.39"' not in text:
    raise SystemExit("v0.11.7.40 expected Bridge v0.11.7.39 source")

# Normalize every runtime-facing Bridge version marker. Earlier field builds
# bumped only one literal, so the dedicated local-control status handler could
# still advertise .37 even when a newer Bridge was actually running.
for old in ("0.11.7.37", "0.11.7.38", "0.11.7.39"):
    text = text.replace(f'"version": "{old}"', '"version": "0.11.7.40"')

PATH.write_text(text, encoding="utf-8")
compile(text, str(PATH), "exec")

tree = ast.parse(text)
defs = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
required = {
    "_ollama_models",
    "_start_ollama_if_needed",
    "_cognition_capacity",
    "_model_billions",
    "_cognition_model_rank",
    "_choose_ollama_model",
}
missing = sorted(required - defs)
if missing:
    raise SystemExit("missing cognition helper definitions: " + ", ".join(missing))

chooser = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_choose_ollama_model")
called = {
    node.func.id
    for node in ast.walk(chooser)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id.startswith("_")
}
undefined = sorted(name for name in called if name not in defs)
if undefined:
    raise SystemExit("chooser references undefined helpers: " + ", ".join(undefined))

if '"version": "0.11.7.40"' not in text:
    raise SystemExit("v0.11.7.40 runtime version marker missing")

print("Applied v0.11.7.40 cognition live-smoke + version normalization fix")
