#!/usr/bin/env python3
from pathlib import Path
import re

remote_path = Path("Tools/VexRemoteSupport.py")
worker_path = Path("Tools/VexArtWorker.py")
remote = remote_path.read_text(encoding="utf-8")
worker = worker_path.read_text(encoding="utf-8")

if (
    'action == "art_render"' in remote
    and 'V120_ART_REMOTE_RENDER = "v0.12-art-remote-render-v2"' in remote
    and '"image_name"' in remote
    and 'ComfyUI output file escaped output directory' in worker
):
    print("v0.12 art remote render patch already applied")
    raise SystemExit(0)

if 'def execute_command(command: dict, allow_maintenance: bool) -> dict:' not in remote:
    raise SystemExit("Remote Support execute_command marker missing")
if 'if action == "art_health":' not in remote:
    raise SystemExit("Remote Support art_health marker missing")
if 'def render(prompt:' not in worker:
    raise SystemExit("VexArtWorker render marker missing")

# Current v0.12 assembler can generate a newer Remote Support identity than the
# field baseline. Never require/downgrade an exact prior version; stamp this layer
# distinctly while preserving every newer capability underneath it.
remote = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.72"', remote, count=1, flags=re.M)
if 'V120_ART_REMOTE_RENDER = "v0.12-art-remote-render-v2"' not in remote:
    version_line = 'VERSION = "0.11.7.72"\n'
    remote = remote.replace(version_line, version_line + 'V120_ART_REMOTE_RENDER = "v0.12-art-remote-render-v2"\n', 1)

# Keep the worker identity explicit without assuming which historical art patch
# last touched VERSION.
worker = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.12.0-art-remote"', worker, count=1, flags=re.M)

# Bound CPU dimensions only if the historical larger profile is still present.
replacements = {
    'return (640, 640) if cpu else (1024, 1024)': 'return (384, 384) if cpu else (1024, 1024)',
    'return (768, 512) if cpu else (1216, 832)': 'return (448, 320) if cpu else (1216, 832)',
    'return (512, 768) if cpu else (832, 1216)': 'return (320, 448) if cpu else (832, 1216)',
}
for old, new in replacements.items():
    worker = worker.replace(old, new)

# Reduce non-test CPU sampling while preserving any newer GPU behavior.
old_steps = 'workflow = _workflow(prompt, checkpoint, width, height, seed, 4 if test else 6)'
if old_steps in worker:
    worker = worker.replace(old_steps, 'workflow = _workflow(prompt, checkpoint, width, height, seed, 3 if test else (4 if mode == "cpu" else 6))', 1)

# Once ComfyUI reports an output image, it already exists on this same machine.
# Read it directly from ComfyUI/output instead of asking localhost /view to serve
# the file back over HTTP. On the 8 GB CPU field PC that redundant request can
# stall for 60 seconds and turn a successful render into ReadTimeout.
old_view = '''        params = {"filename": str(image_meta.get("filename") or ""), "subfolder": str(image_meta.get("subfolder") or ""), "type": str(image_meta.get("type") or "output")}
        response = requests.get(f"{COMFY_BASE}/view", params=params, timeout=60)
        response.raise_for_status()
        data = response.content
'''
new_view = '''        filename = str(image_meta.get("filename") or "").strip()
        subfolder = str(image_meta.get("subfolder") or "").strip()
        if not filename:
            raise RuntimeError("ComfyUI returned an empty output filename")
        output_root = (COMFY_DIR / "output").resolve()
        source = (output_root / subfolder / filename).resolve()
        try:
            source.relative_to(output_root)
        except ValueError:
            raise RuntimeError("ComfyUI output file escaped output directory")
        if not source.is_file():
            raise FileNotFoundError(f"ComfyUI output image was not found: {filename}")
        data = source.read_bytes()
'''
if old_view in worker:
    worker = worker.replace(old_view, new_view, 1)
elif 'ComfyUI output file escaped output directory' not in worker:
    raise SystemExit("Could not replace localhost /view image fetch")

# Return only a basename over the relay; local full path remains private.
if '"image_name": target.name' not in worker:
    worker = worker.replace('"image_path": str(target), "image_bytes": len(data)', '"image_path": str(target), "image_name": target.name, "image_bytes": len(data)', 1)
if '"image_name"' not in worker.split('def sanitized', 1)[-1]:
    worker = worker.replace('"mode", "image_bytes", "elapsed_seconds"}', '"mode", "image_name", "image_bytes", "elapsed_seconds"}', 1)

execute_marker = 'def execute_command(command: dict, allow_maintenance: bool) -> dict:\n'
if 'def art_worker_path()' not in remote:
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

# Older generated v0.12 source can already contain the art-worker helper from a
# historical patch. In that case, upgrade its relay allowlist in place instead of
# skipping it just because the helper function exists.
helper_start = remote.find('def art_worker_command(')
helper_end = remote.find(execute_marker, helper_start if helper_start >= 0 else 0)
if helper_start < 0 or helper_end < 0:
    raise SystemExit("Remote Support art_worker_command helper missing")
helper_text = remote[helper_start:helper_end]
if '"image_name"' not in helper_text:
    helper_text, changed = re.subn(
        r'("image_bytes"\s*,)',
        r'"image_name", \1',
        helper_text,
        count=1,
    )
    if not changed or '"image_name"' not in helper_text:
        raise SystemExit("Could not add image_name to art relay allowlist")
    remote = remote[:helper_start] + helper_text + remote[helper_end:]

if 'action == "art_render"' not in remote:
    addition = '''    if action == "art_worker_status":\n        return {"art_worker": art_worker_command(["--headless-status"], timeout=240)}\n    if action == "art_render_test":\n        return {"art_worker": art_worker_command(["--render-test"], timeout=1500)}\n    if action == "art_render":\n        prompt = " ".join(str(command.get("prompt") or "").split()).strip()\n        if not prompt or len(prompt) > 1200:\n            return {"ok": False, "error": "art prompt must be 1-1200 characters"}\n        orientation = str(command.get("orientation") or "portrait").strip().lower()\n        aliases = {"1:1": "square", "wide": "landscape", "horizontal": "landscape", "vertical": "portrait"}\n        orientation = aliases.get(orientation, orientation)\n        if orientation not in {"portrait", "landscape", "square"}:\n            return {"ok": False, "error": "orientation must be portrait, landscape, or square"}\n        args = ["--prompt", prompt, "--orientation", orientation]\n        seed = command.get("seed")\n        if seed is not None:\n            try:\n                seed_value = int(seed)\n            except Exception:\n                return {"ok": False, "error": "seed must be a whole number"}\n            if seed_value < 0 or seed_value > 2147483647:\n                return {"ok": False, "error": "seed is out of range"}\n            args += ["--seed", str(seed_value)]\n        return {"art_worker": art_worker_command(args, timeout=1800)}\n'''
    art_start = remote.find('    if action == "art_health":')
    if art_start < 0:
        raise SystemExit("art_health action not found")
    boundary = remote.find('\n    if action == "', art_start + 8)
    if boundary < 0:
        raise SystemExit("Could not locate action boundary after art_health")
    remote = remote[:boundary+1] + addition + remote[boundary+1:]

checks = [
    (remote, 'VERSION = "0.11.7.72"'),
    (remote, 'V120_ART_REMOTE_RENDER = "v0.12-art-remote-render-v2"'),
    (remote, 'def art_worker_command('),
    (remote, 'action == "art_worker_status"'),
    (remote, 'action == "art_render_test"'),
    (remote, 'action == "art_render"'),
    (remote, '"image_name"'),
    (worker, 'VERSION = "0.12.0-art-remote"'),
    (worker, '"image_name": target.name'),
    (worker, 'ComfyUI output file escaped output directory'),
]
for text, marker in checks:
    if marker not in text:
        raise SystemExit(f"art remote patch missing marker: {marker}")

remote_path.write_text(remote, encoding="utf-8")
worker_path.write_text(worker, encoding="utf-8")
compile(remote, str(remote_path), "exec")
compile(worker, str(worker_path), "exec")
print("Applied current-runtime-safe art remote render v2")
