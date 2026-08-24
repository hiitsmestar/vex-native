#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

BRIDGE = Path('Bridge/vex_bridge.py')
REMOTE = Path('Tools/VexRemoteSupport.py')
bridge = BRIDGE.read_text(encoding='utf-8')
remote = REMOTE.read_text(encoding='utf-8')

if '"version": "0.11.7.15"' not in bridge:
    raise SystemExit('v0.11.7.16 expected Bridge v0.11.7.15 source')
if 'VERSION = "0.11.7.15"' not in remote:
    raise SystemExit('v0.11.7.16 expected Remote Support v0.11.7.15 source')

# Restore the original all-interface listener behavior while keeping health probes local.
bridge = bridge.replace('ThreadingHTTPServer(("127.0.0.1", port), Handler)', 'ReusableThreadingHTTPServer(("0.0.0.0", port), Handler)', 1)

handler_anchor = '\n\nclass Handler(BaseHTTPRequestHandler):\n'
server_class = '''\n\nclass ReusableThreadingHTTPServer(ThreadingHTTPServer):\n    allow_reuse_address = True\n\n'''
if handler_anchor not in bridge:
    raise SystemExit('v0.11.7.16 handler anchor missing')
bridge = bridge.replace(handler_anchor, server_class + handler_anchor, 1)

# Clear stale stage data on every launch so a dead process can never look like it reached listening.
main_anchor = 'def main() -> None:\n'
if main_anchor not in bridge:
    raise SystemExit('v0.11.7.16 main anchor missing')
bridge = bridge.replace(main_anchor, '''def main() -> None:\n    try:\n        (app_dir() / "startup-health.json").unlink(missing_ok=True)\n    except Exception:\n        pass\n''', 1)

# Record fatal startup exceptions without exposing paths/content.
entry = 'if __name__ == "__main__":\n    main()\n'
wrapped = '''if __name__ == "__main__":\n    try:\n        main()\n    except Exception as exc:\n        _write_startup_stage("fatal", exc.__class__.__name__)\n        raise\n'''
if entry not in bridge:
    raise SystemExit('v0.11.7.16 entrypoint anchor missing')
bridge = bridge.replace(entry, wrapped, 1)
bridge = bridge.replace('"version": "0.11.7.15"', '"version": "0.11.7.16"')

# More useful but still sanitized Bridge diagnostics in Remote Support.
helper_anchor = '\n\ndef _bridge_health_public() -> dict:\n'
helper = '''\n\ndef _bridge_startup_meta() -> dict:\n    try:\n        path = Path(os.environ.get("APPDATA", str(Path.home()))) / "VexBridge" / "startup-health.json"\n        data = json.loads(path.read_text("utf-8"))\n        stamp = int(data.get("time") or 0)\n        age = max(0, int(time.time()) - stamp) if stamp else 0\n        return {\n            "stage": str(data.get("stage") or "")[:48] or None,\n            "error_class": str(data.get("error_class") or "")[:80] or None,\n            "age_seconds": age,\n        }\n    except Exception:\n        return {"stage": None, "error_class": None, "age_seconds": 0}\n\n\ndef _bridge_tcp_probe() -> bool:\n    try:\n        import socket\n        cfg = bridge_config()\n        port = int(cfg.get("port") or 8765)\n        with socket.create_connection(("127.0.0.1", port), timeout=2):\n            return True\n    except Exception:\n        return False\n'''
if helper_anchor not in remote:
    raise SystemExit('v0.11.7.16 remote health anchor missing')
remote = remote.replace(helper_anchor, helper + helper_anchor, 1)

marker = '        "startup_stage": _bridge_startup_stage(),\n'
if marker not in remote:
    raise SystemExit('v0.11.7.16 startup marker missing')
remote = remote.replace(marker, '''        "startup_stage": _bridge_startup_meta().get("stage"),\n        "startup_error_class": _bridge_startup_meta().get("error_class"),\n        "startup_stage_age_seconds": int(_bridge_startup_meta().get("age_seconds") or 0),\n        "tcp_reachable": _bridge_tcp_probe(),\n''', 1)
remote = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.16"', remote, count=1, flags=re.M)

BRIDGE.write_text(bridge, encoding='utf-8')
REMOTE.write_text(remote, encoding='utf-8')
compile(bridge, str(BRIDGE), 'exec')
compile(remote, str(REMOTE), 'exec')

for marker in [
    '"version": "0.11.7.16"',
    'class ReusableThreadingHTTPServer',
    'ReusableThreadingHTTPServer(("0.0.0.0", port), Handler)',
    '_write_startup_stage("fatal", exc.__class__.__name__)',
]:
    if marker not in bridge:
        raise SystemExit(f'v0.11.7.16 Bridge verifier missing: {marker}')
for marker in [
    'VERSION = "0.11.7.16"',
    'def _bridge_tcp_probe()',
    '"tcp_reachable": _bridge_tcp_probe()',
    '"startup_stage_age_seconds"',
    'action == "safe_update"',
]:
    if marker not in remote:
        raise SystemExit(f'v0.11.7.16 Remote verifier missing: {marker}')

print('Applied v0.11.7.16 Bridge bind + diagnostics hardening')
