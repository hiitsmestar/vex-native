#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "Tools" / "apply_v11729_ios_natural_continuity.py"
source = PATCH.read_text(encoding="utf-8")

replacements = []

replacements.append((
'''fast_end = app.find("        if engine == nil {", fast_start)\nrequire(fast_end >= 0, "native grounded fast path end")\n''',
'''fast_end = app.find("        if engine == nil {", fast_start)\nif fast_end < 0:\n    # v0.9.4.1 startup-safe builds deliberately removed implicit model loading.\n    # End the old closed-world short circuit at that preserved startup-safe block.\n    fast_end = app.find("        // v0.9.4.1 startup-safe mode:", fast_start)\nrequire(fast_end >= 0, "native grounded fast path end")\n''',
"startup-safe fast-path end",
))

replacements.append((
'''main_pattern = re.compile(r"(newestUserText:\\s*(?:modelText|text),\\n\\s*isQwen3:\\s*isQwen3)(\\n\\s*\\))")\napp, count = main_pattern.subn(r"\\1,\\n            groundedDirective: groundedDirective\\2", app, count=1)\nrequire(count == 1, "first PromptComposer call")\n\nretry_pattern = re.compile(r"(newestUserText:\\s*(?:modelText|text),\\n\\s*isQwen3:\\s*true,\\n\\s*retryMode:\\s*true)(\\n\\s*\\))")\napp, count = retry_pattern.subn(r"\\1,\\n                    groundedDirective: groundedDirective\\2", app, count=1)\nrequire(count == 1, "retry PromptComposer call")\n''',
'''main_pattern = re.compile(r"(newestUserText:\\s*(?:modelText|text),\\n\\s*isQwen3:\\s*isQwen3,)(\\n\\s*pcBrainContext:\\s*pcBrainContext)(\\n\\s*\\))")\napp, count = main_pattern.subn(r"\\1\\2,\\n            groundedDirective: groundedDirective\\3", app, count=1)\nrequire(count == 1, "first PromptComposer call")\n\nretry_pattern = re.compile(r"(newestUserText:\\s*(?:modelText|text),\\n\\s*isQwen3:\\s*true,\\n\\s*retryMode:\\s*true,)(\\n\\s*pcBrainContext:\\s*pcBrainContext)(\\n\\s*\\))")\napp, count = retry_pattern.subn(r"\\1\\2,\\n                    groundedDirective: groundedDirective\\3", app, count=1)\nrequire(count == 1, "retry PromptComposer call")\n''',
"PC-context PromptComposer calls",
))

replacements.append((
'''sig_pattern = re.compile(r"retryMode:\\s*Bool\\s*=\\s*false(\\s*\\n\\s*)\\)\\s*->\\s*String\\s*\\{")\nprompt, n = sig_pattern.subn(\n    r"retryMode: Bool = false,\\1groundedDirective: String? = nil\\1) -> String {",\n    prompt,\n    count=1,\n)\nrequire(n == 1, "PromptComposer groundedDirective parameter")\n''',
'''sig_pattern = re.compile(r"(pcBrainContext:\\s*String\\?\\s*=\\s*nil)(\\s*\\n\\s*)\\)\\s*->\\s*String\\s*\\{")\nprompt, n = sig_pattern.subn(\n    r"\\1,\\2groundedDirective: String? = nil\\2) -> String {",\n    prompt,\n    count=1,\n)\nrequire(n == 1, "PromptComposer groundedDirective parameter")\n''',
"PC-context PromptComposer signature",
))

for old, new, label in replacements:
    if old not in source:
        raise SystemExit(f"natural-continuity compatibility anchor missing: {label}")
    source = source.replace(old, new, 1)

PATCH.write_text(source, encoding="utf-8")
compile(source, str(PATCH), "exec")

result = subprocess.run([sys.executable, str(PATCH.relative_to(ROOT))], cwd=ROOT)
raise SystemExit(result.returncode)
