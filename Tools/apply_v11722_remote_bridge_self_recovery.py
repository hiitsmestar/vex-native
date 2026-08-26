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

if '"version": "0.11.7.21"' not in bridge:
    raise SystemExit('v0.11.7.22 expected Bridge v0.11.7.21 source')
if 'VERSION = "0.11.7.21"' not in remote:
    raise SystemExit('v0.11.7.22 expected Remote Support v0.11.7.21 source')

bridge = bridge.replace('"version": "0.11.7.21"', '"version": "0.11.7.22"')
remote = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.22"', remote, count=1, flags=re.M)
doctor = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.22"', doctor, count=1, flags=re.M)

# Live field evidence on v0.11.7.21 showed process_count=0 while Remote Support
# remained healthy. Make Remote Support itself the final supervisor so Bridge
# recovery does not depend on the external PowerShell watchdog being alive.
anchor = '''def bridge_config() -> dict:\n    path = Path(os.environ.get("APPDATA", str(Path.home()))) / "VexBridge" / "config.json"\n    try:\n        return json.loads(path.read_text("utf-8"))\n    except Exception:\n        return {}\n\n\n'''
helper = r'''_BRIDGE_RECOVERY_LOCK = threading.Lock()
_BRIDGE_RECOVERY_LAST = 0.0


def bridge_runtime_dir() -> Path | None:
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent)
    else:
        candidates.append(Path(__file__).resolve().parent.parent)
    downloads = Path.home() / "Downloads"
    try:
        for p in downloads.iterdir():
            if p.is_dir() and (p / "START-VEX-SELF-HEAL.cmd").exists() and (p / "VexBridge.exe").exists():
                candidates.insert(0, p)
    except Exception:
        pass
    for p in candidates:
        if (p / "VexBridge.exe").exists():
            return p
    return None


def bridge_process_count() -> int:
    try:
        result = run_quiet(["tasklist.exe", "/FI", "IMAGENAME eq VexBridge.exe", "/NH", "/FO", "CSV"], timeout=8)
        text = (result.stdout or "").lower()
        return text.count('"vexbridge.exe"')
    except Exception:
        return 0


def ensure_bridge_process(force: bool = False) -> dict:
    global _BRIDGE_RECOVERY_LAST
    now = time.time()
    if not force and bridge_process_count() > 0:
        return {"launched": False, "reason": "already_running"}
    if not force and now - _BRIDGE_RECOVERY_LAST < 20:
        return {"launched": False, "reason": "cooldown"}
    if not _BRIDGE_RECOVERY_LOCK.acquire(blocking=False):
        return {"launched": False, "reason": "recovery_busy"}
    try:
        _BRIDGE_RECOVERY_LAST = time.time()
        home = bridge_runtime_dir()
        if not home:
            return {"launched": False, "reason": "bridge_binary_missing"}
        exe = home / "VexBridge.exe"
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen([str(exe)], cwd=str(home), creationflags=flags)
        return {"launched": True, "reason": "process_missing", "runtime_source": "user_owned"}
    except Exception as exc:
        return {"launched": False, "reason": "launch_failed", "error_class": exc.__class__.__name__}
    finally:
        _BRIDGE_RECOVERY_LOCK.release()


def bridge_candidate_ports(config: dict) -> list[int]:
    external = int(config.get("port") or 8765)
    preferred = int(config.get("local_control_port") or (external + 1))
    ports = [preferred]
    for p in range(external + 1, external + 13):
        if p not in ports:
            ports.append(p)
    return ports


def bridge_target_for_port(path: str, config: dict, port: int) -> tuple[str, dict] | None:
    token = str(config.get("token") or "").strip()
    if not token:
        return None
    return f"http://127.0.0.1:{port}{path}", {"token": token}


'''
if anchor not in remote:
    raise SystemExit('v0.11.7.22 bridge_config anchor missing')
remote = remote.replace(anchor, anchor + helper, 1)

old_get = '''def bridge_get(path: str, timeout: int = 8) -> dict:\n    target = bridge_url(path)\n    if not target:\n        return {"ok": False, "error": "bridge config unavailable"}\n    url, params = target\n    try:\n        response = _BRIDGE_SESSION.get(url, params=params, timeout=timeout)\n        payload = response.json() if response.content else {}\n        if not isinstance(payload, dict):\n            payload = {"value": payload}\n        payload.setdefault("http_status", response.status_code)\n        if response.status_code >= 400:\n            payload.setdefault("ok", False)\n        return payload\n    except Exception as exc:\n        return {"ok": False, "error": exc.__class__.__name__}\n'''
new_get = '''def bridge_get(path: str, timeout: int = 8) -> dict:\n    config = bridge_config()\n    if not str(config.get("token") or "").strip():\n        return {"ok": False, "error": "bridge config unavailable"}\n    last_error = "ConnectionError"\n    for attempt in range(2):\n        for port in bridge_candidate_ports(config):\n            target = bridge_target_for_port(path, config, port)\n            if not target:\n                continue\n            url, params = target\n            try:\n                response = _BRIDGE_SESSION.get(url, params=params, timeout=min(timeout, 4))\n                payload = response.json() if response.content else {}\n                if not isinstance(payload, dict):\n                    payload = {"value": payload}\n                payload.setdefault("http_status", response.status_code)\n                if response.status_code >= 400:\n                    payload.setdefault("ok", False)\n                if response.status_code < 500:\n                    return payload\n            except Exception as exc:\n                last_error = exc.__class__.__name__\n        if attempt == 0:\n            recovery = ensure_bridge_process()\n            if recovery.get("launched"):\n                time.sleep(3)\n                config = bridge_config()\n    return {"ok": False, "error": last_error, "process_count": bridge_process_count()}\n'''
if old_get not in remote:
    raise SystemExit('v0.11.7.22 bridge_get anchor missing')
remote = remote.replace(old_get, new_get, 1)

old_post = '''def bridge_post(path: str, payload: dict | None = None, timeout: int = 180) -> dict:\n    target = bridge_url(path)\n    if not target:\n        return {"ok": False, "error": "bridge config unavailable"}\n    url, params = target\n    try:\n        response = _BRIDGE_SESSION.post(url, params=params, json=payload or {}, timeout=timeout)\n        body = response.json() if response.content else {}\n        if not isinstance(body, dict):\n            body = {"value": body}\n        body.setdefault("http_status", response.status_code)\n        if response.status_code >= 400:\n            body.setdefault("ok", False)\n        return body\n    except Exception as exc:\n        return {"ok": False, "error": exc.__class__.__name__}\n'''
new_post = '''def bridge_post(path: str, payload: dict | None = None, timeout: int = 180) -> dict:\n    config = bridge_config()\n    if not str(config.get("token") or "").strip():\n        return {"ok": False, "error": "bridge config unavailable"}\n    last_error = "ConnectionError"\n    for attempt in range(2):\n        for port in bridge_candidate_ports(config):\n            target = bridge_target_for_port(path, config, port)\n            if not target:\n                continue\n            url, params = target\n            try:\n                response = _BRIDGE_SESSION.post(url, params=params, json=payload or {}, timeout=timeout)\n                body = response.json() if response.content else {}\n                if not isinstance(body, dict):\n                    body = {"value": body}\n                body.setdefault("http_status", response.status_code)\n                if response.status_code >= 400:\n                    body.setdefault("ok", False)\n                return body\n            except Exception as exc:\n                last_error = exc.__class__.__name__\n        if attempt == 0:\n            recovery = ensure_bridge_process()\n            if recovery.get("launched"):\n                time.sleep(3)\n                config = bridge_config()\n    return {"ok": False, "error": last_error, "process_count": bridge_process_count()}\n'''
if old_post not in remote:
    raise SystemExit('v0.11.7.22 bridge_post anchor missing')
remote = remote.replace(old_post, new_post, 1)

BRIDGE.write_text(bridge, encoding='utf-8')
REMOTE.write_text(remote, encoding='utf-8')
DOCTOR.write_text(doctor, encoding='utf-8')
compile(bridge, str(BRIDGE), 'exec')
compile(remote, str(REMOTE), 'exec')
compile(doctor, str(DOCTOR), 'exec')

for marker in [
    'VERSION = "0.11.7.22"',
    'def ensure_bridge_process(force: bool = False)',
    'def bridge_candidate_ports(config: dict)',
    'tasklist.exe',
    'recovery = ensure_bridge_process()',
]:
    if marker not in remote:
        raise SystemExit(f'v0.11.7.22 Remote verifier missing: {marker}')
if '"version": "0.11.7.22"' not in bridge:
    raise SystemExit('v0.11.7.22 Bridge version marker missing')
if 'VERSION = "0.11.7.22"' not in doctor:
    raise SystemExit('v0.11.7.22 Doctor version marker missing')

print('Applied v0.11.7.22 Remote Support bridge self-recovery')
