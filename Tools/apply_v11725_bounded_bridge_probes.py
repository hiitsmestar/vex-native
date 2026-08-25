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

candidate_anchor = '''def bridge_candidate_ports(config: dict) -> list[int]:
    external = int(config.get("port") or 8765)
    reserved = list(range(external + 1, external + 33))
    preferred = int(config.get("local_control_port") or (external + 1))
    return ([preferred] if preferred in reserved else []) + [p for p in reserved if p != preferred]


'''
if candidate_anchor not in remote:
    raise SystemExit('v0.11.7.25 candidate-port anchor missing')
probe_helper = '''def bridge_open_ports(config: dict, connect_timeout: float = 0.035) -> list[int]:
    open_ports: list[int] = []
    for port in bridge_candidate_ports(config):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.settimeout(connect_timeout)
            if sock.connect_ex(("127.0.0.1", int(port))) == 0:
                open_ports.append(int(port))
        except Exception:
            pass
        finally:
            try:
                sock.close()
            except Exception:
                pass
    return open_ports


'''
remote = remote.replace(candidate_anchor, candidate_anchor + probe_helper, 1)

get_pattern = re.compile(r'''def bridge_get\(path: str, timeout: int = 8\) -> dict:\n.*?\n    return \{"ok": False, "error": last_error, "process_count": bridge_process_count\(\)\}\n''', re.S)
get_match = get_pattern.search(remote)
if not get_match:
    raise SystemExit('v0.11.7.25 bridge_get current self-recovery block missing')
new_get = '''def bridge_get(path: str, timeout: int = 8) -> dict:
    config = bridge_config()
    if not str(config.get("token") or "").strip():
        return {"ok": False, "error": "bridge config unavailable"}
    last_error = "ConnectionError"
    for attempt in range(2):
        ports = bridge_open_ports(config)
        for port in ports:
            target = bridge_target_for_port(path, config, port)
            if not target:
                continue
            url, params = target
            try:
                response = _BRIDGE_SESSION.get(url, params=params, timeout=min(float(timeout), 1.25))
                payload = response.json() if response.content else {}
                if not isinstance(payload, dict):
                    payload = {"value": payload}
                payload.setdefault("http_status", response.status_code)
                if response.status_code >= 400:
                    payload.setdefault("ok", False)
                if response.status_code < 500:
                    return payload
            except Exception as exc:
                last_error = exc.__class__.__name__
        if attempt == 0:
            recovery = ensure_bridge_process()
            if recovery.get("launched"):
                time.sleep(1.5)
                config = bridge_config()
            elif not ports:
                break
    return {"ok": False, "error": last_error, "process_count": bridge_process_count()}
'''
remote = remote[:get_match.start()] + new_get + remote[get_match.end():]

post_pattern = re.compile(r'''def bridge_post\(path: str, payload: dict \| None = None, timeout: int = 180\) -> dict:\n.*?\n    return \{"ok": False, "error": last_error, "process_count": bridge_process_count\(\)\}\n''', re.S)
post_match = post_pattern.search(remote)
if not post_match:
    raise SystemExit('v0.11.7.25 bridge_post current self-recovery block missing')
new_post = '''def bridge_post(path: str, payload: dict | None = None, timeout: int = 180) -> dict:
    config = bridge_config()
    if not str(config.get("token") or "").strip():
        return {"ok": False, "error": "bridge config unavailable"}
    last_error = "ConnectionError"
    for attempt in range(2):
        ports = bridge_open_ports(config)
        for port in ports:
            target = bridge_target_for_port(path, config, port)
            if not target:
                continue
            url, params = target
            try:
                response = _BRIDGE_SESSION.post(url, params=params, json=payload or {}, timeout=timeout)
                body = response.json() if response.content else {}
                if not isinstance(body, dict):
                    body = {"value": body}
                body.setdefault("http_status", response.status_code)
                if response.status_code >= 400:
                    body.setdefault("ok", False)
                return body
            except Exception as exc:
                last_error = exc.__class__.__name__
        if attempt == 0:
            recovery = ensure_bridge_process()
            if recovery.get("launched"):
                time.sleep(1.5)
                config = bridge_config()
            elif not ports:
                break
    return {"ok": False, "error": last_error, "process_count": bridge_process_count()}
'''
remote = remote[:post_match.start()] + new_post + remote[post_match.end():]

# If /status is dead, do not serially probe four more Bridge endpoints. This
# makes the startup snapshot bounded even while Bridge is completely offline.
old_snapshot = '''def collect_snapshot(include_doctor: bool = False, deep: bool = False) -> dict:
    status = bridge_get("/status", timeout=8)
    llm = bridge_get("/llm/status", timeout=8)
    art = bridge_get("/art/health", timeout=8)
    learning = bridge_get("/learning/status", timeout=10)
    maintenance = bridge_get("/maintenance/status", timeout=20)
'''
new_snapshot = '''def collect_snapshot(include_doctor: bool = False, deep: bool = False) -> dict:
    status = bridge_get("/status", timeout=2)
    reachable = integer(status.get("http_status")) in range(200, 300)
    if reachable:
        llm = bridge_get("/llm/status", timeout=4)
        art = bridge_get("/art/health", timeout=4)
        learning = bridge_get("/learning/status", timeout=5)
        maintenance = bridge_get("/maintenance/status", timeout=8)
    else:
        llm = {}
        art = {}
        learning = {}
        maintenance = {}
'''
if old_snapshot not in remote:
    raise SystemExit('v0.11.7.25 collect_snapshot anchor missing')
remote = remote.replace(old_snapshot, new_snapshot, 1)

# Session activation must not wait on the initial Bridge snapshot or GitHub post.
# Match only the stable prefix so earlier/later health-monitor edits do not make
# this patch brittle.
old_session = '''            state = load_state()
            last_id = integer(state.get("last_comment_id"))
            post_comment("session_started", collect_snapshot(include_doctor=False))
            self.on_status("Support session is active")
'''
new_session = '''            state = load_state()
            last_id = integer(state.get("last_comment_id"))
            self.on_status("Support session is active")

            def announce_session_start() -> None:
                try:
                    post_comment("session_started", collect_snapshot(include_doctor=False))
                except Exception:
                    pass

            threading.Thread(
                target=announce_session_start,
                daemon=True,
                name="VexSessionAnnounce",
            ).start()
'''
if old_session not in remote:
    raise SystemExit('v0.11.7.25 support-session startup prefix missing')
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
