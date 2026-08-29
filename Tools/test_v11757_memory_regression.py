#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

# Re-run the field-proven .56 write/correction/fresh-recall regression against
# the .57 bundle identity and evidence-loop supervisor mode. The iPhone stays .49.
path = Path("Tools/test_v11756_memory_regression.py")
source = path.read_text(encoding="utf-8")

if "0.11.7.56" not in source:
    raise SystemExit("v0.11.7.57 expected .56 memory regression identity missing")
source = source.replace("0.11.7.56", "0.11.7.57")
source = source.replace(
    "autonomous-source-grounded-project-learning-guarded",
    "autonomous-source-grounded-project-learning-evidence-loop",
)

exec(
    compile(source, str(path) + "[v11757]", "exec"),
    {"__name__": "__main__", "__file__": str(path)},
)
