#!/usr/bin/env python3
from pathlib import Path

path = Path("Tools/VexRemoteSupport.py")
text = path.read_text(encoding="utf-8")

if 'VERSION = "0.10.0"' in text and 'art_render_test' in text:
    print("v0.10.0 art remote patch already applied")
    raise SystemExit(0)
if 'VERSION = "0.9.9.2"' not in text:
    raise SystemExit("v0.9.9.2 Remote Support marker missing")
text = text.replace('VERSION = "0.9.9.2"', 'VERSION = "0.10.0"', 1)

marker = 'def execute_command(command: dict, allow_maintenance: bool) -> dict:\n'
if marker not in text:
    raise SystemExit("execute_command marker missing")
helper = r'''def art_worker_path() -> Path | None:
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent
    candidates = [base / "VexArtWorker.exe", base / "dist" / "VexArtWorker.exe"]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def art_worker_command(args: list[str], timeout: int) -> dict:
    worker = art_worker_path()
    if not worker:
        return {"ok": False, "error": "VexArtWorker.exe is not installed beside Remote Support"}
    try:
        result = run_quiet([str(worker), *args], timeout=timeout)
        payload = {}
        for line in reversed([x.strip() for x in (result.stdout or "").splitlines() if x.strip()]):
            if line.startswith("{"):
                try:
                    value = json.loads(line)
                    if isinstance(value, dict):
                        payload = value
                        break
                except Exception:
                    pass
        allowed = {
            "ok", "status", "installed", "python_exists", "comfy_exists", "checkpoint", "checkpoint_exists",
            "comfy_reachable", "error_class", "node_id", "node_type", "message", "width", "height", "seed",
            "mode", "image_bytes", "elapsed_seconds",
        }
        clean = {str(k): v for k, v in payload.items() if k in allowed}
        clean.setdefault("ok", result.returncode == 0)
        clean["exit_code"] = int(result.returncode)
        if not payload and result.returncode != 0:
            clean["error"] = "art worker returned no structured result"
        return clean
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "art worker timed out"}
    except Exception as exc:
        return {"ok": False, "error": exc.__class__.__name__}


'''
text = text.replace(marker, helper + marker, 1)

needle = '''    if action == "art_health":\n        a = bridge_get("/art/health")\n        return {"art": {"ok": yes(a.get("ok")), "installed": yes(a.get("installed")), "running": yes(a.get("running")), "model": model_label(a.get("model"))}}\n'''
if needle not in text:
    raise SystemExit("art_health command marker missing")
replacement = needle + '''    if action == "art_worker_status":\n        return {"art_worker": art_worker_command(["--headless-status"], timeout=240)}\n    if action == "art_render_test":\n        return {"art_worker": art_worker_command(["--render-test"], timeout=1500)}\n'''
text = text.replace(needle, replacement, 1)

notify_old = '''        "art_health": "art-engine check",\n'''
if notify_old not in text:
    raise SystemExit("notify art marker missing")
text = text.replace(notify_old, notify_old + '''        "art_worker_status": "art-worker check",\n        "art_render_test": "art render test",\n''', 1)

# An art-worker result wraps the actual status one level down; teach notification
# severity detection to look there without publishing any additional details.
attention_old = '''        doctor = result.get("doctor")\n        if isinstance(doctor, dict) and str(doctor.get("overall") or "").lower() not in {"", "healthy", "ok"}:\n            attention = True\n'''
if attention_old not in text:
    raise SystemExit("notify attention marker missing")
attention_new = attention_old + '''        art_worker = result.get("art_worker")\n        if isinstance(art_worker, dict) and art_worker.get("ok") is False:\n            attention = True\n'''
text = text.replace(attention_old, attention_new, 1)

checks = [
    'VERSION = "0.10.0"',
    'def art_worker_path()',
    'def art_worker_command(',
    'action == "art_worker_status"',
    'action == "art_render_test"',
    '"art_render_test": "art render test"',
]
for check in checks:
    if check not in text:
        raise SystemExit(f"v0.10.0 missing marker: {check}")

path.write_text(text, encoding="utf-8")
print("Applied Vex Remote Support v0.10.0 art-worker relay patch")
