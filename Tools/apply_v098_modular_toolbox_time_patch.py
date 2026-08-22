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
# v0.9.8 modular toolbox + deterministic diagnostics + real clock grounding.
#
# The core architectural rule is deliberately boring and useful:
# - keep Bridge/routing/auth/time/knowledge lightweight and always available
# - keep heavy/specialized tools in separate executables/services
# - invoke tools through a small whitelist instead of arbitrary shell execution
# - let tools fail/repair independently without corrupting conversation cognition
# ---------------------------------------------------------------------------

handler_marker = "\n\nclass Handler(BaseHTTPRequestHandler):\n"
if handler_marker not in text:
    raise SystemExit("Bridge Handler marker missing")

helpers = r'''

TIME_STATE_PATH = CONFIG_PATH.parent / "time-state.json"
_TIME_STATE_LOCK = threading.Lock()
TOOL_MANIFEST_NAME = "VexToolManifest.json"


def _system_time_snapshot(mark_interaction: bool = False) -> dict:
    """Return host-OS time and, for cognition turns, real elapsed time since the prior turn."""
    from datetime import datetime

    now_epoch = time.time()
    now = datetime.now().astimezone()
    previous = None
    with _TIME_STATE_LOCK:
        try:
            if TIME_STATE_PATH.exists():
                state = json.loads(TIME_STATE_PATH.read_text("utf-8"))
                previous = float(state.get("last_pc_cognition_epoch") or 0) or None
        except Exception:
            previous = None
        if mark_interaction:
            try:
                TIME_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
                TIME_STATE_PATH.write_text(
                    json.dumps({
                        "last_pc_cognition_epoch": now_epoch,
                        "last_pc_cognition_iso": now.isoformat(timespec="seconds"),
                    }, indent=2),
                    "utf-8",
                )
            except Exception:
                pass

    elapsed = None
    if previous is not None and 0 <= now_epoch - previous < 3650 * 86400:
        elapsed = round(now_epoch - previous, 3)

    bridge_uptime = None
    try:
        if STATE is not None:
            bridge_uptime = max(0, int(now_epoch - STATE.started))
    except Exception:
        pass

    return {
        "iso": now.isoformat(timespec="seconds"),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": now.strftime("%A"),
        "timezone": now.tzname() or "local",
        "utc_offset": now.strftime("%z"),
        "unix_seconds": now_epoch,
        "seconds_since_previous_pc_cognition_turn": elapsed,
        "bridge_uptime_seconds": bridge_uptime,
        "source": "host operating-system clock",
    }


def _system_time_prompt(mark_interaction: bool = True) -> str:
    snap = _system_time_snapshot(mark_interaction=mark_interaction)
    elapsed = snap.get("seconds_since_previous_pc_cognition_turn")
    elapsed_text = "unknown/no previous PC cognition turn"
    if elapsed is not None:
        elapsed_text = f"{elapsed:.3f} seconds"
    return (
        "AUTHORITATIVE LOCAL TIME — supplied by the host operating-system clock, not guessed by the model:\n"
        f"Current local datetime: {snap['iso']} ({snap['weekday']}, {snap['timezone']}, UTC offset {snap['utc_offset']}).\n"
        f"Unix time: {snap['unix_seconds']:.3f}. Time since the previous PC cognition turn: {elapsed_text}.\n"
        "Use this clock for today/tonight/yesterday/tomorrow and elapsed-time reasoning. "
        "When an event has a stored timestamp, compare real timestamps. Never invent a date, duration, or passage of time that the clock/history does not support."
    )


def _tool_runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _tool_manifest_path() -> Path | None:
    root = _tool_runtime_root()
    for candidate in [root / TOOL_MANIFEST_NAME, root / "Tools" / TOOL_MANIFEST_NAME]:
        if candidate.exists():
            return candidate
    return None


def _tool_manifest() -> dict:
    path = _tool_manifest_path()
    if path is None:
        return {"schema": 1, "version": "0.9.8", "tools": []}
    try:
        payload = json.loads(path.read_text("utf-8"))
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    return {"schema": 1, "version": "0.9.8", "tools": []}


def _expand_tool_path(value: str) -> Path:
    return Path(os.path.expandvars(str(value or ""))).expanduser()


def _tool_status() -> dict:
    manifest = _tool_manifest()
    root = _tool_runtime_root()
    entries = []
    for item in manifest.get("tools") or []:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        executable = str(item.get("executable") or "").strip()
        install_root = str(item.get("install_root") or "").strip()
        if executable:
            row["available"] = (root / executable).exists()
            row["resolved_path"] = str(root / executable)
        elif install_root:
            resolved = _expand_tool_path(install_root)
            row["available"] = resolved.exists()
            row["resolved_path"] = str(resolved)
        else:
            row["available"] = bool(item.get("external"))
        entries.append(row)
    return {
        "ok": True,
        "version": str(manifest.get("version") or "0.9.8"),
        "runtime_root": str(root),
        "tools": entries,
        "policy": "Only known packaged/on-demand tools are brokered. Arbitrary executables from request text are never launched.",
    }


def _diagnostic_report_path() -> Path:
    path = CONFIG_PATH.parent / "diagnostics" / "bridge-latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _diagnostics_latest() -> dict:
    path = _diagnostic_report_path()
    if not path.exists():
        return {"ok": False, "available": False, "error": "No Vex Doctor report has been run yet", "path": str(path)}
    try:
        payload = json.loads(path.read_text("utf-8"))
        return {"ok": True, "available": True, "path": str(path), "report": payload}
    except Exception as exc:
        return {"ok": False, "available": True, "path": str(path), "error": str(exc)}


def _run_vex_doctor(deep: bool = False) -> dict:
    """Run the separately packaged doctor. No model output participates in diagnosis."""
    import subprocess

    root = _tool_runtime_root()
    exe = root / "VexDoctor.exe"
    source = root / "Tools" / "VexDoctor.py"
    output = _diagnostic_report_path()
    if exe.exists():
        command = [str(exe), "--headless", "--json-out", str(output)]
    elif source.exists():
        command = [sys.executable, str(source), "--headless", "--json-out", str(output)]
    else:
        return {"ok": False, "error": "VexDoctor is not installed beside this Bridge", "tool_status": _tool_status()}
    if deep:
        command.append("--deep")
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.run(
            command,
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=520 if deep else 120,
            creationflags=flags,
        )
        latest = _diagnostics_latest()
        return {
            "ok": bool(latest.get("ok")),
            "tool": "VexDoctor",
            "deep": bool(deep),
            "exit_code": int(proc.returncode),
            "tool_output": str(proc.stdout or "").strip()[-4000:],
            "diagnostic": latest,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "tool": "VexDoctor", "deep": bool(deep), "error": "Vex Doctor timed out"}
    except Exception as exc:
        return {"ok": False, "tool": "VexDoctor", "deep": bool(deep), "error": str(exc)}

'''
text = text.replace(handler_marker, helpers + handler_marker, 1)

# Inject the real host clock into every PC cognition call. Retained memory can
# still say *what* happened; the clock is authoritative about *when it is now*.
time_inject_old = '    safe_messages = [{"role": "system", "content": system_text}]\n'
time_inject_new = '''    system_text += "\\n\\n" + _system_time_prompt(mark_interaction=True)\n    safe_messages = [{"role": "system", "content": system_text}]\n'''
replace_once(time_inject_old, time_inject_new, "PC cognition time grounding")

# Deterministic GET endpoints. These are protected by the same Bridge token as
# every other endpoint and report machine state without asking the language model.
get_marker = '        if parsed.path == "/learning/status":\n'
get_add = '''        if parsed.path == "/system/time":\n            self._json(200, {"ok": True, "clock": _system_time_snapshot(mark_interaction=False)})\n            return\n\n        if parsed.path == "/tools/list":\n            self._json(200, _tool_status())\n            return\n\n        if parsed.path == "/diagnostics/latest":\n            self._json(200, _diagnostics_latest())\n            return\n\n'''
replace_once(get_marker, get_add + get_marker, "time/tool/diagnostic GET routes")

# Vex may invoke the doctor through Bridge, but only this whitelisted packaged
# tool is accepted here. No arbitrary command/executable text crosses this API.
post_marker = '        if parsed.path == "/learning/run":\n'
post_add = r'''        if parsed.path == "/diagnostics/run":
            deep = False
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length > 0:
                    if length > 20_000:
                        self._json(413, {"ok": False, "error": "diagnostic payload too large"})
                        return
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    deep = bool(payload.get("deep", False)) if isinstance(payload, dict) else False
            except Exception:
                deep = False
            result = _run_vex_doctor(deep=deep)
            self._json(200 if result.get("ok") else 503, result)
            return

'''
replace_once(post_marker, post_add + post_marker, "diagnostic POST route")

bridge_path.write_text(text, encoding="utf-8")

full_path = Path("Bridge/vex_bridge_full.py")
full = full_path.read_text(encoding="utf-8")
if 'VERSION = "0.9.7.3"' not in full:
    raise SystemExit("v0.9.7.3 launcher marker missing")
full = full.replace('VERSION = "0.9.7.3"', 'VERSION = "0.9.8"', 1)
full_path.write_text(full, encoding="utf-8")

checks = [
    "def _system_time_snapshot",
    "def _system_time_prompt",
    "def _tool_status",
    "def _run_vex_doctor",
    'parsed.path == "/system/time"',
    'parsed.path == "/tools/list"',
    'parsed.path == "/diagnostics/run"',
    "AUTHORITATIVE LOCAL TIME",
]
final = bridge_path.read_text(encoding="utf-8")
for check in checks:
    if check not in final:
        raise SystemExit(f"v0.9.8 missing marker: {check}")
if 'VERSION = "0.9.8"' not in full_path.read_text(encoding="utf-8"):
    raise SystemExit("v0.9.8 launcher version missing")

print("Applied Vex v0.9.8 modular toolbox + diagnostics + real-time grounding patch")
