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

# Make the generated PC-health layer self-contained. The long cumulative Bridge
# build has changed its top-level imports several times; health/maintenance must
# not inherit accidental dependencies from whichever older patch ran first.
layer_anchor = 'V120_IDLE_ROTATION = "v0.12-idle-productive-rotation-v1"\n'
layer_imports = (
    layer_anchor
    + 'import json\n'
    + 'import os\n'
    + 'import re\n'
    + 'import shutil\n'
    + 'import subprocess\n'
    + 'import sys\n'
    + 'import time\n'
    + 'from pathlib import Path\n'
)
if layer_anchor in text and layer_imports not in text:
    text = text.replace(layer_anchor, layer_imports, 1)

# Bind every dependency again inside the hardware probe. This protects the
# frozen endpoint even if a later generated-source transform moves the layer.
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

# Keep exact bounded diagnostic detail for the two field-proof surfaces. These
# messages are local/CI diagnostics and contain only exception text from the
# hardware/housekeeping probes, not private memory or user content.
hardware_error_anchor = '        result["error_class"] = exc.__class__.__name__\n'
hardware_error_hardened = (
    '        result["error_class"] = exc.__class__.__name__\n'
    '        result["error_detail"] = str(exc)[:300]\n'
)
if hardware_error_anchor in text and 'result["error_detail"] = str(exc)[:300]' not in text:
    text = text.replace(hardware_error_anchor, hardware_error_hardened, 1)

housekeeping_error_anchor = (
    '    except Exception as exc:\n'
    '        return {"ok": False, "error": exc.__class__.__name__, "policy_version": V120_PC_HEALTH_AUTONOMY}\n\n\n'
    'def _v120_health_delete_items'
)
housekeeping_error_hardened = (
    '    except Exception as exc:\n'
    '        return {"ok": False, "error": exc.__class__.__name__, "error_detail": str(exc)[:300], '
    '"policy_version": V120_PC_HEALTH_AUTONOMY}\n\n\n'
    'def _v120_health_delete_items'
)
if housekeeping_error_anchor in text:
    text = text.replace(housekeeping_error_anchor, housekeeping_error_hardened, 1)

maintenance_anchor = (
    '        "ok": bool(audit.get("ok")),\n'
    '        "state": state,\n'
)
maintenance_hardened = (
    '        "ok": bool(audit.get("ok")),\n'
    '        "audit_error": str(audit.get("error") or "")[:120],\n'
    '        "audit_error_detail": str(audit.get("error_detail") or "")[:300],\n'
    '        "state": state,\n'
)
if maintenance_anchor in text and '"audit_error_detail": str(audit.get("error_detail") or "")[:300]' not in text:
    text = text.replace(maintenance_anchor, maintenance_hardened, 1)

for required in [
    'V120_IDLE_ROTATION = "v0.12-idle-productive-rotation-v1"\nimport json\nimport os\n',
    'def _v120_health_hardware_status() -> dict:',
    '    import subprocess\n',
    '    from pathlib import Path\n',
    'result["error_detail"] = str(exc)[:300]',
    '"audit_error_detail": str(audit.get("error_detail") or "")[:300]',
]:
    if required not in text:
        raise SystemExit(f"PC health prepare verifier missing: {required}")

compile(text, str(path), "exec")
path.write_text(text, encoding="utf-8")
print("Prepared v0.12 PC health autonomy patch with self-contained health imports and diagnostics")
