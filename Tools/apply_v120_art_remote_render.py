#!/usr/bin/env python3
from pathlib import Path

remote_path = Path("Tools/VexRemoteSupport.py")
worker_path = Path("Tools/VexArtWorker.py")
remote = remote_path.read_text(encoding="utf-8")
worker = worker_path.read_text(encoding="utf-8")

if 'VERSION = "0.11.7.71"' in remote and 'action == "art_render"' in remote and 'VERSION = "0.10.1"' in worker:
    print("v0.12 art remote render patch already applied")
    raise SystemExit(0)

if 'VERSION = "0.11.7.70"' not in remote:
    raise SystemExit("Expected final Remote Support v0.11.7.70 source; run v0.12 foundation assembler first")
if 'def execute_command(command: dict, allow_maintenance: bool) -> dict:' not in remote:
    raise SystemExit("Remote Support execute_command marker missing")
if 'if action == "art_health":' not in remote:
    raise SystemExit("Remote Support art_health marker missing")
if 'VERSION = "0.10.0"' not in worker or 'def render(prompt:' not in worker:
    raise SystemExit("VexArtWorker v0.10.0 markers missing")

# --- VexArtWorker: bounded CPU profile for the field PC + safe render filename return. ---
worker = worker.replace('VERSION = "0.10.0"', 'VERSION = "0.10.1"', 1)

old_dims = '''    if low in {"square", "1:1"}:\n        return (640, 640) if cpu else (1024, 1024)\n    if low in {"landscape", "wide", "horizontal"}:\n        return (768, 512) if cpu else (1216, 832)\n    return (512, 768) if cpu else (832, 1216)\n'''
new_dims = '''    if low in {"square", "1:1"}:\n        return (384, 384) if cpu else (1024, 1024)\n    if low in {"landscape", "wide", "horizontal"}:\n        return (448, 320) if cpu else (1216, 832)\n    return (320, 448) if cpu else (832, 1216)\n'''
if old_dims not in worker:
    raise SystemExit("VexArtWorker dimension marker missing")
worker = worker.replace(old_dims, new_dims, 1)

old_steps = 'workflow = _workflow(prompt, checkpoint, width, height, seed, 4 if test else 6)'
new_steps = 'workflow = _workflow(prompt, checkpoint, width, height, seed, 3 if test else (4 if mode == "cpu" else 6))'
if old_steps not in worker:
    raise SystemExit("VexArtWorker step marker missing")
worker = worker.replace(old_steps, new_steps, 1)

old_result = '"image_path": str(target), "image_bytes": len(data), "elapsed_seconds": round(time.time() - started, 1)'
new_result = '"image_path": str(target), "image_name": target.name, "image_bytes": len(data), "elapsed_seconds": round(time.time() - started, 1)'
if old_result not in worker:
    raise SystemExit("VexArtWorker success-result marker missing")
worker = worker.replace(old_result, new_result, 1)

old_allowed = '"mode", "image_bytes", "elapsed_seconds"}'
new_allowed = '"mode", "image_name", "image_bytes", "elapsed_seconds"}'
if old_allowed not in worker:
    raise SystemExit("VexArtWorker sanitize marker missing")
worker = worker.replace(old_allowed, new_allowed, 1)

# --- Remote Support .71: preserve .70, add only narrow art-worker calls. ---
remote = remote.replace('VERSION = "0.11.7.70"', 'VERSION = "0.11.7.71"', 1)

execute_marker = 'def execute_command(command: dict, allow_maintenance: bool) -> dict:\n'
if 'def art_worker_command(' not in remote:
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
            "mode", "image_name", "image_bytes", "elapsed_seconds",
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
    remote = remote.replace(execute_marker, helper + execute_marker, 1)
else:
    # Existing v100 helper: allow only the new basename field through.
    if '"image_name"' not in remote:
        remote = remote.replace('"mode", "image_bytes", "elapsed_seconds",', '"mode", "image_name", "image_bytes", "elapsed_seconds",', 1)

# Insert after art_health without depending on later command ordering.
art_start = remote.find('    if action == "art_health":')
if art_start < 0:
    raise SystemExit("art_health action not found")
next_action = remote.find('\n    if action == "', art_start + 8)
if next_action < 0:
    raise SystemExit("Could not locate action boundary after art_health")

addition = '''\n    if action == "art_worker_status":\n        return {"art_worker": art_worker_command(["--headless-status"], timeout=240)}\n    if action == "art_render_test":\n        return {"art_worker": art_worker_command(["--render-test"], timeout=1500)}\n    if action == "art_render":\n        prompt = " ".join(str(command.get("prompt") or "").split()).strip()\n        if not prompt or len(prompt) > 1200:\n            return {"ok": False, "error": "art prompt must be 1-1200 characters"}\n        orientation = str(command.get("orientation") or "portrait").strip().lower()\n        aliases = {"1:1": "square", "wide": "landscape", "horizontal": "landscape", "vertical": "portrait"}\n        orientation = aliases.get(orientation, orientation)\n        if orientation not in {"portrait", "landscape", "square"}:\n            return {"ok": False, "error": "orientation must be portrait, landscape, or square"}\n        args = ["--prompt", prompt, "--orientation", orientation]\n        seed = command.get("seed")\n        if seed is not None:\n            try:\n                seed_value = int(seed)\n            except Exception:\n                return {"ok": False, "error": "seed must be a whole number"}\n            if seed_value < 0 or seed_value > 2147483647:\n                return {"ok": False, "error": "seed is out of range"}\n            args += ["--seed", str(seed_value)]\n        return {"art_worker": art_worker_command(args, timeout=1800)}\n'''

# Avoid duplicate insertion if an older art patch already supplied status/test.
if 'action == "art_render"' not in remote:
    if 'action == "art_worker_status"' in remote or 'action == "art_render_test"' in remote:
        # Add just the new render action after the existing test block.
        render_test = remote.find('    if action == "art_render_test":')
        boundary = remote.find('\n    if action == "', render_test + 8)
        only_render = addition[addition.find('    if action == "art_render":'):]
        remote = remote[:boundary] + '\n' + only_render.rstrip() + remote[boundary:]
    else:
        remote = remote[:next_action] + addition.rstrip() + remote[next_action:]

checks = [
    ('remote', remote, 'VERSION = "0.11.7.71"'),
    ('remote', remote, 'def art_worker_command('),
    ('remote', remote, 'action == "art_worker_status"'),
    ('remote', remote, 'action == "art_render_test"'),
    ('remote', remote, 'action == "art_render"'),
    ('remote', remote, '"image_name"'),
    ('worker', worker, 'VERSION = "0.10.1"'),
    ('worker', worker, '"image_name": target.name'),
    ('worker', worker, '(4 if mode == "cpu" else 6)'),
]
for name, text, marker in checks:
    if marker not in text:
        raise SystemExit(f"{name} missing marker: {marker}")

remote_path.write_text(remote, encoding="utf-8")
worker_path.write_text(worker, encoding="utf-8")
print("Applied Remote Support v0.11.7.71 + VexArtWorker v0.10.1 remote-render/low-memory patch")
