#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

INSTALLER = Path("Tools/VexAgentRuntimeInstall.py")
installer = INSTALLER.read_text(encoding="utf-8")

if 'BUNDLE_VERSION = "0.12.0"' not in installer:
    raise SystemExit("v0.12 readiness gate requires bootstrapped v0.12 installer")

anchor = "\n\ndef wait_direct_memory(seconds: int = 30) -> dict:\n"
helper = r'''

def wait_cognition(seconds: int = 150) -> dict:
    """Do not report a successful v0.12 install until the deployed PC model is usable."""
    deadline = time.time() + seconds
    last = "no response"
    while time.time() < deadline:
        try:
            status = local_bridge_get("/status", timeout=3.0)
            bundle = str(status.get("agent_runtime_bundle") or "")
            if bundle != BUNDLE_VERSION:
                last = f"runtime bundle is {bundle or 'missing'}, expected {BUNDLE_VERSION}"
                time.sleep(1.0)
                continue
            value = local_bridge_get("/llm/status", timeout=5.0)
            model = str(value.get("model") or "").strip()
            count = int(value.get("available_model_count") or 0)
            if bool(value.get("ok")) and model and count > 0:
                return value
            last = str(value.get("error") or f"model={model or 'none'} count={count}")
        except Exception as exc:
            last = f"{exc.__class__.__name__}: {exc}"
        time.sleep(1.0)
    raise RuntimeError(f"PC cognition did not become ready after v0.12 install: {last}")
'''
if "def wait_cognition(" not in installer:
    if anchor not in installer:
        raise SystemExit("v0.12 readiness gate could not find memory-wait anchor")
    installer = installer.replace(anchor, helper + anchor, 1)

main_anchor = "        launch(home / \"VexBridge.exe\", home)\n        wait_bridge()\n        memory = wait_memory()\n"
main_replacement = "        launch(home / \"VexBridge.exe\", home)\n        wait_bridge()\n        cognition = wait_cognition()\n        memory = wait_memory()\n"
if main_anchor in installer:
    installer = installer.replace(main_anchor, main_replacement, 1)
elif "        cognition = wait_cognition()\n" not in installer:
    raise SystemExit("v0.12 readiness gate could not attach cognition check")

# The component executables intentionally retain their own component versions.
# Make the success dialog explicit about the aggregate v0.12 agent bundle and
# prove which local model is actually serving before telling Star install succeeded.
old = '            "Vex Agent Runtime v0.12.0 installed.\\n\\n"\n'
new = '            f"Vex Agent Runtime {BUNDLE_VERSION} installed and verified.\\n\\n"\n'
if old in installer:
    installer = installer.replace(old, new, 1)
elif "installed and verified" not in installer:
    # Older generated source can still carry a pre-v0.12 literal at this point.
    import re
    installer, n = re.subn(r'            "Vex Agent Runtime v[^"\\n]+ installed\\.\\n\\n"\\n', new, installer, count=1)
    if n == 0:
        raise SystemExit("v0.12 readiness gate could not normalize success dialog")

model_line = '            f"Bridge {BRIDGE_VERSION}: ready\\n"\n'
model_replacement = model_line + '            f"PC cognition: ready ({cognition.get(\'model\') or \'local model\'})\\n"\n'
if "PC cognition: ready" not in installer:
    if model_line not in installer:
        raise SystemExit("v0.12 readiness gate could not find success-dialog Bridge line")
    installer = installer.replace(model_line, model_replacement, 1)

INSTALLER.write_text(installer, encoding="utf-8")
compile(installer, str(INSTALLER), "exec")

for marker in [
    "def wait_cognition(seconds: int = 150)",
    'status.get("agent_runtime_bundle")',
    'local_bridge_get("/llm/status"',
    "cognition = wait_cognition()",
    "installed and verified",
    "PC cognition: ready",
]:
    if marker not in installer:
        raise SystemExit(f"v0.12 readiness gate missing marker: {marker}")
print("Applied v0.12 live cognition install-readiness gate")
