#!/usr/bin/env python3
from pathlib import Path

path = Path("Tools/apply_v120_pc_health_autonomy.py")
text = path.read_text(encoding="utf-8")

# The health patch embeds generated Bridge source in one raw triple-quoted block.
# Its PowerShell probe needs the opposite quote delimiter so the patch script
# itself remains valid Python on a fresh checkout.
old_open = "    script = r'''$ErrorActionPreference='Stop'\n"
new_open = '    script = r"""$ErrorActionPreference=\'Stop\'\n'
old_close = "} | ConvertTo-Json -Depth 6 -Compress'''\n"
new_close = '} | ConvertTo-Json -Depth 6 -Compress"""\n'

if old_open in text:
    text = text.replace(old_open, new_open, 1)
if old_close in text:
    text = text.replace(old_close, new_close, 1)

# A raw generated Windows root written as r"C:\\" becomes the invalid r"C:\"
# once the outer raw layer is emitted. A forward-slash Windows root is accepted
# by pathlib/shutil and avoids that trailing-backslash syntax trap entirely.
bad_root = 'Path.home().anchor or r"C:\\"'
if bad_root in text:
    text = text.replace(bad_root, 'Path.home().anchor or "C:/"')

# The PC-health layer is injected into a Bridge assembled by a long cumulative
# patch chain. Do not rely on whichever imports an older Bridge happened to
# retain: bind every stdlib dependency used by /hardware/status inside the
# probe itself. This makes the frozen endpoint self-contained and prevents a
# late NameError from turning the otherwise healthy Bridge into HTTP 503.
hardware_anchor = 'def _v120_health_hardware_status() -> dict:\n    result = {'
hardware_hardened = (
    'def _v120_health_hardware_status() -> dict:\n'
    '    import json\n'
    '    import os\n'
    '    import shutil\n'
    '    import subprocess\n'
    '    import sys\n'
    '    from pathlib import Path\n'
    '    result = {'
)
if hardware_anchor in text:
    text = text.replace(hardware_anchor, hardware_hardened, 1)

# Keep the exact exception class for the public/sanitized status while adding
# the bounded message to CI/local diagnostics. The message contains only the
# probe exception; the probe intentionally does not collect secrets/serials.
error_anchor = '        result["error_class"] = exc.__class__.__name__\n'
error_hardened = (
    '        result["error_class"] = exc.__class__.__name__\n'
    '        result["error_detail"] = str(exc)[:300]\n'
)
if error_anchor in text and 'result["error_detail"] = str(exc)[:300]' not in text:
    text = text.replace(error_anchor, error_hardened, 1)

for required in [
    'def _v120_health_hardware_status() -> dict:',
    '    import subprocess\\n',
    '    from pathlib import Path\\n',
    'result["error_detail"] = str(exc)[:300]',
]:
    if required not in text:
        raise SystemExit(f"PC health prepare verifier missing: {required}")

compile(text, str(path), "exec")
path.write_text(text, encoding="utf-8")
print("Prepared v0.12 PC health autonomy patch source with self-contained hardware probe")
