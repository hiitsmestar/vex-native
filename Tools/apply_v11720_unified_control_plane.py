#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

BRIDGE = Path('Bridge/vex_bridge.py')
REMOTE = Path('Tools/VexRemoteSupport.py')
DOCTOR = Path('Tools/VexDoctor.py')
bridge = BRIDGE.read_text(encoding='utf-8')
remote = REMOTE.read_text(encoding='utf-8')
doctor = DOCTOR.read_text(encoding='utf-8')

if '"version": "0.11.7.19"' not in bridge:
    raise SystemExit('v0.11.7.20 expected Bridge v0.11.7.19 source')
if 'VERSION = "0.11.7.19"' not in remote:
    raise SystemExit('v0.11.7.20 expected Remote Support v0.11.7.19 source')

# One coordinated control plane: keep the existing TLS/LAN listener for iPhone
# and other clients, while adding a loopback-only HTTP listener for local Vex
# components. The local listener uses the same Handler/token contract, so there
# is one API surface without making Windows local health depend on TLS/proxies.
reindex_anchor = '''def start_background_reindex(state: BridgeState) -> None:\n    def loop() -> None:\n        while True:\n            time.sleep(600)\n            try:\n                state.index.rebuild()\n            except Exception:\n                pass\n    threading.Thread(target=loop, daemon=True).start()\n'''
local_helper = '''def start_local_control_server(config: dict):\n    external_port = int(config.get("port") or PORT)\n    preferred = int(config.get("local_control_port") or (external_port + 1))\n    last_error = None\n    for candidate in range(preferred, preferred + 12):\n        try:\n            server = ReusableThreadingHTTPServer(("127.0.0.1", candidate), Handler)\n            config["local_control_port"] = int(candidate)\n            config["local_control_protocol"] = "vex-local-v1"\n            save_config(config)\n            threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.5}, daemon=True).start()\n            return server\n        except OSError as exc:\n            last_error = exc\n    raise RuntimeError(f"local control bind failed: {last_error.__class__.__name__ if last_error else 'unknown'}")\n'''
if reindex_anchor not in bridge:
    raise SystemExit('v0.11.7.20 reindex anchor missing')
bridge = bridge.replace(reindex_anchor, reindex_anchor + '\n\n' + local_helper, 1)

port_anchor = '''    port = int(config.get("port", PORT))\n    address = lan_ip()\n    token = config["token"]\n'''
port_replacement = '''    port = int(config.get("port", PORT))\n    address = lan_ip()\n    token = config["token"]\n    local_control_server = start_local_control_server(config)\n'''
if port_anchor not in bridge:
    raise SystemExit('v0.11.7.20 main port anchor missing')
bridge = bridge.replace(port_anchor, port_replacement, 1)

finally_anchor = '''    finally:\n        server.server_close()\n'''
finally_replacement = '''    finally:\n        server.server_close()\n        try:\n            local_control_server.shutdown()\n            local_control_server.server_close()\n        except Exception:\n            pass\n'''
if finally_anchor not in bridge:
    raise SystemExit('v0.11.7.20 server close anchor missing')
bridge = bridge.replace(finally_anchor, finally_replacement, 1)

bridge = bridge.replace('"version": "0.11.7.19"', '"version": "0.11.7.20"')
status_marker = '                "version": "0.11.7.20",\n'
if status_marker not in bridge:
    raise SystemExit('v0.11.7.20 status version marker missing')
bridge = bridge.replace(status_marker, status_marker + '                "local_control_protocol": "vex-local-v1",\n', 1)

# Remote Support always talks to the local control listener. This deliberately
# does not touch the LAN/TLS endpoint used by the rest of VexNative.
old_url = '''    token = str(config.get("token") or "").strip()\n    port = int(config.get("port") or 8765)\n    if not token:\n        return None\n    return f"https://127.0.0.1:{port}{path}", {"token": token}\n'''
new_url = '''    token = str(config.get("token") or "").strip()\n    external_port = int(config.get("port") or 8765)\n    port = int(config.get("local_control_port") or (external_port + 1))\n    if not token:\n        return None\n    return f"http://127.0.0.1:{port}{path}", {"token": token}\n'''
if old_url not in remote:
    raise SystemExit('v0.11.7.20 Remote Support bridge_url anchor missing')
remote = remote.replace(old_url, new_url, 1)

# requests verify=False is harmless on HTTP, but remove it so the transport
# contract is explicit and no TLS behavior can leak back into loopback calls.
remote = remote.replace('_BRIDGE_SESSION.get(url, params=params, timeout=timeout, verify=False)', '_BRIDGE_SESSION.get(url, params=params, timeout=timeout)')
remote = remote.replace('_BRIDGE_SESSION.post(url, params=params, json=payload or {}, timeout=timeout, verify=False)', '_BRIDGE_SESSION.post(url, params=params, json=payload or {}, timeout=timeout)')

# Point the diagnostics TCP probe at the same local control port.
old_probe = '''        cfg = bridge_config()\n        port = int(cfg.get("port") or 8765)\n        with socket.create_connection(("127.0.0.1", port), timeout=2):\n'''
new_probe = '''        cfg = bridge_config()\n        external_port = int(cfg.get("port") or 8765)\n        port = int(cfg.get("local_control_port") or (external_port + 1))\n        with socket.create_connection(("127.0.0.1", port), timeout=2):\n'''
if old_probe not in remote:
    raise SystemExit('v0.11.7.20 TCP probe anchor missing')
remote = remote.replace(old_probe, new_probe, 1)
remote = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.20"', remote, count=1, flags=re.M)

# Doctor reports whether diagnostics executed separately from whether the host
# is healthy. CI runs on an intentionally empty runner, so a broken/degraded
# health result is valid smoke output and must not be confused with execution
# failure. Keep both values in the JSON contract and align Doctor identity.
doctor = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.20"', doctor, count=1, flags=re.M)
doctor_anchor = '''    report = collect(deep=args.deep)\n    json_path, txt_path = write_report(report, args.json_out)\n'''
doctor_replacement = '''    report = collect(deep=args.deep)\n    report["ok"] = True\n    report["overall"] = report["summary"]["overall"]\n    json_path, txt_path = write_report(report, args.json_out)\n'''
if doctor_anchor not in doctor:
    raise SystemExit('v0.11.7.20 Doctor headless anchor missing')
doctor = doctor.replace(doctor_anchor, doctor_replacement, 1)

BRIDGE.write_text(bridge, encoding='utf-8')
REMOTE.write_text(remote, encoding='utf-8')
DOCTOR.write_text(doctor, encoding='utf-8')
compile(bridge, str(BRIDGE), 'exec')
compile(remote, str(REMOTE), 'exec')
compile(doctor, str(DOCTOR), 'exec')

for marker in [
    '"version": "0.11.7.20"',
    'def start_local_control_server(config: dict)',
    'ReusableThreadingHTTPServer(("127.0.0.1", candidate), Handler)',
    '"local_control_protocol": "vex-local-v1"',
    'local_control_server = start_local_control_server(config)',
]:
    if marker not in bridge:
        raise SystemExit(f'v0.11.7.20 Bridge verifier missing: {marker}')
for marker in [
    'VERSION = "0.11.7.20"',
    'config.get("local_control_port")',
    'return f"http://127.0.0.1:{port}{path}"',
    '_BRIDGE_SESSION.get(url, params=params, timeout=timeout)',
    '_BRIDGE_SESSION.post(url, params=params, json=payload or {}, timeout=timeout)',
]:
    if marker not in remote:
        raise SystemExit(f'v0.11.7.20 Remote verifier missing: {marker}')
for marker in [
    'VERSION = "0.11.7.20"',
    'report["ok"] = True',
    'report["overall"] = report["summary"]["overall"]',
]:
    if marker not in doctor:
        raise SystemExit(f'v0.11.7.20 Doctor verifier missing: {marker}')

print('Applied v0.11.7.20 unified local control plane')
