#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

PATH = Path("Bridge/vex_bridge.py")
text = PATH.read_text(encoding="utf-8")

if '"version": "0.11.7.38"' not in text:
    raise SystemExit("v0.11.7.39 expected Bridge v0.11.7.38 source")

choose_marker = "def _choose_ollama_model() -> str | None:\n"
choose_at = text.find(choose_marker)
if choose_at < 0:
    raise SystemExit("_choose_ollama_model marker missing")

helpers = ""
if "def _model_billions(name: str) -> float | None:" not in text:
    helpers += r'''
def _model_billions(name: str) -> float | None:
    low = str(name or "").lower()
    import re
    match = re.search(r"(?:^|[-_:])([0-9]+(?:\.[0-9]+)?)b(?:$|[-_:])", low)
    if not match:
        return None
    try:
        return float(match.group(1))
    except Exception:
        return None


'''

if "def _cognition_model_rank(name: str, max_billions: float) -> tuple:" not in text:
    helpers += r'''
def _cognition_model_rank(name: str, max_billions: float) -> tuple:
    low = str(name or "").lower()
    size = _model_billions(low)
    fits = size is None or size <= max_billions + 0.01
    family = 0
    if "qwen3" in low:
        family = 5
    elif "qwen" in low:
        family = 4
    elif "gemma" in low:
        family = 3
    elif "llama" in low:
        family = 2
    known = size is not None
    return (1 if fits else 0, family, 1 if known else 0, size or 0.0)


'''

if helpers:
    text = text[:choose_at] + helpers + text[choose_at:]

text = text.replace('"version": "0.11.7.38"', '"version": "0.11.7.39"', 1)
PATH.write_text(text, encoding="utf-8")
compile(text, str(PATH), "exec")

# Catch the exact class of field failures that slipped through .37/.38:
# helper calls compile fine even when the helper definition was removed.
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

# Verify every private helper called directly by the chooser exists.
chooser = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_choose_ollama_model")
called = {
    node.func.id
    for node in ast.walk(chooser)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id.startswith("_")
}
undefined = sorted(name for name in called if name not in defs)
if undefined:
    raise SystemExit("chooser references undefined helpers: " + ", ".join(undefined))

for marker in [
    '"version": "0.11.7.39"',
    "def _cognition_capacity() -> dict:",
    "def _model_billions(name: str) -> float | None:",
    "def _cognition_model_rank(name: str, max_billions: float) -> tuple:",
    "def _start_ollama_if_needed()",
]:
    if marker not in text:
        raise SystemExit(f"missing v0.11.7.39 marker: {marker}")

print("Applied v0.11.7.39 complete cognition helper bundle")
