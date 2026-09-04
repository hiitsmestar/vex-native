#!/usr/bin/env python3
from pathlib import Path

remote_path = Path("Tools/VexRemoteSupport.py")
worker_path = Path("Tools/VexArtWorker.py")
remote = remote_path.read_text(encoding="utf-8")
worker = worker_path.read_text(encoding="utf-8")

# This patch is intended to run after the existing v0.10.0 art-remote patch.
if 'VERSION = "0.10.1"' in remote and 'action == "art_render"' in remote and 'VERSION = "0.10.1"' in worker:
    print("v0.10.1 remote art render patch already applied")
    raise SystemExit(0)

if 'VERSION = "0.10.0"' not in remote or 'action == "art_render_test"' not in remote:
    raise SystemExit("Remote Support v0.10.0 art markers missing; apply v100 art remote patch first")
if 'VERSION = "0.10.0"' not in worker or 'def render(prompt:' not in worker:
    raise SystemExit("VexArtWorker v0.10.0 markers missing")

# ---- Art worker: make CPU renders much more realistic for the 8 GB no-GPU field PC. ----
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
    raise SystemExit("VexArtWorker render-result marker missing")
worker = worker.replace(old_result, new_result, 1)

old_allowed = '"mode", "image_bytes", "elapsed_seconds"}'
new_allowed = '"mode", "image_name", "image_bytes", "elapsed_seconds"}'
if old_allowed not in worker:
    raise SystemExit("VexArtWorker sanitize marker missing")
worker = worker.replace(old_allowed, new_allowed, 1)

# ---- Remote support: narrow render command only; no shell or arbitrary paths. ----
remote = remote.replace('VERSION = "0.10.0"', 'VERSION = "0.10.1"', 1)
remote = remote.replace('"mode", "image_bytes", "elapsed_seconds",', '"mode", "image_name", "image_bytes", "elapsed_seconds",', 1)

needle = '''    if action == "art_render_test":\n        return {"art_worker": art_worker_command(["--render-test"], timeout=1500)}\n'''
if needle not in remote:
    raise SystemExit("Remote art_render_test marker missing")
replacement = needle + '''    if action == "art_render":\n        prompt = " ".join(str(command.get("prompt") or "").split()).strip()\n        if not prompt or len(prompt) > 1200:\n            return {"ok": False, "error": "art prompt must be 1-1200 characters"}\n        orientation = str(command.get("orientation") or "portrait").strip().lower()\n        aliases = {"1:1": "square", "wide": "landscape", "horizontal": "landscape", "vertical": "portrait"}\n        orientation = aliases.get(orientation, orientation)\n        if orientation not in {"portrait", "landscape", "square"}:\n            return {"ok": False, "error": "orientation must be portrait, landscape, or square"}\n        args = ["--prompt", prompt, "--orientation", orientation]\n        seed = command.get("seed")\n        if seed is not None:\n            try:\n                seed_value = int(seed)\n            except Exception:\n                return {"ok": False, "error": "seed must be a whole number"}\n            if seed_value < 0 or seed_value > 2147483647:\n                return {"ok": False, "error": "seed is out of range"}\n            args += ["--seed", str(seed_value)]\n        return {"art_worker": art_worker_command(args, timeout=1800)}\n'''
remote = remote.replace(needle, replacement, 1)

notify_old = '        "art_render_test": "art render test",\n'
if notify_old not in remote:
    raise SystemExit("Remote notify art_render_test marker missing")
remote = remote.replace(notify_old, notify_old + '        "art_render": "art render",\n', 1)

checks = [
    ('remote', remote, 'VERSION = "0.10.1"'),
    ('remote', remote, 'action == "art_render"'),
    ('remote', remote, '"image_name"'),
    ('worker', worker, 'VERSION = "0.10.1"'),
    ('worker', worker, '"image_name": target.name'),
    ('worker', worker, '(4 if mode == "cpu" else 6)'),
]
for name, text, marker in checks:
    if marker not in text:
        raise SystemExit(f"{name} missing v0.10.1 marker: {marker}")

remote_path.write_text(remote, encoding="utf-8")
worker_path.write_text(worker, encoding="utf-8")
print("Applied Vex Art/Remote Support v0.10.1 bounded remote render + CPU low-memory patch")
