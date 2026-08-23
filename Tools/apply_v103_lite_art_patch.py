#!/usr/bin/env python3
from pathlib import Path


def replace_function(text: str, name: str, replacement: str) -> str:
    start = text.find(f"def {name}(")
    if start < 0:
        raise SystemExit(f"missing function: {name}")
    end = text.find("\n\ndef ", start + 10)
    if end < 0:
        raise SystemExit(f"could not find end of function: {name}")
    return text[:start] + replacement.rstrip() + text[end:]


path = Path("Tools/VexArtWorker.py")
text = path.read_text(encoding="utf-8")
if 'VERSION = "0.10.2"' not in text:
    raise SystemExit("v0.10.2 Art Worker marker missing")
text = text.replace('VERSION = "0.10.2"', 'VERSION = "0.10.3"', 1)

# Free, local, CPU-friendlier SD1.5 checkpoint. The URL is from Comfy-Org's
# Stable Diffusion 1.5 archive and is verified against the published SHA256.
const_marker = 'CHECKPOINT_NAME = "RealVisXL_V5.0_Lightning_fp16.safetensors"\n'
if const_marker not in text:
    raise SystemExit("checkpoint constant marker missing")
text = text.replace(const_marker, const_marker + '''LITE_CHECKPOINT_NAME = "v1-5-pruned-emaonly-fp16.safetensors"\nLITE_CHECKPOINT_URL = "https://huggingface.co/Comfy-Org/stable-diffusion-v1-5-archive/resolve/main/v1-5-pruned-emaonly-fp16.safetensors?download=true"\nLITE_CHECKPOINT_SHA256 = "e9476a13728cd75d8279f6ec8bad753a66a1957ca375a1464dc63b37db6e3916"\n''', 1)

# imports for download/hash
text = text.replace('import argparse\n', 'import argparse\nimport hashlib\n', 1)

helper_marker = '\n\ndef _checkpoint_name() -> str | None:\n'
if helper_marker not in text:
    raise SystemExit("checkpoint helper marker missing")
helpers = r'''
def _lite_checkpoint_path() -> Path:
    return CHECKPOINT_DIR / LITE_CHECKPOINT_NAME


def _lite_model_installed() -> bool:
    p = _lite_checkpoint_path()
    return p.exists() and p.is_file() and p.stat().st_size > 1_500_000_000


def _write_stage(stage: str, message: str = "", **extra) -> None:
    payload = {
        "ok": True,
        "status": "running",
        "stage": str(stage),
        "message": str(message or "")[:500],
        "time": time.time(),
    }
    payload.update(extra)
    _write_report(payload)


def _quick_status() -> dict:
    state = installed_state()
    memory = _memory_profile()
    result = {
        "ok": bool(state.get("installed")),
        "status": "idle",
        "installed": bool(state.get("installed")),
        "comfy_reachable": bool(state.get("comfy_reachable")),
        "lite_model_installed": _lite_model_installed(),
        "lite_checkpoint": LITE_CHECKPOINT_NAME,
        "mode": "cpu-lite" if memory.get("low_memory") else "auto",
        "memory_total_mb": memory.get("total_physical_mb"),
        "memory_available_mb": memory.get("available_physical_mb"),
        "commit_total_mb": memory.get("total_commit_mb"),
        "commit_available_mb": memory.get("available_commit_mb"),
        "low_memory": memory.get("low_memory"),
    }
    try:
        prior = json.loads(REPORT_PATH.read_text("utf-8")) if REPORT_PATH.exists() else {}
        if isinstance(prior, dict) and prior.get("status") == "running":
            result["status"] = "running"
            result["stage"] = str(prior.get("stage") or "working")
            result["message"] = str(prior.get("message") or "")[:500]
    except Exception:
        pass
    return result


def _download_lite_model(progress=None) -> dict:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    target = _lite_checkpoint_path()
    if _lite_model_installed():
        return {"ok": True, "status": "already_installed", "checkpoint": LITE_CHECKPOINT_NAME}
    temp = target.with_suffix(target.suffix + ".part")
    try:
        with requests.get(LITE_CHECKPOINT_URL, stream=True, timeout=(30, 300), allow_redirects=True) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length") or 0)
            done = 0
            sha = hashlib.sha256()
            with open(temp, "wb") as f:
                for chunk in response.iter_content(chunk_size=8 * 1024 * 1024):
                    if not chunk:
                        continue
                    f.write(chunk)
                    sha.update(chunk)
                    done += len(chunk)
                    if progress:
                        try:
                            progress(done, total)
                        except Exception:
                            pass
        digest = sha.hexdigest().lower()
        if digest != LITE_CHECKPOINT_SHA256.lower():
            try:
                temp.unlink()
            except Exception:
                pass
            return {"ok": False, "status": "hash_mismatch", "error_class": "ModelIntegrityError", "message": "Downloaded lite model failed SHA256 verification"}
        temp.replace(target)
        return {"ok": True, "status": "installed", "checkpoint": LITE_CHECKPOINT_NAME, "bytes": target.stat().st_size}
    except Exception as exc:
        try:
            if temp.exists():
                temp.unlink()
        except Exception:
            pass
        return {"ok": False, "status": "download_failed", "error_class": exc.__class__.__name__, "message": str(exc)[:600]}
'''
text = text.replace(helper_marker, '\n\n' + helpers.strip() + helper_marker, 1)

# On weak CPU hardware, never fall back to the SDXL checkpoint. Require the
# smaller model first so a render has a realistic chance of completing.
select_marker = '\n\ndef _dimensions(orientation: str, mode: str, test: bool) -> tuple[int, int]:\n'
if select_marker not in text:
    raise SystemExit("dimensions marker missing")
selector = r'''
def _select_checkpoint(mode: str) -> tuple[str | None, str]:
    if mode != "gpu":
        if _lite_model_installed():
            return LITE_CHECKPOINT_NAME, "sd15-lite"
        return None, "lite-model-required"
    return _checkpoint_name(), "sdxl"
'''
text = text.replace(select_marker, '\n\n' + selector.strip() + select_marker, 1)

text = replace_function(text, "_dimensions", r'''def _dimensions(orientation: str, mode: str, test: bool) -> tuple[int, int]:
    cpu = mode != "gpu"
    if test:
        return (320, 320) if cpu else (512, 512)
    low = str(orientation or "portrait").lower()
    if low in {"square", "1:1"}:
        return (384, 384) if cpu else (1024, 1024)
    if low in {"landscape", "wide", "horizontal"}:
        return (512, 320) if cpu else (1216, 832)
    return (320, 512) if cpu else (832, 1216)
''')

text = replace_function(text, "_workflow", r'''def _workflow(prompt: str, checkpoint: str, width: int, height: int, seed: int, steps: int, cfg: float = 6.0) -> dict:
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": NEGATIVE, "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": steps, "cfg": cfg, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0, "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0]}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": "VexArtWorker", "images": ["6", 0]}},
    }
''')

# Patch render flow: report cheap progress, select SD1.5 on CPU, and refuse SDXL
# on the 8 GB node when the lite model is not installed.
old = '''    ok, launch = ensure_comfy()\n    if not ok:\n'''
new = '''    _write_stage("starting", "Starting local art engine")\n    ok, launch = ensure_comfy()\n    if not ok:\n'''
if old not in text:
    raise SystemExit("render ensure marker missing")
text = text.replace(old, new, 1)
old = '''    checkpoint = _checkpoint_name()\n    if not checkpoint:\n        result = {"ok": False, "status": "missing_checkpoint", "error_class": "CheckpointError", "message": "No checkpoint was found"}\n        _write_report(result)\n        _BUSY = False\n        _LAST_ACTIVITY = time.time()\n        return result\n    mode = str(launch.get("mode") or "existing")\n    if mode == "existing":\n        probe = _torch_probe()\n        mode = "gpu" if probe.get("ok") and probe.get("cuda") else "cpu"\n    width, height = _dimensions(orientation, mode, test)\n    seed = int(seed if seed is not None else random.randint(1, 2_147_483_647))\n    workflow = _workflow(prompt, checkpoint, width, height, seed, 3 if test else 5)\n'''
new = '''    mode = str(launch.get("mode") or "cpu-lowmem")\n    if mode == "worker-owned":\n        mode = "cpu-lowmem"\n    checkpoint, model_profile = _select_checkpoint(mode)\n    if not checkpoint:\n        result = {"ok": False, "status": "lite_model_required", "error_class": "LiteModelRequired", "message": "Install the free Lite CPU model in Vex Art Worker before rendering on this CPU-only node."}\n        _write_report(result)\n        _BUSY = False\n        _LAST_ACTIVITY = time.time()\n        return result\n    width, height = _dimensions(orientation, mode, test)\n    seed = int(seed if seed is not None else random.randint(1, 2_147_483_647))\n    steps = (4 if test else 8) if model_profile == "sd15-lite" else (3 if test else 5)\n    cfg = 6.0 if model_profile == "sd15-lite" else 1.6\n    _write_stage("loading_model", f"Loading {model_profile} checkpoint", checkpoint=checkpoint, width=width, height=height)\n    workflow = _workflow(prompt, checkpoint, width, height, seed, steps, cfg=cfg)\n'''
if old not in text:
    raise SystemExit("render checkpoint block marker missing")
text = text.replace(old, new, 1)
text = text.replace('        status_code, queued = _http_json("POST", "/prompt", json_body={"prompt": workflow, "client_id": f"vexart-{seed}"}, timeout=30)\n', '        status_code, queued = _http_json("POST", "/prompt", json_body={"prompt": workflow, "client_id": f"vexart-{seed}"}, timeout=30)\n        _write_stage("sampling", "ComfyUI accepted the workflow; sampling", checkpoint=checkpoint, width=width, height=height)\n', 1)
text = text.replace('        target.write_bytes(data)\n', '        _write_stage("saving", "Saving completed render")\n        target.write_bytes(data)\n', 1)

# Make sanitized status include new lightweight/progress keys.
needle = '"memory_total_mb", "memory_available_mb", "commit_total_mb", "commit_available_mb", "low_memory"}'
if needle not in text:
    raise SystemExit("sanitized keys marker missing")
text = text.replace(needle, '"memory_total_mb", "memory_available_mb", "commit_total_mb", "commit_available_mb", "low_memory", "stage", "lite_model_installed", "lite_checkpoint"}', 1)

# Add GUI install button and background progress.
btn_marker = '    tk.Button(buttons, text="Stop Worker ComfyUI", command=lambda: status_var.set("Stopped worker-owned ComfyUI" if stop_owned_comfy() else "ComfyUI was not started by this app"), width=19).pack(side="left", padx=4)\n'
if btn_marker not in text:
    raise SystemExit("GUI button marker missing")
install_code = r'''    def install_lite() -> None:
        def progress(done: int, total: int) -> None:
            if total > 0:
                pct = int((done * 100) / total)
                root.after(0, lambda p=pct: status_var.set(f"Downloading Lite CPU model... {p}%"))
            else:
                root.after(0, lambda: status_var.set("Downloading Lite CPU model..."))
        def worker() -> None:
            result = _download_lite_model(progress)
            root.after(0, lambda: show_result(result))
            if result.get("ok"):
                root.after(0, lambda: status_var.set("Lite CPU model installed - ready to render"))
        threading.Thread(target=worker, daemon=True).start()

'''
text = text.replace(btn_marker, install_code + btn_marker + '    tk.Button(buttons, text="Install Lite Model", command=install_lite, width=17).pack(side="left", padx=4)\n', 1)

# Quick status avoids loading torch just to monitor a render.
main_marker = '    parser.add_argument("--headless-status", action="store_true")\n'
if main_marker not in text:
    raise SystemExit("argparse marker missing")
text = text.replace(main_marker, main_marker + '    parser.add_argument("--quick-status", action="store_true")\n    parser.add_argument("--install-lite-model", action="store_true")\n', 1)
main_if = '    if args.headless_status:\n        _json_print(headless_status())\n        return 0\n'
if main_if not in text:
    raise SystemExit("headless main marker missing")
text = text.replace(main_if, '    if args.quick_status:\n        _json_print(_quick_status())\n        return 0\n    if args.install_lite_model:\n        result = _download_lite_model()\n        _json_print(result)\n        return 0 if result.get("ok") else 2\n' + main_if, 1)

path.write_text(text, encoding="utf-8")

# Remote Support: monitor with --quick-status so it does not import torch while a
# render is already stressing the CPU/RAM.
rp = Path("Tools/VexRemoteSupport.py")
remote = rp.read_text(encoding="utf-8")
if 'VERSION = "0.10.0"' not in remote:
    raise SystemExit("Remote Support v0.10.0 marker missing")
remote = remote.replace('VERSION = "0.10.0"', 'VERSION = "0.10.3"', 1)
remote = remote.replace('return {"art_worker": art_worker_command(["--headless-status"], timeout=240)}', 'return {"art_worker": art_worker_command(["--quick-status"], timeout=45)}', 1)
remote = remote.replace('"mode", "image_bytes", "elapsed_seconds",', '"mode", "image_bytes", "elapsed_seconds", "stage", "lite_model_installed", "lite_checkpoint",', 1)
rp.write_text(remote, encoding="utf-8")

# Bridge compatibility label only; modular art ownership remains v0.10.2 logic.
bp = Path("Bridge/vex_bridge.py")
bridge = bp.read_text(encoding="utf-8").replace('"version": "0.10.2"', '"version": "0.10.3"')
bp.write_text(bridge, encoding="utf-8")
fp = Path("Bridge/vex_bridge_full.py")
full = fp.read_text(encoding="utf-8").replace('VERSION = "0.10.2"', 'VERSION = "0.10.3"', 1)
fp.write_text(full, encoding="utf-8")

checks = [
    'VERSION = "0.10.3"', 'LITE_CHECKPOINT_NAME', 'LITE_CHECKPOINT_SHA256',
    'def _download_lite_model(', 'def _quick_status(', 'LiteModelRequired',
    'Install Lite Model', '"--quick-status"', 'model_profile == "sd15-lite"',
]
final = path.read_text(encoding="utf-8")
for marker in checks:
    if marker not in final:
        raise SystemExit(f"v0.10.3 worker missing marker: {marker}")
if 'VERSION = "0.10.3"' not in rp.read_text(encoding="utf-8"):
    raise SystemExit("v0.10.3 Remote Support version missing")
print("Applied v0.10.3 lightweight CPU art model + cheap progress telemetry patch")
