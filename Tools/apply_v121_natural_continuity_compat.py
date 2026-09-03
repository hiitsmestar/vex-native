#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "Tools" / "apply_v11729_ios_natural_continuity.py"
source = PATCH.read_text(encoding="utf-8")

old = '''fast_end = app.find("        if engine == nil {", fast_start)\nrequire(fast_end >= 0, "native grounded fast path end")\n'''
new = '''fast_end = app.find("        if engine == nil {", fast_start)\nif fast_end < 0:\n    # v0.9.4.1 startup-safe builds deliberately removed implicit model loading.\n    # End the old closed-world short circuit at that preserved startup-safe block.\n    fast_end = app.find("        // v0.9.4.1 startup-safe mode:", fast_start)\nrequire(fast_end >= 0, "native grounded fast path end")\n'''

if old not in source:
    raise SystemExit("natural-continuity compatibility anchor missing")
source = source.replace(old, new, 1)
PATCH.write_text(source, encoding="utf-8")
compile(source, str(PATCH), "exec")

result = subprocess.run([sys.executable, str(PATCH.relative_to(ROOT))], cwd=ROOT)
raise SystemExit(result.returncode)
