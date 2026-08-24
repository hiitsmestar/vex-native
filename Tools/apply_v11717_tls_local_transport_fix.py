#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

BRIDGE = Path('Bridge/vex_bridge.py')
REMOTE = Path('Tools/VexRemoteSupport.py')
bridge = BRIDGE.read_text(encoding='utf-8')
remote = REMOTE.read_text(encoding='utf-8')

if '"version": "0.11.7.16"' not in bridge:
    raise SystemExit('v0.11.7.17 expected Bridge v0.11.7.16 source')
if 'VERSION = "0.11.7.16"' not in remote:
    raise SystemExit('v0.11.7.17 expected Remote Support v0.11.7.16 source')

# Do TLS wrapping per accepted connection rather than wrapping the listening
# socket. This isolates malformed/raw TCP probes and makes handshake failures
# non-fatal to the serving loop.
class_anchor = '''class ReusableThreadingHTTPServer(ThreadingHTTPServer):\n    allow_reuse_address = True\n'''
class_replacement = '''class ReusableThreadingHTTPServer(ThreadingHTTPServer):\n    allow_reuse_address = True\n    daemon_threads = True\n\n\nclass TLSThreadingHTTPServer(ReusableThreadingHTTPServer):\n    def __init__(self, server_address, handler_class, ssl_context):\n        self.ssl_context = ssl_context\n        super().__init__(server_address, handler_class)\n\n    def get_request(self):\n        while True:\n            sock, addr = self.socket.accept()\n            try:\n                sock.settimeout(8.0)\n                tls_sock = self.ssl_context.wrap_socket(sock, server_side=True)\n                tls_sock.settimeout(None)\n                return tls_sock, addr\n            except (ssl.SSLError, OSError):\n                try:\n                    sock.close()\n                except Exception:\n                    pass\n'''
if class_anchor not in bridge:
    raise SystemExit('v0.11.7.17 reusable server anchor missing')
bridge = bridge.replace(class_anchor, class_replacement, 1)

old_server = '''    _write_startup_stage("binding")\n    server = ReusableThreadingHTTPServer(("0.0.0.0", port), Handler)\n    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)\n    _write_startup_stage("tls")\n    context.load_cert_chain(certfile=str(CERT_PATH), keyfile=str(KEY_PATH))\n    server.socket = context.wrap_socket(server.socket, server_side=True)\n    _write_startup_stage("listening")\n'''
new_server = '''    _write_startup_stage("tls")\n    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)\n    context.minimum_version = ssl.TLSVersion.TLSv1_2\n    context.load_cert_chain(certfile=str(CERT_PATH), keyfile=str(KEY_PATH))\n    _write_startup_stage("binding")\n    server = TLSThreadingHTTPServer(("0.0.0.0", port), Handler, context)\n    _write_startup_stage("listening")\n'''
if old_server not in bridge:
    raise SystemExit('v0.11.7.17 TLS server block anchor missing')
bridge = bridge.replace(old_server, new_server, 1)
bridge = bridge.replace('"version": "0.11.7.16"', '"version": "0.11.7.17"')

# Never let system/user proxy settings intercept loopback Bridge calls.
# Reuse one direct session for all Bridge GET/POST traffic.
requests_anchor = 'urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)\n'
requests_insert = '''urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)\n\n_BRIDGE_SESSION = requests.Session()\n_BRIDGE_SESSION.trust_env = False\n'''
if requests_anchor not in remote:
    raise SystemExit('v0.11.7.17 requests anchor missing')
remote = remote.replace(requests_anchor, requests_insert, 1)
remote = remote.replace('response = requests.get(url, params=params, timeout=timeout, verify=False)', 'response = _BRIDGE_SESSION.get(url, params=params, timeout=timeout, verify=False)')
remote = remote.replace('response = requests.post(url, params=params, json=payload or {}, timeout=timeout, verify=False)', 'response = _BRIDGE_SESSION.post(url, params=params, json=payload or {}, timeout=timeout, verify=False)')
remote = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.17"', remote, count=1, flags=re.M)

BRIDGE.write_text(bridge, encoding='utf-8')
REMOTE.write_text(remote, encoding='utf-8')
compile(bridge, str(BRIDGE), 'exec')
compile(remote, str(REMOTE), 'exec')

for marker in [
    '"version": "0.11.7.17"',
    'class TLSThreadingHTTPServer',
    'self.ssl_context.wrap_socket(sock, server_side=True)',
    'TLSThreadingHTTPServer(("0.0.0.0", port), Handler, context)',
    'context.minimum_version = ssl.TLSVersion.TLSv1_2',
]:
    if marker not in bridge:
        raise SystemExit(f'v0.11.7.17 Bridge verifier missing: {marker}')
for marker in [
    'VERSION = "0.11.7.17"',
    '_BRIDGE_SESSION.trust_env = False',
    '_BRIDGE_SESSION.get(',
    '_BRIDGE_SESSION.post(',
    'action == "safe_update"',
]:
    if marker not in remote:
        raise SystemExit(f'v0.11.7.17 Remote verifier missing: {marker}')

print('Applied v0.11.7.17 TLS accept + direct loopback transport fix')
