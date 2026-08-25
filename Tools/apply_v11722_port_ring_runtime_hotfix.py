#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

BRIDGE = Path('Bridge/vex_bridge.py')
REMOTE = Path('Tools/VexRemoteSupport.py')
INSTALLER = Path('Tools/VexInstall11722.py')
WATCHDOG = Path('Tools/VexBridgeWatchdog-v11722.ps1')

bridge = BRIDGE.read_text(encoding='utf-8')
remote = REMOTE.read_text(encoding='utf-8')
installer = INSTALLER.read_text(encoding='utf-8')
watchdog = WATCHDOG.read_text(encoding='utf-8')

if '"version": "0.11.7.22"' not in bridge:
    raise SystemExit('v0.11.7.22 Bridge marker missing before runtime hotfix')
if 'VERSION = "0.11.7.22"' not in remote:
    raise SystemExit('v0.11.7.22 Remote marker missing before runtime hotfix')

old_bridge = '''def start_local_control_server(config: dict):\n    external_port = int(config.get("port") or PORT)\n    preferred = int(config.get("local_control_port") or (external_port + 1))\n    last_error = None\n    for candidate in range(preferred, preferred + 12):\n'''
new_bridge = '''def start_local_control_server(config: dict):\n    external_port = int(config.get("port") or PORT)\n    reserved = list(range(external_port + 1, external_port + 33))\n    preferred = int(config.get("local_control_port") or (external_port + 1))\n    candidates = ([preferred] if preferred in reserved else []) + [p for p in reserved if p != preferred]\n    last_error = None\n    for candidate in candidates:\n'''
if old_bridge not in bridge:
    raise SystemExit('Bridge local-control candidate loop anchor missing')
bridge = bridge.replace(old_bridge, new_bridge, 1)

# The local control plane is the critical runtime path. A collision or TLS error
# on the optional LAN listener must never tear down the already-live loopback
# listener. Keep Bridge alive in local-only mode and surface the sanitized stage.
old_external = '''    _write_startup_stage("binding")\n    server = ReusableThreadingHTTPServer(("0.0.0.0", port), Handler)\n    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)\n    _write_startup_stage("tls")\n    context.load_cert_chain(certfile=str(CERT_PATH), keyfile=str(KEY_PATH))\n    server.socket = context.wrap_socket(server.socket, server_side=True)\n    _write_startup_stage("listening")\n    try:\n        server.serve_forever(poll_interval=0.5)\n    except KeyboardInterrupt:\n        print("\\nVex Bridge stopped.")\n    finally:\n        server.server_close()\n        try:\n            local_control_server.shutdown()\n            local_control_server.server_close()\n        except Exception:\n            pass\n'''
new_external = '''    server = None\n    try:\n        _write_startup_stage("binding")\n        server = ReusableThreadingHTTPServer(("0.0.0.0", port), Handler)\n        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)\n        _write_startup_stage("tls")\n        context.load_cert_chain(certfile=str(CERT_PATH), keyfile=str(KEY_PATH))\n        server.socket = context.wrap_socket(server.socket, server_side=True)\n        _write_startup_stage("listening")\n        server.serve_forever(poll_interval=0.5)\n    except KeyboardInterrupt:\n        print("\\nVex Bridge stopped.")\n    except Exception as exc:\n        _write_startup_stage("local_only", exc.__class__.__name__)\n        try:\n            while True:\n                time.sleep(60)\n        except KeyboardInterrupt:\n            pass\n    finally:\n        if server is not None:\n            try:\n                server.server_close()\n            except Exception:\n                pass\n        try:\n            local_control_server.shutdown()\n            local_control_server.server_close()\n        except Exception:\n            pass\n'''
if old_external not in bridge:
    raise SystemExit('Bridge external-listener block anchor missing')
bridge = bridge.replace(old_external, new_external, 1)

remote = re.sub(
    r'''def bridge_candidate_ports\(config: dict\) -> list\[int\]:\n    external = int\(config\.get\("port"\) or 8765\)\n    preferred = int\(config\.get\("local_control_port"\) or \(external \+ 1\)\)\n    ports = \[preferred\]\n    for p in range\(external \+ 1, external \+ 13\):\n        if p not in ports:\n            ports\.append\(p\)\n    return ports''',
    '''def bridge_candidate_ports(config: dict) -> list[int]:\n    external = int(config.get("port") or 8765)\n    reserved = list(range(external + 1, external + 33))\n    preferred = int(config.get("local_control_port") or (external + 1))\n    return ([preferred] if preferred in reserved else []) + [p for p in reserved if p != preferred]''',
    remote,
    count=1,
)

old_installer = '''def candidate_ports(cfg:dict)->list[int]:\n    external=int(cfg.get('port') or 8765); preferred=int(cfg.get('local_control_port') or (external+1)); ports=[preferred]\n    for p in range(external+1, external+13):\n        if p not in ports: ports.append(p)\n    return ports\n'''
new_installer = '''def candidate_ports(cfg:dict)->list[int]:\n    external=int(cfg.get('port') or 8765)\n    reserved=list(range(external+1, external+33))\n    preferred=int(cfg.get('local_control_port') or (external+1))\n    return ([preferred] if preferred in reserved else []) + [p for p in reserved if p != preferred]\n'''
if old_installer not in installer:
    raise SystemExit('Installer candidate-port anchor missing')
installer = installer.replace(old_installer, new_installer, 1)

old_watchdog = '''function Get-CandidatePorts($Cfg) {\n  $external=if($Cfg -and $Cfg.port){[int]$Cfg.port}else{8765}\n  $preferred=if($Cfg -and $Cfg.local_control_port){[int]$Cfg.local_control_port}else{($external+1)}\n  $ports=@($preferred)\n  foreach($p in (($external+1)..($external+12))){ if($ports -notcontains $p){ $ports += $p } }\n  return $ports\n}\n'''
new_watchdog = '''function Get-CandidatePorts($Cfg) {\n  $external=if($Cfg -and $Cfg.port){[int]$Cfg.port}else{8765}\n  $preferred=if($Cfg -and $Cfg.local_control_port){[int]$Cfg.local_control_port}else{($external+1)}\n  $reserved=@(($external+1)..($external+32))\n  $ports=@()\n  if($reserved -contains $preferred){ $ports += $preferred }\n  foreach($p in $reserved){ if($ports -notcontains $p){ $ports += $p } }\n  return $ports\n}\n'''
if old_watchdog not in watchdog:
    raise SystemExit('Watchdog candidate-port anchor missing')
watchdog = watchdog.replace(old_watchdog, new_watchdog, 1)

BRIDGE.write_text(bridge, encoding='utf-8')
REMOTE.write_text(remote, encoding='utf-8')
INSTALLER.write_text(installer, encoding='utf-8')
WATCHDOG.write_text(watchdog, encoding='utf-8')

compile(bridge, str(BRIDGE), 'exec')
compile(remote, str(REMOTE), 'exec')
compile(installer, str(INSTALLER), 'exec')

for marker in [
    'reserved = list(range(external_port + 1, external_port + 33))',
    'for candidate in candidates:',
    '_write_startup_stage("local_only", exc.__class__.__name__)',
    'while True:\n                time.sleep(60)',
]:
    if marker not in bridge:
        raise SystemExit(f'Bridge runtime hotfix missing: {marker}')
if 'reserved = list(range(external + 1, external + 33))' not in remote:
    raise SystemExit('Remote port-ring hotfix missing')
if 'reserved=list(range(external+1, external+33))' not in installer:
    raise SystemExit('Installer port-ring hotfix missing')
if '($external+1)..($external+32)' not in watchdog:
    raise SystemExit('Watchdog port-ring hotfix missing')

print('Applied v0.11.7.22 fixed port-ring + local-control survival hotfix')
