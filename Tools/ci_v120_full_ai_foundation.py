#!/usr/bin/env python3
from pathlib import Path

source_path = Path("Tools/ci_v11780_memory_route_punctuation_fix.py")
source = source_path.read_text(encoding="utf-8")

if "0.11.7.80" not in source:
    raise SystemExit("v0.12.0 expected .80 build identity missing")

# ci_v11780 is source-generating source. Extend its final nested cumulative patch
# list directly, preserving the escaping shape it expects, so the v0.12 bootstrap
# runs before installer hardening/resilience/readiness verification.
anchor = '''        '        \\\"Tools/apply_v11780_memory_route_punctuation_fix.py\\\",\\\\n'\n'''
addition = anchor + '''        '        \\\"Tools/apply_v120_conversation_route_entry.py\\\",\\\\n'\n        '        \\\"Tools/apply_v120_installer_lock_fix.py\\\",\\\\n'\n        '        \\\"Tools/apply_v120_cognition_model_resilience.py\\\",\\\\n'\n        '        \\\"Tools/apply_v120_install_readiness_gate.py\\\",\\\\n'\n'''
if anchor not in source:
    raise SystemExit("v0.12.0 nested .80 patch anchor missing")
source = source.replace(anchor, addition, 1)

source = source.replace("0.11.7.80", "0.12.0")
source = source.replace(
    'Vex-Agent-Runtime-v0.12.0-MemoryRoutePunctuationFix',
    'Vex-Agent-Runtime-v0.12.0-FullAIFoundation',
)
source = source.replace(
    'Vex Agent Runtime v0.12.0 Memory Route Punctuation Fix',
    'Vex Agent Runtime v0.12.0 Full AI Foundation',
)

globals_dict = {
    "__name__": "__main__",
    "__file__": str(source_path),
    "__package__": None,
}
exec(compile(source, str(source_path) + "[v120]", "exec"), globals_dict)
