#!/usr/bin/env python3
from pathlib import Path

bridge_path = Path("Bridge/vex_bridge.py")
text = bridge_path.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global text
    if old not in text:
        raise SystemExit(f"{label}: expected source block not found")
    text = text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# 1) Make config loading defensive. A partially-written/corrupt JSON file should
# not strand the phone pairing or kill startup. Back up the bad file, salvage the
# token/port when possible, and atomically rewrite a valid config.
# ---------------------------------------------------------------------------
old_load = '''def load_config() -> dict:\n    if CONFIG_PATH.exists():\n        try:\n            return json.loads(CONFIG_PATH.read_text("utf-8"))\n        except Exception:\n            pass\n    config = {\n        "token": secrets.token_urlsafe(32),\n        "folders": [],\n        "web_search": True,\n        "port": PORT,\n    }\n    save_config(config)\n    return config\n\n\ndef save_config(config: dict) -> None:\n    CONFIG_PATH.write_text(json.dumps(config, indent=2), "utf-8")\n'''
new_load = r'''def _config_backup(raw: str, label: str = "corrupt") -> Path | None:
    try:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        target = CONFIG_PATH.with_name(f"config.{label}.{stamp}.json")
        target.write_text(raw, "utf-8")
        return target
    except Exception:
        return None


def _salvage_config(raw: str) -> dict:
    result = {}
    token = re.search(r'"token"\s*:\s*"([^"\\]{12,})"', raw)
    port = re.search(r'"port"\s*:\s*(\d{2,5})', raw)
    if token:
        result["token"] = token.group(1)
    if port:
        value = int(port.group(1))
        if 1 <= value <= 65535:
            result["port"] = value
    return result


def load_config() -> dict:
    defaults = {
        "token": secrets.token_urlsafe(32),
        "folders": [],
        "web_search": True,
        "port": PORT,
    }
    if CONFIG_PATH.exists():
        raw = ""
        try:
            raw = CONFIG_PATH.read_text("utf-8")
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                merged = dict(defaults)
                merged.update(loaded)
                if not str(merged.get("token") or "").strip():
                    merged["token"] = defaults["token"]
                return merged
        except Exception as exc:
            print(f"[self-repair] config parse failed: {exc}", flush=True)
            if raw:
                backup = _config_backup(raw)
                salvaged = _salvage_config(raw)
                defaults.update(salvaged)
                if backup:
                    print(f"[self-repair] backed up damaged config to {backup}", flush=True)
    save_config(defaults)
    return defaults


def save_config(config: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = CONFIG_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(config, indent=2), "utf-8")
    temp.replace(CONFIG_PATH)
'''
replace_once(old_load, new_load, "defensive config loader")


# ---------------------------------------------------------------------------
# 2) Runtime self-repair supervisor. This is intentionally bounded recovery,
# not arbitrary self-modifying code. It can repair state files, restart local
# services, refresh stale indexing, and record diagnostics without deleting
# personal files or reinstalling anything.
# ---------------------------------------------------------------------------
insert_marker = "def _vex_background_services() -> None:\n"
if insert_marker not in text:
    raise SystemExit("background services marker missing")

self_repair = r'''SELF_REPAIR_ROOT = CONFIG_PATH.parent / "self-repair"
SELF_REPAIR_STATE = SELF_REPAIR_ROOT / "state.json"
SELF_REPAIR_INTERVAL = 45
SELF_REPAIR_SERVICE_COOLDOWN = 300
SELF_REPAIR_MAX_ATTEMPTS_WINDOW = 3
SELF_REPAIR_WINDOW_SECONDS = 1800
_SELF_REPAIR_LOCK = threading.Lock()
_SELF_REPAIR_LAST = {"ollama": 0.0, "art": 0.0, "index": 0.0}
_SELF_REPAIR_ATTEMPTS = {"ollama": [], "art": [], "index": []}


def _sr_now() -> float:
    return time.time()


def _sr_trim_attempts(kind: str) -> list[float]:
    now = _sr_now()
    values = [float(v) for v in _SELF_REPAIR_ATTEMPTS.get(kind, []) if now - float(v) < SELF_REPAIR_WINDOW_SECONDS]
    _SELF_REPAIR_ATTEMPTS[kind] = values
    return values


def _sr_can_attempt(kind: str, force: bool = False) -> bool:
    if force:
        return True
    now = _sr_now()
    if now - float(_SELF_REPAIR_LAST.get(kind, 0.0)) < SELF_REPAIR_SERVICE_COOLDOWN:
        return False
    return len(_sr_trim_attempts(kind)) < SELF_REPAIR_MAX_ATTEMPTS_WINDOW


def _sr_mark_attempt(kind: str) -> None:
    now = _sr_now()
    _SELF_REPAIR_LAST[kind] = now
    _SELF_REPAIR_ATTEMPTS.setdefault(kind, []).append(now)
    _sr_trim_attempts(kind)


def _sr_read_state() -> dict:
    try:
        data = json.loads(SELF_REPAIR_STATE.read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _sr_write_state(state: dict) -> None:
    try:
        SELF_REPAIR_ROOT.mkdir(parents=True, exist_ok=True)
        history = list(state.get("history") or [])[-80:]
        state["history"] = history
        temp = SELF_REPAIR_STATE.with_suffix(".tmp")
        temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), "utf-8")
        temp.replace(SELF_REPAIR_STATE)
    except Exception as exc:
        print(f"[self-repair] state write warning: {exc}", flush=True)


def _sr_record(component: str, action: str, ok: bool, detail: str = "") -> None:
    with _SELF_REPAIR_LOCK:
        state = _sr_read_state()
        event = {
            "time": _sr_now(),
            "component": component,
            "action": action,
            "ok": bool(ok),
            "detail": str(detail or "")[:1800],
        }
        history = list(state.get("history") or [])
        history.append(event)
        state["history"] = history[-80:]
        state["last_event"] = event
        _sr_write_state(state)
    print(f"[self-repair] {component}: {action}: {'ok' if ok else 'failed'} {detail}", flush=True)


def _sr_repair_skill_store() -> tuple[bool, str]:
    try:
        path = _skills_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            _save_skills({"schema": SKILL_SCHEMA_VERSION, "skills": []})
            return True, "created missing learned-skills store"
        raw = path.read_text("utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict) or not isinstance(data.get("skills"), list):
            raise ValueError("invalid learned-skills schema")
        return True, "healthy"
    except Exception as exc:
        try:
            path = _skills_path()
            if path.exists():
                stamp = time.strftime("%Y%m%d-%H%M%S")
                backup = path.with_name(f"learned_skills.corrupt.{stamp}.json")
                backup.write_bytes(path.read_bytes())
            _save_skills({"schema": SKILL_SCHEMA_VERSION, "skills": []})
            return True, f"rebuilt learned-skills store after {exc}"
        except Exception as repair_exc:
            return False, f"skill repair failed: {repair_exc}"


def _sr_ollama_healthy() -> bool:
    try:
        import requests
        response = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=2.5)
        return response.status_code < 400
    except Exception:
        return False


def _sr_find_ollama() -> str | None:
    candidates = []
    try:
        import shutil
        found = shutil.which("ollama")
        if found:
            candidates.append(found)
    except Exception:
        pass
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    candidates.extend([
        str(local / "Programs" / "Ollama" / "ollama.exe"),
        str(Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Ollama" / "ollama.exe"),
    ])
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def _sr_restart_ollama(force: bool = False) -> tuple[bool, str]:
    if _sr_ollama_healthy():
        return True, "already healthy"
    if not _sr_can_attempt("ollama", force=force):
        return False, "restart circuit breaker active"
    _sr_mark_attempt("ollama")
    exe = _sr_find_ollama()
    if not exe:
        return False, "ollama executable not found"
    try:
        import subprocess
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(
            [exe, "serve"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
        for _ in range(30):
            time.sleep(1)
            if _sr_ollama_healthy():
                return True, "restarted Ollama service"
        return False, "Ollama did not answer after restart"
    except Exception as exc:
        return False, f"Ollama restart failed: {exc}"


def _sr_art_installed() -> bool:
    return ART_PYTHON.exists() and (ART_COMFY_DIR / "main.py").exists()


def _sr_repair_art(force: bool = False) -> tuple[bool, str]:
    if not _sr_art_installed():
        return True, "art engine not installed on this node"
    if _art_comfy_health(timeout=1.0):
        return True, "already healthy"
    if not _sr_can_attempt("art", force=force):
        return False, "restart circuit breaker active"
    _sr_mark_attempt("art")
    ok, error = _ensure_art_comfy()
    return bool(ok), "restarted ComfyUI" if ok else str(error or "ComfyUI restart failed")


def _sr_repair_index(force: bool = False) -> tuple[bool, str]:
    if STATE is None or getattr(STATE, "index", None) is None:
        return False, "Bridge index is not initialized"
    index = STATE.index
    if getattr(index, "_vex_indexing", False):
        return True, "index refresh already running"
    age = _sr_now() - float(getattr(index, "last_indexed", 0.0) or 0.0)
    docs = len(getattr(index, "documents", []) or [])
    stale = age > 20 * 60 or docs == 0
    if not stale and not force:
        return True, f"healthy ({docs} files)"
    if not _sr_can_attempt("index", force=force):
        return False, "index repair circuit breaker active"
    _sr_mark_attempt("index")
    try:
        threading.Thread(target=index.rebuild, daemon=True, name="VexSelfRepairIndex").start()
        return True, "started index rebuild"
    except Exception as exc:
        return False, f"index restart failed: {exc}"


def _sr_run_once(force: bool = False, include_art: bool = True) -> dict:
    result = {"ok": True, "node_name": socket.gethostname(), "repairs": []}

    skill_ok, skill_detail = _sr_repair_skill_store()
    result["repairs"].append({"component": "skills", "ok": skill_ok, "detail": skill_detail})
    if not skill_ok:
        result["ok"] = False
        _sr_record("skills", "repair", False, skill_detail)
    elif skill_detail != "healthy":
        _sr_record("skills", "repair", True, skill_detail)

    ollama_ok, ollama_detail = _sr_restart_ollama(force=force)
    result["repairs"].append({"component": "ollama", "ok": ollama_ok, "detail": ollama_detail})
    if not ollama_ok and "circuit breaker" not in ollama_detail:
        result["ok"] = False
        _sr_record("ollama", "restart", False, ollama_detail)
    elif ollama_detail.startswith("restarted"):
        _sr_record("ollama", "restart", True, ollama_detail)

    index_ok, index_detail = _sr_repair_index(force=force)
    result["repairs"].append({"component": "index", "ok": index_ok, "detail": index_detail})
    if not index_ok and "circuit breaker" not in index_detail:
        result["ok"] = False
        _sr_record("index", "repair", False, index_detail)
    elif index_detail.startswith("started"):
        _sr_record("index", "repair", True, index_detail)

    if include_art:
        art_ok, art_detail = _sr_repair_art(force=force)
        result["repairs"].append({"component": "art", "ok": art_ok, "detail": art_detail})
        if not art_ok and "circuit breaker" not in art_detail:
            result["ok"] = False
            _sr_record("art", "restart", False, art_detail)
        elif art_detail.startswith("restarted"):
            _sr_record("art", "restart", True, art_detail)

    result["state"] = _sr_read_state()
    return result


def _sr_supervisor_loop() -> None:
    # Heavy services are already staged during normal startup. Give that sequence
    # time to settle before the repair loop begins checking anything.
    time.sleep(210)
    while True:
        try:
            _sr_run_once(force=False, include_art=True)
        except Exception as exc:
            _sr_record("supervisor", "iteration", False, str(exc))
        time.sleep(SELF_REPAIR_INTERVAL)


def _sr_status() -> dict:
    return {
        "ok": True,
        "node_name": socket.gethostname(),
        "supervisor": True,
        "ollama_healthy": _sr_ollama_healthy(),
        "art_installed": _sr_art_installed(),
        "art_healthy": _art_comfy_health(timeout=0.8) if _sr_art_installed() else None,
        "skills_path": str(_skills_path()),
        "state": _sr_read_state(),
        "policy": "Bounded recovery only: repair state, restart local services, refresh index, preserve user data. No arbitrary self-modifying code.",
    }


'''
text = text.replace(insert_marker, self_repair + insert_marker, 1)

# Start the supervisor beside the existing staged cognition/art/housekeeper threads.
old_threads = '''    threading.Thread(target=warm_cognition, daemon=True, name="VexCognitionWarmup").start()\n    threading.Thread(target=warm_art, daemon=True, name="VexArtWarmup").start()\n    threading.Thread(target=_hk_maintenance_loop, daemon=True, name="VexHousekeeperMaintenance").start()\n'''
new_threads = '''    threading.Thread(target=warm_cognition, daemon=True, name="VexCognitionWarmup").start()\n    threading.Thread(target=warm_art, daemon=True, name="VexArtWarmup").start()\n    threading.Thread(target=_hk_maintenance_loop, daemon=True, name="VexHousekeeperMaintenance").start()\n    threading.Thread(target=_sr_supervisor_loop, daemon=True, name="VexSelfRepairSupervisor").start()\n'''
replace_once(old_threads, new_threads, "self-repair supervisor startup")


# ---------------------------------------------------------------------------
# 3) Add authenticated repair/status endpoints. Existing VexNative does not need
# them for automatic recovery, but they give future app builds and diagnostics a
# clean way to inspect or force a repair pass.
# ---------------------------------------------------------------------------
get_marker = '        if parsed.path == "/maintenance/status":\n'
if get_marker not in text:
    raise SystemExit("maintenance status GET marker missing")
get_addition = r'''        if parsed.path == "/repair/status":
            self._json(200, _sr_status())
            return

'''
text = text.replace(get_marker, get_addition + get_marker, 1)

post_marker = '        if parsed.path == "/maintenance/run":\n'
if post_marker not in text:
    raise SystemExit("maintenance run POST marker missing")
post_addition = r'''        if parsed.path == "/repair/run":
            self._json(200, _sr_run_once(force=True, include_art=True))
            return

'''
text = text.replace(post_marker, post_addition + post_marker, 1)

bridge_path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# 4) Full launcher version bump. Process-level crashes are additionally covered
# by the packaged watchdog script; the in-process supervisor handles normal
# service/config/index failures while VexBridge remains alive.
# ---------------------------------------------------------------------------
full_path = Path("Bridge/vex_bridge_full.py")
full = full_path.read_text(encoding="utf-8")
if 'VERSION = "0.9.6.1"' not in full:
    raise SystemExit("full bridge v0.9.6.1 marker missing")
full = full.replace('VERSION = "0.9.6.1"', 'VERSION = "0.9.6.2"', 1)
full_path.write_text(full, encoding="utf-8")

checks = [
    "def _config_backup", "def _salvage_config", "def _sr_supervisor_loop",
    "def _sr_restart_ollama", "def _sr_repair_art", "def _sr_repair_index",
    'parsed.path == "/repair/status"', 'parsed.path == "/repair/run"',
    "VexSelfRepairSupervisor", "Bounded recovery only",
]
final = bridge_path.read_text(encoding="utf-8")
for marker in checks:
    if marker not in final:
        raise SystemExit(f"missing v0.9.6.2 self-repair marker: {marker}")
if 'VERSION = "0.9.6.2"' not in full_path.read_text(encoding="utf-8"):
    raise SystemExit("missing v0.9.6.2 launcher version")

print("Applied v0.9.6.2 bounded self-healing supervisor + repair endpoints")
