#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

BRIDGE = Path('Bridge/vex_bridge.py')
REMOTE = Path('Tools/VexRemoteSupport.py')
DOCTOR = Path('Tools/VexDoctor.py')
INSTALLER = Path('Tools/VexInstall11722.py')
WATCHDOG = Path('Tools/VexBridgeWatchdog-v11722.ps1')

bridge = BRIDGE.read_text(encoding='utf-8')
remote = REMOTE.read_text(encoding='utf-8')
doctor = DOCTOR.read_text(encoding='utf-8')
installer = INSTALLER.read_text(encoding='utf-8')
watchdog = WATCHDOG.read_text(encoding='utf-8')

for label, text, marker in [
    ('Bridge', bridge, '"version": "0.11.7.24"'),
    ('Remote', remote, 'VERSION = "0.11.7.24"'),
    ('Doctor', doctor, 'VERSION = "0.11.7.24"'),
    ('Installer', installer, "VERSION='0.11.7.24'"),
]:
    if marker not in text:
        raise SystemExit(f'v0.11.7.25 expected {label} v0.11.7.24 marker missing')

bridge = bridge.replace('"version": "0.11.7.24"', '"version": "0.11.7.25"')
remote = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.25"', remote, count=1, flags=re.M)
doctor = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.25"', doctor, count=1, flags=re.M)
installer = installer.replace("VERSION='0.11.7.24'", "VERSION='0.11.7.25'", 1)
watchdog = watchdog.replace('0.11.7.24', '0.11.7.25')

# Fast local TCP preflight keeps a dead 32-port ring from multiplying HTTP
# timeouts across every snapshot endpoint. Only ports that actually accept a
# loopback connection are queried with requests.
if '\nimport socket\n' not in remote:
    remote = remote.replace('\nimport shutil\n', '\nimport shutil\nimport socket\n', 1)

candidate_anchor = '''def bridge_candidate_ports(config: dict) -> list[int]:\n    external = int(config.get("port") or 8765)\n    reserved = list(range(external + 1, external + 33))\n    preferred = int(config.get("local_control_port") or (external + 1))\n    return ([preferred] if preferred in reserved else []) + [p for p in reserved if p != preferred]\n\n\n'''
if candidate_anchor not in remote:
    raise SystemExit('v0.11.7.25 candidate-port anchor missing')
probe_helper = '''def bridge_open_ports(config: dict, connect_timeout: float = 0.035) -> list[int]:\n    open_ports: list[int] = []\n    for port in bridge_candidate_ports(config):\n        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n        try:\n            sock.settimeout(connect_timeout)\n            if sock.connect_ex(("127.0.0.1", int(port))) == 0:\n                open_ports.append(int(port))\n        except Exception:\n            pass\n        finally:\n            try:\n                sock.close()\n            except Exception:\n                pass\n    return open_ports\n\n\n'''
remote = remote.replace(candidate_anchor, candidate_anchor + probe_helper, 1)

get_pattern = re.compile(r'''def bridge_get\(path: str, timeout: int = 8\) -> dict:\n.*?\n    return \{"ok": False, "error": last_error, "process_count": bridge_process_count\(\)\}\n''', re.S)
get_match = get_pattern.search(remote)
if not get_match:
    raise SystemExit('v0.11.7.25 bridge_get current self-recovery block missing')
new_get = '''def bridge_get(path: str, timeout: int = 8) -> dict:\n    config = bridge_config()\n    if not str(config.get("token") or "").strip():\n        return {"ok": False, "error": "bridge config unavailable"}\n    last_error = "ConnectionError"\n    for attempt in range(2):\n        ports = bridge_open_ports(config)\n        for port in ports:\n            target = bridge_target_for_port(path, config, port)\n            if not target:\n                continue\n            url, params = target\n            try:\n                response = _BRIDGE_SESSION.get(url, params=params, timeout=min(float(timeout), 1.25))\n                payload = response.json() if response.content else {}\n                if not isinstance(payload, dict):\n                    payload = {"value": payload}\n                payload.setdefault("http_status", response.status_code)\n                if response.status_code >= 400:\n                    payload.setdefault("ok", False)\n                if response.status_code < 500:\n                    return payload\n            except Exception as exc:\n                last_error = exc.__class__.__name__\n        if attempt == 0:\n            recovery = ensure_bridge_process()\n            if recovery.get("launched"):\n                time.sleep(1.5)\n                config = bridge_config()\n            elif not ports:\n                break\n    return {"ok": False, "error": last_error, "process_count": bridge_process_count()}\n'''
remote = remote[:get_match.start()] + new_get + remote[get_match.end():]

post_pattern = re.compile(r'''def bridge_post\(path: str, payload: dict \| None = None, timeout: int = 180\) -> dict:\n.*?\n    return \{"ok": False, "error": last_error, "process_count": bridge_process_count\(\)\}\n''', re.S)
post_match = post_pattern.search(remote)
if not post_match:
    raise SystemExit('v0.11.7.25 bridge_post current self-recovery block missing')
new_post = '''def bridge_post(path: str, payload: dict | None = None, timeout: int = 180) -> dict:\n    config = bridge_config()\n    if not str(config.get("token") or "").strip():\n        return {"ok": False, "error": "bridge config unavailable"}\n    last_error = "ConnectionError"\n    for attempt in range(2):\n        ports = bridge_open_ports(config)\n        for port in ports:\n            target = bridge_target_for_port(path, config, port)\n            if not target:\n                continue\n            url, params = target\n            try:\n                response = _BRIDGE_SESSION.post(url, params=params, json=payload or {}, timeout=timeout)\n                body = response.json() if response.content else {}\n                if not isinstance(body, dict):\n                    body = {"value": body}\n                body.setdefault("http_status", response.status_code)\n                if response.status_code >= 400:\n                    body.setdefault("ok", False)\n                return body\n            except Exception as exc:\n                last_error = exc.__class__.__name__\n        if attempt == 0:\n            recovery = ensure_bridge_process()\n            if recovery.get("launched"):\n                time.sleep(1.5)\n                config = bridge_config()\n            elif not ports:\n                break\n    return {"ok": False, "error": last_error, "process_count": bridge_process_count()}\n'''
remote = remote[:post_match.start()] + new_post + remote[post_match.end():]

# If /status is dead, do not serially probe four more Bridge endpoints. This
# makes the startup snapshot bounded even while Bridge is completely offline.
old_snapshot = '''def collect_snapshot(include_doctor: bool = False, deep: bool = False) -> dict:\n    status = bridge_get("/status", timeout=8)\n    llm = bridge_get("/llm/status", timeout=8)\n    art = bridge_get("/art/health", timeout=8)\n    learning = bridge_get("/learning/status", timeout=10)\n    maintenance = bridge_get("/maintenance/status", timeout=20)\n'''
new_snapshot = '''def collect_snapshot(include_doctor: bool = False, deep: bool = False) -> dict:\n    status = bridge_get("/status", timeout=2)\n    reachable = integer(status.get("http_status")) in range(200, 300)\n    if reachable:\n        llm = bridge_get("/llm/status", timeout=4)\n        art = bridge_get("/art/health", timeout=4)\n        learning = bridge_get("/learning/status", timeout=5)\n        maintenance = bridge_get("/maintenance/status", timeout=8)\n    else:\n        llm = {}\n        art = {}\n        learning = {}\n        maintenance = {}\n'''
if old_snapshot not in remote:
    raise SystemExit('v0.11.7.25 collect_snapshot anchor missing')
remote = remote.replace(old_snapshot, new_snapshot, 1)

# Session activation must not wait on the initial Bridge snapshot or GitHub post.
old_session = '''            state = load_state()\n            last_id = integer(state.get("last_comment_id"))\n            post_comment("session_started", collect_snapshot(include_doctor=False))\n            self.on_status("Support session is active")\n            threading.Thread(\n                target=_bridge_health_monitor,\n                args=(self,),\n                daemon=True,\n                name="VexBridgeHealthMonitor",\n            ).start()\n'''
new_session = '''            state = load_state()\n            last_id = integer(state.get("last_comment_id"))\n            self.on_status("Support session is active")\n\n            def announce_session_start() -> None:\n                try:\n                    post_comment("session_started", collect_snapshot(include_doctor=False))\n                except Exception:\n                    pass\n\n            threading.Thread(\n                target=announce_session_start,\n                daemon=True,\n                name="VexSessionAnnounce",\n            ).start()\n            threading.Thread(\n                target=_bridge_health_monitor,\n                args=(self,),\n                daemon=True,\n                name="VexBridgeHealthMonitor",\n            ).start()\n'''
if old_session not in remote:
    raise SystemExit('v0.11.7.25 support-session startup anchor missing')
remote = remote.replace(old_session, new_session, 1)

BRIDGE.write_text(bridge, encoding='utf-8')
REMOTE.write_text(remote, encoding='utf-8')
DOCTOR.write_text(doctor, encoding='utf-8')
INSTALLER.write_text(installer, encoding='utf-8')
WATCHDOG.write_text(watchdog, encoding='utf-8')

compile(bridge, str(BRIDGE), 'exec')
compile(remote, str(REMOTE), 'exec')
compile(doctor, str(DOCTOR), 'exec')
compile(installer, str(INSTALLER), 'exec')

for marker in [
    'VERSION = "0.11.7.25"',
    'def bridge_open_ports(config: dict, connect_timeout: float = 0.035)',
    'name="VexSessionAnnounce"',
    'self.on_status("Support session is active")',
    'if reachable:',
    'elif not ports:',
]:
    if marker not in remote:
        raise SystemExit(f'v0.11.7.25 Remote verifier missing: {marker}')
if '"version": "0.11.7.25"' not in bridge:
    raise SystemExit('v0.11.7.25 Bridge version missing')
if "VERSION='0.11.7.25'" not in installer:
    raise SystemExit('v0.11.7.25 Installer version missing')
if '0.11.7.25' not in watchdog:
    raise SystemExit('v0.11.7.25 Watchdog version missing')

print('Applied v0.11.7.25 bounded Bridge probes + nonblocking session activation')
