#!/usr/bin/env python3
from pathlib import Path

path = Path("Bridge/vex_bridge.py")
text = path.read_text(encoding="utf-8")


def once(old: str, new: str, label: str):
    global text
    if old not in text:
        raise SystemExit(f"{label}: source block not found")
    text = text.replace(old, new, 1)

helper_marker = "\n\n_BROWSER_CONTROL_LOCK = threading.Lock()"
if helper_marker not in text:
    raise SystemExit("v0.9.1 browser helper marker missing")

art_helpers = r'''

# ---------------------------------------------------------------------------
# Vex Art Engine v0.9.4
# Local ComfyUI only. The phone never talks to ComfyUI directly; the already
# authenticated/pinned Vex Bridge owns the LAN-facing API and proxies results.
# ---------------------------------------------------------------------------
ART_ROOT = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "VexArt"
ART_COMFY_DIR = ART_ROOT / "ComfyUI"
ART_PYTHON = ART_ROOT / "venv" / "Scripts" / "python.exe"
ART_COMFY_BASE = "http://127.0.0.1:8188"
ART_CHECKPOINT = "RealVisXL_V5.0_Lightning_fp16.safetensors"
ART_RENDER_DIR = Path.home() / "Pictures" / "VexRenders"
ART_NEGATIVE = (
    "octane render, CGI, 3d render, drawing, anime, illustration, worst quality, low quality, blurry, "
    "plastic skin, waxy skin, over-smoothed skin, bad teeth, deformed teeth, deformed lips, bad anatomy, "
    "bad proportions, deformed iris, deformed pupils, deformed eyes, bad eyes, deformed face, bad face, "
    "deformed hands, bad hands, fused fingers, extra fingers, missing fingers, mutation, disfigured"
)
_ART_JOB_LOCK = threading.Lock()
_ART_JOBS: dict[str, dict] = {}
_ART_COMFY_PROCESS = None


def _art_comfy_health(timeout: float = 1.5) -> bool:
    try:
        import requests
        response = requests.get(f"{ART_COMFY_BASE}/system_stats", timeout=timeout)
        return response.status_code < 400
    except Exception:
        return False


def _ensure_art_comfy() -> tuple[bool, str | None]:
    global _ART_COMFY_PROCESS
    if _art_comfy_health():
        return True, None
    if not ART_PYTHON.exists() or not (ART_COMFY_DIR / "main.py").exists():
        return False, "Vex Art Engine is not installed on this PC. Run VexArtSetup.ps1 first."
    try:
        import subprocess
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        _ART_COMFY_PROCESS = subprocess.Popen(
            [str(ART_PYTHON), "main.py", "--listen", "127.0.0.1", "--port", "8188", "--disable-auto-launch"],
            cwd=str(ART_COMFY_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
        for _ in range(80):
            time.sleep(0.5)
            if _art_comfy_health(timeout=1.0):
                return True, None
        return False, "ComfyUI did not become ready in time."
    except Exception as exc:
        return False, f"Could not start ComfyUI: {exc}"


def _art_is_stylized(prompt: str) -> bool:
    low = str(prompt or "").lower()
    return any(token in low for token in [
        "anime", "cartoon", "illustration", "drawing", "watercolor", "oil painting", "comic",
        "3d render", "cgi", "pixel art", "sketch", "cel shaded", "manga"
    ])


def _art_clean_request(prompt: str) -> str:
    value = re.sub(r"\s+", " ", str(prompt or "")).strip()
    value = re.sub(
        r"^(?:hey\s+(?:babe|baby|vex)[, ]+)?(?:(?:can|could|would)\s+you\s+)?(?:please\s+)?"
        r"(?:make|generate|create|render|draw)\s+(?:me\s+)?(?:a\s+|an\s+)?(?:picture|pic|photo|image|portrait|render|artwork)\s+(?:of\s+)?",
        "",
        value,
        flags=re.I,
    ).strip()
    return value or str(prompt or "").strip()


def _art_enhance_prompt(raw: str) -> str:
    cleaned = _art_clean_request(raw)
    stylized = _art_is_stylized(cleaned)
    model = _choose_ollama_model()
    if model:
        try:
            import requests
            system = (
                "Rewrite the user's image request into one concise production prompt for a local text-to-image model. "
                "Preserve every requested subject, body trait, clothing detail, pose, setting, camera angle, mood and style. "
                "Do not add people or objects the user did not request. If the request is photographic, emphasize believable optics, "
                "natural skin texture, coherent lighting, realistic materials and an actual-camera look. Output the prompt only."
            )
            response = requests.post(
                f"{OLLAMA_BASE}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": cleaned[:5000]},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.45, "top_p": 0.9, "num_ctx": 4096},
                },
                timeout=35,
            )
            if response.status_code < 400:
                enhanced = _strip_reasoning_markup(str(((response.json().get("message") or {}).get("content")) or ""))
                if enhanced:
                    cleaned = enhanced[:7000]
        except Exception as exc:
            print(f"[art] prompt enhancer fallback: {exc}", flush=True)

    if stylized:
        return cleaned
    realism = (
        "photorealistic RAW photograph, physically believable scene, natural skin texture and pores, "
        "realistic hair strands, realistic fabric and materials, coherent anatomy, accurate hands, lifelike eyes, "
        "natural dynamic range, subtle film grain, physically plausible lighting, realistic depth of field, "
        "high-end full-frame camera photograph, detailed but not overprocessed"
    )
    return f"{cleaned}, {realism}"


def _art_dimensions(orientation: str) -> tuple[int, int]:
    orientation = str(orientation or "portrait").lower().strip()
    if orientation in {"landscape", "horizontal", "wide"}:
        return 1216, 832
    if orientation in {"square", "1:1"}:
        return 1024, 1024
    return 832, 1216


def _art_workflow(prompt: str, orientation: str, seed: int) -> dict:
    width, height = _art_dimensions(orientation)
    negative = "" if _art_is_stylized(prompt) else ART_NEGATIVE
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ART_CHECKPOINT}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {
            "seed": int(seed), "steps": 6, "cfg": 1.6, "sampler_name": "dpmpp_sde",
            "scheduler": "karras", "denoise": 1.0, "model": ["1", 0],
            "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0]
        }},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": "VexRender", "images": ["6", 0]}},
    }


def _art_trim_jobs() -> None:
    with _ART_JOB_LOCK:
        if len(_ART_JOBS) <= 24:
            return
        ordered = sorted(_ART_JOBS.items(), key=lambda item: float(item[1].get("created_at", 0)))
        for job_id, _ in ordered[:-24]:
            _ART_JOBS.pop(job_id, None)


def _art_start_job(raw_prompt: str, orientation: str) -> dict:
    raw_prompt = str(raw_prompt or "").strip()
    if not raw_prompt:
        return {"ok": False, "error": "missing image prompt"}
    job_id = secrets.token_hex(10)
    seed = secrets.randbelow(2_147_483_647)
    width, height = _art_dimensions(orientation)
    job = {
        "id": job_id,
        "status": "queued",
        "raw_prompt": raw_prompt[:7000],
        "orientation": orientation,
        "seed": seed,
        "width": width,
        "height": height,
        "model": ART_CHECKPOINT,
        "created_at": time.time(),
        "error": None,
        "image_path": None,
        "content_type": "image/png",
    }
    with _ART_JOB_LOCK:
        _ART_JOBS[job_id] = job
    threading.Thread(target=_art_run_job, args=(job_id,), daemon=True).start()
    _art_trim_jobs()
    return {"ok": True, "job_id": job_id, "seed": seed, "width": width, "height": height, "model": ART_CHECKPOINT}


def _art_run_job(job_id: str) -> None:
    with _ART_JOB_LOCK:
        job = dict(_ART_JOBS.get(job_id) or {})
        if not job:
            return
        _ART_JOBS[job_id]["status"] = "starting"

    ok, error = _ensure_art_comfy()
    if not ok:
        with _ART_JOB_LOCK:
            _ART_JOBS[job_id]["status"] = "error"
            _ART_JOBS[job_id]["error"] = error
        return

    try:
        import requests
        prompt = _art_enhance_prompt(job["raw_prompt"])
        workflow = _art_workflow(prompt, job["orientation"], int(job["seed"]))
        with _ART_JOB_LOCK:
            _ART_JOBS[job_id]["status"] = "rendering"
            _ART_JOBS[job_id]["effective_prompt"] = prompt

        queued = requests.post(
            f"{ART_COMFY_BASE}/prompt",
            json={"prompt": workflow, "client_id": f"vex-{job_id}"},
            timeout=15,
        )
        queued.raise_for_status()
        prompt_id = str(queued.json().get("prompt_id") or "").strip()
        if not prompt_id:
            raise RuntimeError("ComfyUI did not return a prompt id")

        deadline = time.time() + 420
        image_meta = None
        while time.time() < deadline:
            time.sleep(1.5)
            history = requests.get(f"{ART_COMFY_BASE}/history/{prompt_id}", timeout=10)
            if history.status_code >= 400:
                continue
            payload = history.json()
            record = payload.get(prompt_id) or {}
            outputs = record.get("outputs") or {}
            for output in outputs.values():
                images = output.get("images") or [] if isinstance(output, dict) else []
                if images:
                    image_meta = images[0]
                    break
            if image_meta:
                break
            status = record.get("status") or {}
            if isinstance(status, dict) and status.get("completed") is False and status.get("status_str") == "error":
                raise RuntimeError("ComfyUI reported a render error")
        if not image_meta:
            raise TimeoutError("Image render timed out")

        view = requests.get(
            f"{ART_COMFY_BASE}/view",
            params={
                "filename": image_meta.get("filename", ""),
                "subfolder": image_meta.get("subfolder", ""),
                "type": image_meta.get("type", "output"),
            },
            timeout=30,
        )
        view.raise_for_status()
        data = view.content
        if len(data) < 1000:
            raise RuntimeError("Rendered image was unexpectedly small")

        ART_RENDER_DIR.mkdir(parents=True, exist_ok=True)
        target = ART_RENDER_DIR / f"Vex_{time.strftime('%Y%m%d_%H%M%S')}_{job['seed']}.png"
        target.write_bytes(data)
        with _ART_JOB_LOCK:
            _ART_JOBS[job_id]["status"] = "done"
            _ART_JOBS[job_id]["image_path"] = str(target)
            _ART_JOBS[job_id]["completed_at"] = time.time()
    except Exception as exc:
        print(f"[art] job {job_id} failed: {exc}", flush=True)
        with _ART_JOB_LOCK:
            if job_id in _ART_JOBS:
                _ART_JOBS[job_id]["status"] = "error"
                _ART_JOBS[job_id]["error"] = str(exc)[:1200]


def _art_status(job_id: str) -> dict:
    with _ART_JOB_LOCK:
        job = dict(_ART_JOBS.get(str(job_id or "")) or {})
    if not job:
        return {"ok": False, "error": "unknown art job"}
    return {
        "ok": True,
        "job_id": job.get("id"),
        "status": job.get("status"),
        "error": job.get("error"),
        "seed": job.get("seed"),
        "width": job.get("width"),
        "height": job.get("height"),
        "model": job.get("model"),
    }


def _art_result(job_id: str) -> tuple[bytes, str] | None:
    with _ART_JOB_LOCK:
        job = dict(_ART_JOBS.get(str(job_id or "")) or {})
    if job.get("status") != "done" or not job.get("image_path"):
        return None
    try:
        path = Path(job["image_path"])
        if not path.exists() or path.stat().st_size > 30_000_000:
            return None
        return path.read_bytes(), str(job.get("content_type") or "image/png")
    except Exception:
        return None

'''
text = text.replace(helper_marker, art_helpers + helper_marker, 1)

status_cap = '                "local_cognition_model": _choose_ollama_model(),\n'
status_new = '                "local_cognition_model": _choose_ollama_model(),\n                "local_art_engine": _art_comfy_health(),\n                "local_art_model": ART_CHECKPOINT if (ART_COMFY_DIR / "models" / "checkpoints" / ART_CHECKPOINT).exists() else None,\n'
once(status_cap, status_new, "status art capability")

get_marker = '        if parsed.path == "/llm/status":\n'
get_new = r'''        if parsed.path == "/art/health":
            installed = ART_PYTHON.exists() and (ART_COMFY_DIR / "main.py").exists()
            checkpoint = ART_COMFY_DIR / "models" / "checkpoints" / ART_CHECKPOINT
            self._json(200, {
                "ok": installed and checkpoint.exists(),
                "installed": installed,
                "running": _art_comfy_health(),
                "model": ART_CHECKPOINT if checkpoint.exists() else None,
                "render_dir": str(ART_RENDER_DIR),
            })
            return

        if parsed.path == "/art/status":
            job_id = (params.get("id") or [""])[0].strip()
            self._json(200, _art_status(job_id))
            return

        if parsed.path == "/art/result":
            job_id = (params.get("id") or [""])[0].strip()
            result = _art_result(job_id)
            if result is None:
                self._json(404, {"ok": False, "error": "art result not ready"})
                return
            body, content_type = result
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/llm/status":
'''
once(get_marker, get_new, "art GET routes")

post_marker = '        if parsed.path == "/llm/chat":\n'
post_new = r'''        if parsed.path == "/art/generate":
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length <= 0 or length > 80_000:
                    self._json(413, {"ok": False, "error": "art payload too large"})
                    return
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                prompt = str(payload.get("prompt") or "").strip()
                orientation = str(payload.get("orientation") or "portrait").strip().lower()
                if orientation not in {"portrait", "vertical", "landscape", "horizontal", "wide", "square", "1:1"}:
                    orientation = "portrait"
                result = _art_start_job(prompt, orientation)
                result["node_name"] = STATE.config.get("node_name", "PC") if STATE else "PC"
                self._json(202 if result.get("ok") else 400, result)
            except Exception as exc:
                self._json(500, {"ok": False, "error": f"art request failed: {exc}"})
            return

        if parsed.path == "/llm/chat":
'''
once(post_marker, post_new, "art POST generate route")

path.write_text(text, encoding="utf-8")

full_path = Path("Bridge/vex_bridge_full.py")
full = full_path.read_text(encoding="utf-8")
if 'VERSION = "0.9.3"' not in full:
    raise SystemExit("vex_bridge_full.py: expected v0.9.3 version marker missing")
full = full.replace('VERSION = "0.9.3"', 'VERSION = "0.9.4"', 1)
full_path.write_text(full, encoding="utf-8")

for target, markers in [
    (path, [
        "Vex Art Engine v0.9.4", "_art_start_job", "_art_workflow",
        'parsed.path == "/art/generate"', 'parsed.path == "/art/status"',
        'parsed.path == "/art/result"', "local_art_engine", "RealVisXL_V5.0_Lightning_fp16.safetensors"
    ]),
    (full_path, ['VERSION = "0.9.4"']),
]:
    data = target.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in data:
            raise SystemExit(f"{target}: missing v0.9.4 art marker: {marker}")

print("Applied v0.9.4 authenticated local PC art engine service")
