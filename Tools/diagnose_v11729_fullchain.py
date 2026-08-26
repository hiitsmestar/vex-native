#!/usr/bin/env python3
from pathlib import Path
import re
import sys

app = Path("VexNative/AppModel.swift").read_text(encoding="utf-8")
prompt = Path("VexNative/Core/PromptComposer.swift").read_text(encoding="utf-8")
mode = sys.argv[1] if len(sys.argv) > 1 else "all"

checks = {
    "engine_end": lambda: "        if engine == nil {" in app,
    "fn_end": lambda: "    private func normalizedIntentText(_ text: String) -> String {" in app,
    "main_regex": lambda: re.search(r"newestUserText:\s*(?:modelText|text),\n\s*isQwen3:\s*isQwen3\n\s*\)", app) is not None,
    "retry_regex": lambda: re.search(r"newestUserText:\s*(?:modelText|text),\n\s*isQwen3:\s*true,\n\s*retryMode:\s*true\n\s*\)", app) is not None,
    "sampling_temp": lambda: re.search(r"webGroundedTurn\s*\?\s*([0-9.]+)\s*:\s*0\.80", app) is not None,
    "sampling_topp": lambda: re.search(r"webGroundedTurn\s*\?\s*([0-9.]+)\s*:\s*0\.90", app) is not None,
    "sampling_topk": lambda: re.search(r"webGroundedTurn\s*\?\s*(\d+)\s*:\s*40", app) is not None,
    "signature": lambda: re.search(r"retryMode:\s*Bool\s*=\s*false(\s*\n\s*)\)\s*->\s*String\s*\{", prompt) is not None,
    "memory_end": lambda: re.search(r"^\s*let memoryBlock: String\s*$", prompt, flags=re.M) is not None,
    "system_boundary": lambda: "        let system: String" in prompt,
    "closed_exact": lambda: "            \\(closedWorld)" in prompt,
    "compact_regex": lambda: re.search(r"compact\s*=\s*String\(modelUserText\.prefix\(cap\)\)", prompt) is not None,
}

if mode == "all":
    failed = []
    for name, check in checks.items():
        ok = bool(check())
        print(f"{name}: {'PASS' if ok else 'FAIL'}")
        if not ok:
            failed.append(name)
    raise SystemExit(1 if failed else 0)

if mode not in checks:
    raise SystemExit(f"unknown diagnostic: {mode}")

ok = bool(checks[mode]())
print(f"{mode}: {'PASS' if ok else 'FAIL'}")
raise SystemExit(0 if ok else 1)
