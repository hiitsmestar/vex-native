#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
REMOTE = Path("Tools/VexRemoteSupport.py")
bridge = BRIDGE.read_text(encoding="utf-8")
remote = REMOTE.read_text(encoding="utf-8")

if 'VERSION = "0.11.7.13"' not in remote:
    raise SystemExit("v0.11.7.14 expected Remote Support v0.11.7.13 source")
if '"version": "0.11.7.12"' not in bridge:
    raise SystemExit("v0.11.7.14 expected Bridge v0.11.7.12 source")

# Never block Bridge startup on the folder picker. Folder selection is now
# explicit (--setup) only; an empty folder list still starts a healthy listener.
old_setup = '''    if args.setup or not config.get("folders"):\n        config["folders"] = choose_folders(config.get("folders", []))\n        save_config(config)\n'''
new_setup = '''    if args.setup:\n        config["folders"] = choose_folders(config.get("folders", []))\n        save_config(config)\n'''
if old_setup not in bridge:
    raise SystemExit("v0.11.7.14 startup folder-prompt anchor missing")
bridge = bridge.replace(old_setup, new_setup, 1)

# Lightweight local startup stage telemetry. It contains only stage/error class
# and never paths, tokens, filenames, or personal content.
insert_anchor = '\n\ndef ensure_certificate() -> None:\n'
if insert_anchor not in bridge:
    raise SystemExit("v0.11.7.14 telemetry anchor missing")
telemetry = '''\n\ndef _write_startup_stage(stage: str, error_class: str | None = None) -> None:\n    try:\n        payload = {"stage": str(stage)[:48], "error_class": (str(error_class)[:80] if error_class else None), "time": int(time.time())}\n        (app_dir() / "startup-health.json").write_text(json.dumps(payload), encoding="utf-8")\n    except Exception:\n        pass\n'''
bridge = bridge.replace(insert_anchor, telemetry + insert_anchor, 1)

main_anchor = '    config = load_config()\n'
if main_anchor not in bridge:
    raise SystemExit("v0.11.7.14 main anchor missing")
bridge = bridge.replace(main_anchor, '    _write_startup_stage("config")\n    config = load_config()\n', 1)
bridge = bridge.replace('    ensure_certificate()\n', '    _write_startup_stage("certificate")\n    ensure_certificate()\n', 1)
bridge = bridge.replace('    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)\n', '    _write_startup_stage("binding")\n    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)\n', 1)
bridge = bridge.replace('    context.load_cert_chain(certfile=str(CERT_PATH), keyfile=str(KEY_PATH))\n', '    _write_startup_stage("tls")\n    context.load_cert_chain(certfile=str(CERT_PATH), keyfile=str(KEY_PATH))\n', 1)
bridge = bridge.replace('    try:\n        server.serve_forever(poll_interval=0.5)\n', '    _write_startup_stage("listening")\n    try:\n        server.serve_forever(poll_interval=0.5)\n', 1)
bridge = bridge.replace('"version": "0.11.7.12"', '"version": "0.11.7.14"')

# Surface only the sanitized local startup stage in Remote Support health.
health_return = '        "listener_verified": reachable,\n'
if health_return not in remote:
    raise SystemExit("v0.11.7.14 health return anchor missing")
remote = remote.replace(health_return, health_return + '        "startup_stage": _bridge_startup_stage(),\n', 1)
helper_anchor = '\n\ndef _bridge_health_public() -> dict:\n'
helper = '''\n\ndef _bridge_startup_stage() -> str | None:\n    try:\n        path = Path(os.environ.get("APPDATA", str(Path.home()))) / "VexBridge" / "startup-health.json"\n        data = json.loads(path.read_text("utf-8"))\n        value = str(data.get("stage") or "").strip()\n        return value[:48] or None\n    except Exception:\n        return None\n'''
if helper_anchor not in remote:
    raise SystemExit("v0.11.7.14 health helper anchor missing")
remote = remote.replace(helper_anchor, helper + helper_anchor, 1)
remote = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.14"', remote, count=1, flags=re.M)

BRIDGE.write_text(bridge, encoding="utf-8")
REMOTE.write_text(remote, encoding="utf-8")
compile(bridge, str(BRIDGE), "exec")
compile(remote, str(REMOTE), "exec")

for marker in ['"version": "0.11.7.14"','if args.setup:','_write_startup_stage("listening")','ThreadingHTTPServer(("127.0.0.1", port), Handler)']:
    if marker not in bridge:
        raise SystemExit(f"v0.11.7.14 Bridge verifier missing: {marker}")
for marker in ['VERSION = "0.11.7.14"','def _bridge_startup_stage()','"startup_stage": _bridge_startup_stage()','action == "safe_update"']:
    if marker not in remote:
        raise SystemExit(f"v0.11.7.14 Remote verifier missing: {marker}")
print("Applied v0.11.7.14 nonblocking Bridge bootstrap + startup telemetry")
