#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

PATH = Path("Bridge/vex_bridge.py")
text = PATH.read_text(encoding="utf-8")

chooser_marker = "def _choose_ollama_model() -> str | None:\n"
chooser_at = text.find(chooser_marker)
if chooser_at < 0:
    raise SystemExit("v0.12 cognition integrity: _choose_ollama_model marker missing")

# Field validation proved the cumulative source generator can preserve calls from
# the chooser while dropping helper definitions after the older .39 verifier ran.
# Restore the complete dependency-free chooser helper set at the final v0.12 stage.
helpers = ""

if "def _cognition_capacity() -> dict:" not in text:
    helpers += r'''
def _cognition_capacity() -> dict:
    total = 0
    available = 0
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            total = int(stat.ullTotalPhys)
            available = int(stat.ullAvailPhys)
    except Exception:
        pass

    cpu = max(1, int(os.cpu_count() or 1))
    total_gb = total / (1024 ** 3) if total else 0.0
    available_gb = available / (1024 ** 3) if available else 0.0

    if total_gb >= 20.0 and cpu >= 8:
        tier, max_billions = "strong", 8.0
    elif total_gb >= 9.0:
        tier, max_billions = "balanced", 4.0
    else:
        tier, max_billions = "lite", 2.0

    pressure = "normal"
    if available_gb and available_gb < 3.0:
        pressure = "memory"
        max_billions = min(max_billions, 2.0)
    elif available_gb and available_gb < 6.0:
        max_billions = min(max_billions, 4.0)

    return {
        "tier": tier,
        "pressure": pressure,
        "max_billions": max_billions,
        "memory_total_gb": round(total_gb, 1),
        "memory_available_gb": round(available_gb, 1),
        "cpu_logical": cpu,
        "gpu_name": None,
        "gpu_vram_gb": 0.0,
        "gpu_source": None,
        "art_running": False,
    }


'''

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
    text = text[:chooser_at] + helpers + text[chooser_at:]

PATH.write_text(text, encoding="utf-8")
compile(text, str(PATH), "exec")

tree = ast.parse(text)
defs = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
required = {
    "_cognition_capacity",
    "_model_billions",
    "_cognition_model_rank",
    "_choose_ollama_model",
    "_ollama_models",
    "_start_ollama_if_needed",
}
missing = sorted(required - defs)
if missing:
    raise SystemExit("v0.12 cognition integrity missing helper definitions: " + ", ".join(missing))

# Check every direct private helper call made by the chooser so another dangling
# NameError cannot pass CI just because field testing has not happened to hit it yet.
chooser = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_choose_ollama_model")
called = {
    node.func.id
    for node in ast.walk(chooser)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id.startswith("_")
}
undefined = sorted(name for name in called if name not in defs)
if undefined:
    raise SystemExit("v0.12 chooser references undefined helpers: " + ", ".join(undefined))

for helper_name in (
    "def _cognition_capacity() -> dict:",
    "def _model_billions(name: str) -> float | None:",
    "def _cognition_model_rank(name: str, max_billions: float) -> tuple:",
):
    if text.find(helper_name) > text.find(chooser_marker):
        raise SystemExit(f"v0.12 cognition helper must precede chooser: {helper_name}")

print("Verified/restored complete final v0.12 cognition chooser helper integrity")
