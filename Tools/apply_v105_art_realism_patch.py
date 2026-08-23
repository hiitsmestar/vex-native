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
if 'VERSION = "0.10.4"' not in text:
    raise SystemExit("VexArtWorker v0.10.4 marker missing")
text = text.replace('VERSION = "0.10.4"', 'VERSION = "0.10.5"', 1)

marker = 'LITE_CHECKPOINT_SHA256 = "e9476a13728cd75d8279f6ec8bad753a66a1957ca375a1464dc63b37db6e3916"\n'
if marker not in text:
    raise SystemExit("lite checkpoint marker missing")
text = text.replace(marker, marker + '''REALISM_CHECKPOINT_NAME = "realismByStableYogi_sd15V9.safetensors"\nREALISM_CHECKPOINT_URL = "https://huggingface.co/Stableyogi/Realism-Checkpoints/resolve/main/realismByStableYogi_sd15V9.safetensors?download=true"\nREALISM_CHECKPOINT_SHA256 = "f592c30e3fde778007bf103d37e5405f3212b73af7be3ed553d7511599555d56"\nREALISM_NEGATIVE = "illustration, anime, cartoon, painting, drawing, 3d render, cgi, large breasts, huge breasts, exaggerated breasts, cropped body, close-up, missing arms, missing hands, missing legs, missing feet, extra limbs, deformed hands, bad anatomy, blurry, low quality, text, watermark, logo"\n''', 1)

helper_marker = '\n\ndef _download_lite_model(progress=None) -> dict:\n'
if helper_marker not in text:
    raise SystemExit("download helper marker missing")
helpers = r'''
def _realism_checkpoint_path() -> Path:
    return CHECKPOINT_DIR / REALISM_CHECKPOINT_NAME


def _realism_model_installed() -> bool:
    p = _realism_checkpoint_path()
    return p.exists() and p.is_file() and p.stat().st_size > 1_900_000_000


def _download_realism_model(progress=None) -> dict:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    target = _realism_checkpoint_path()
    if _realism_model_installed():
        return {"ok": True, "status": "already_installed", "checkpoint": REALISM_CHECKPOINT_NAME}
    temp = target.with_suffix(target.suffix + ".part")
    try:
        with requests.get(REALISM_CHECKPOINT_URL, stream=True, timeout=(30, 300), allow_redirects=True) as response:
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
        if digest != REALISM_CHECKPOINT_SHA256.lower():
            try:
                temp.unlink()
            except Exception:
                pass
            return {"ok": False, "status": "hash_mismatch", "error_class": "ModelIntegrityError", "message": "Downloaded realism model failed SHA256 verification"}
        temp.replace(target)
        return {"ok": True, "status": "installed", "checkpoint": REALISM_CHECKPOINT_NAME, "bytes": target.stat().st_size}
    except Exception as exc:
        try:
            if temp.exists():
                temp.unlink()
        except Exception:
            pass
        return {"ok": False, "status": "download_failed", "error_class": exc.__class__.__name__, "message": str(exc)[:600]}
'''
text = text.replace(helper_marker, '\n\n' + helpers.strip() + helper_marker, 1)

text = text.replace('        "lite_checkpoint": LITE_CHECKPOINT_NAME,\n', '        "lite_checkpoint": LITE_CHECKPOINT_NAME,\n        "realism_model_installed": _realism_model_installed(),\n        "realism_checkpoint": REALISM_CHECKPOINT_NAME,\n', 1)

text = replace_function(text, "_select_checkpoint", r'''def _select_checkpoint(mode: str) -> tuple[str | None, str]:
    if mode != "gpu":
        if _realism_model_installed():
            return REALISM_CHECKPOINT_NAME, "sd15-realism"
        if _lite_model_installed():
            return LITE_CHECKPOINT_NAME, "sd15-lite"
        return None, "lite-model-required"
    return _checkpoint_name(), "sdxl"
''')

text = replace_function(text, "_workflow", r'''def _workflow(prompt: str, checkpoint: str, width: int, height: int, seed: int, steps: int, cfg: float = 6.0, negative: str = NEGATIVE, sampler_name: str = "euler", scheduler: str = "normal") -> dict:
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": steps, "cfg": cfg, "sampler_name": sampler_name, "scheduler": scheduler, "denoise": 1.0, "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0]}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": "VexArtWorker", "images": ["6", 0]}},
    }
''')

old = '''    steps = (4 if test else 8) if model_profile == "sd15-lite" else (3 if test else 5)\n    cfg = 6.0 if model_profile == "sd15-lite" else 1.6\n    _write_stage("loading_model", f"Loading {model_profile} checkpoint", checkpoint=checkpoint, width=width, height=height)\n    workflow = _workflow(prompt, checkpoint, width, height, seed, steps, cfg=cfg)\n'''
new = '''    if model_profile == "sd15-realism":\n        steps = 6 if test else 12\n        cfg = 6.5\n        sampler_name = "dpmpp_2m"\n        scheduler = "karras"\n        negative = REALISM_NEGATIVE\n    elif model_profile == "sd15-lite":\n        steps = 4 if test else 8\n        cfg = 6.0\n        sampler_name = "euler"\n        scheduler = "normal"\n        negative = NEGATIVE\n    else:\n        steps = 3 if test else 5\n        cfg = 1.6\n        sampler_name = "euler"\n        scheduler = "normal"\n        negative = NEGATIVE\n    _write_stage("loading_model", f"Loading {model_profile} checkpoint", checkpoint=checkpoint, width=width, height=height)\n    workflow = _workflow(prompt, checkpoint, width, height, seed, steps, cfg=cfg, negative=negative, sampler_name=sampler_name, scheduler=scheduler)\n'''
if old not in text:
    raise SystemExit("render profile marker missing")
text = text.replace(old, new, 1)

needle = '"stage", "lite_model_installed", "lite_checkpoint"}'
if needle not in text:
    raise SystemExit("sanitized marker missing")
text = text.replace(needle, '"stage", "lite_model_installed", "lite_checkpoint", "realism_model_installed", "realism_checkpoint"}', 1)

btn_marker = '    tk.Button(buttons, text="Stop Worker ComfyUI", command=lambda: status_var.set("Stopped worker-owned ComfyUI" if stop_owned_comfy() else "ComfyUI was not started by this app"), width=19).pack(side="left", padx=4)\n'
if btn_marker not in text:
    raise SystemExit("GUI stop button marker missing")
install_code = r'''    def install_realism() -> None:
        def progress(done: int, total: int) -> None:
            if total > 0:
                pct = int((done * 100) / total)
                root.after(0, lambda p=pct: status_var.set(f"Downloading Realism CPU model... {p}%"))
            else:
                root.after(0, lambda: status_var.set("Downloading Realism CPU model..."))
        def worker() -> None:
            result = _download_realism_model(progress)
            root.after(0, lambda: show_result(result))
            if result.get("ok"):
                root.after(0, lambda: status_var.set("Realism CPU model installed - it will be preferred automatically"))
        threading.Thread(target=worker, daemon=True).start()

'''
text = text.replace(btn_marker, install_code + btn_marker, 1)

lite_button = '    tk.Button(buttons, text="Install Lite Model", command=install_lite, width=17).pack(side="left", padx=4)\n'
if lite_button not in text:
    raise SystemExit("lite install button marker missing")
text = text.replace(lite_button, lite_button + '    tk.Button(prompt_tools, text="Install Realism Model", command=install_realism, width=18).pack(side="left", padx=8)\n', 1)

arg_marker = '    parser.add_argument("--install-lite-model", action="store_true")\n'
if arg_marker not in text:
    raise SystemExit("install lite argparse marker missing")
text = text.replace(arg_marker, arg_marker + '    parser.add_argument("--install-realism-model", action="store_true")\n', 1)
handler = '''    if args.install_lite_model:\n        result = _download_lite_model()\n        _json_print(result)\n        return 0 if result.get("ok") else 2\n'''
if handler not in text:
    raise SystemExit("install lite handler marker missing")
text = text.replace(handler, handler + '''    if args.install_realism_model:\n        result = _download_realism_model()\n        _json_print(result)\n        return 0 if result.get("ok") else 2\n''', 1)

checks = [
    'VERSION = "0.10.5"',
    'REALISM_CHECKPOINT_NAME',
    'f592c30e3fde778007bf103d37e5405f3212b73af7be3ed553d7511599555d56',
    'sd15-realism',
    'dpmpp_2m',
    'Install Realism Model',
]
for check in checks:
    if check not in text:
        raise SystemExit(f"realism patch missing marker: {check}")

path.write_text(text, encoding="utf-8")
print("Applied VexArtWorker v0.10.5 realism model patch")
