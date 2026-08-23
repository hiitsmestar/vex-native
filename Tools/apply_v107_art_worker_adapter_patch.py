#!/usr/bin/env python3
from pathlib import Path
import json


def replace_function(text: str, name: str, replacement: str) -> str:
    start = text.find(f"def {name}(")
    if start < 0:
        raise SystemExit(f"missing function: {name}")
    end = text.find("\n\ndef ", start + 10)
    if end < 0:
        raise SystemExit(f"could not find end of function: {name}")
    return text[:start] + replacement.rstrip() + text[end:]


# ---------------------------------------------------------------------------
# VexBridge: preserve the existing /art/generate -> /art/status -> /art/result
# contract used by iOS, but move ALL actual rendering ownership to the standalone
# VexArtWorker.exe. Bridge becomes a broker only.
# ---------------------------------------------------------------------------
bridge_path = Path("Bridge/vex_bridge.py")
text = bridge_path.read_text(encoding="utf-8")

worker_helpers = r'''
_ART_WORKER_PROCESS_LOCK = threading.Lock()


def _art_worker_candidates() -> list[Path]:
    values: list[Path] = []
    configured = str(os.environ.get("VEX_ART_WORKER_EXE", "") or "").strip()
    if configured:
        values.append(Path(configured).expanduser())
    try:
        import sys
        values.append(Path(sys.executable).resolve().parent / "VexArtWorker.exe")
    except Exception:
        pass
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    values.append(local / "VexArt" / "VexArtWorker.exe")
    # Development/source fallback only. Field builds should use the same-folder EXE.
    values.append(Path(__file__).resolve().parents[1] / "dist" / "VexArtWorker.exe")
    unique: list[Path] = []
    seen: set[str] = set()
    for value in values:
        key = str(value).lower()
        if key not in seen:
            seen.add(key)
            unique.append(value)
    return unique


def _art_worker_exe() -> Path | None:
    for candidate in _art_worker_candidates():
        try:
            if candidate.is_file():
                return candidate
        except Exception:
            continue
    return None


def _art_worker_dimensions(orientation: str) -> tuple[int, int]:
    value = str(orientation or "portrait").lower().strip()
    if value in {"landscape", "horizontal", "wide"}:
        return 512, 320
    if value in {"square", "1:1"}:
        return 384, 384
    return 320, 512
'''

marker = "\n\ndef _art_comfy_health("
if marker not in text:
    raise SystemExit("art helper insertion marker missing")
text = text.replace(marker, "\n\n" + worker_helpers.strip() + marker, 1)

text = replace_function(text, "_art_comfy_health", r'''def _art_comfy_health(timeout: float = 1.5) -> bool:
    """Compatibility health hook: art is healthy when the standalone worker exists.

    Bridge intentionally does not probe/start ComfyUI anymore. VexArtWorker owns it.
    """
    return _art_worker_exe() is not None''')

text = replace_function(text, "_ensure_art_comfy", r'''def _ensure_art_comfy() -> tuple[bool, str | None]:
    """Compatibility shim that prevents Bridge/self-heal from owning ComfyUI."""
    worker = _art_worker_exe()
    if worker is None:
        return False, "VexArtWorker.exe is not beside VexBridge.exe."
    return True, None''')

text = replace_function(text, "_art_start_job", r'''def _art_start_job(raw_prompt: str, orientation: str) -> dict:
    raw_prompt = str(raw_prompt or "").strip()
    if not raw_prompt:
        return {"ok": False, "error": "missing image prompt"}
    if _art_worker_exe() is None:
        return {"ok": False, "error": "VexArtWorker.exe is not installed beside VexBridge.exe"}
    job_id = secrets.token_hex(10)
    seed = secrets.randbelow(2_147_483_647)
    width, height = _art_worker_dimensions(orientation)
    job = {
        "id": job_id,
        "status": "queued",
        "raw_prompt": raw_prompt[:7000],
        "orientation": str(orientation or "portrait"),
        "seed": seed,
        "width": width,
        "height": height,
        "model": "VexArtWorker",
        "created_at": time.time(),
        "error": None,
        "image_path": None,
        "content_type": "image/png",
        "prompt_mode": "smart",
    }
    with _ART_JOB_LOCK:
        _ART_JOBS[job_id] = job
    threading.Thread(target=_art_run_job, args=(job_id,), daemon=True, name=f"VexArtAdapter-{job_id[:6]}").start()
    _art_trim_jobs()
    return {"ok": True, "job_id": job_id, "seed": seed, "width": width, "height": height, "model": "VexArtWorker"}''')

text = replace_function(text, "_art_run_job", r'''def _art_run_job(job_id: str) -> None:
    with _ART_JOB_LOCK:
        job = dict(_ART_JOBS.get(job_id) or {})
        if not job:
            return
        _ART_JOBS[job_id]["status"] = "starting"

    worker = _art_worker_exe()
    if worker is None:
        with _ART_JOB_LOCK:
            if job_id in _ART_JOBS:
                _ART_JOBS[job_id]["status"] = "error"
                _ART_JOBS[job_id]["error"] = "VexArtWorker.exe is not beside VexBridge.exe"
        return

    # Existing Bridge resource coordination is still useful: release the 4B Ollama
    # model only when memory pressure says art needs the space, then rewarm after.
    try:
        _art_release_cognition_memory()
    except Exception:
        pass

    report_dir = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / "VexBridge" / "art_jobs"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{job_id}.json"
    try:
        report_path.unlink(missing_ok=True)
    except Exception:
        pass

    try:
        import subprocess
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        cmd = [
            str(worker),
            "--prompt", str(job.get("raw_prompt") or ""),
            "--orientation", str(job.get("orientation") or "portrait"),
            "--seed", str(int(job.get("seed") or 0)),
            "--result-file", str(report_path),
        ]
        with _ART_WORKER_PROCESS_LOCK:
            with _ART_JOB_LOCK:
                if job_id in _ART_JOBS:
                    _ART_JOBS[job_id]["status"] = "rendering"
            completed = subprocess.run(
                cmd,
                cwd=str(worker.parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=1800,
                creationflags=flags,
            )

        if not report_path.exists():
            raise RuntimeError(f"Art Worker exited {completed.returncode} without a result report")
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("Art Worker result report was invalid")
        if not payload.get("ok"):
            raise RuntimeError(str(payload.get("message") or payload.get("error_class") or payload.get("status") or "Art Worker render failed")[:1200])
        image_path = Path(str(payload.get("image_path") or ""))
        if not image_path.is_file() or image_path.stat().st_size < 1000:
            raise RuntimeError("Art Worker finished but its image file is missing")

        with _ART_JOB_LOCK:
            if job_id in _ART_JOBS:
                _ART_JOBS[job_id]["status"] = "done"
                _ART_JOBS[job_id]["image_path"] = str(image_path)
                _ART_JOBS[job_id]["model"] = str(payload.get("checkpoint") or "VexArtWorker")
                _ART_JOBS[job_id]["prompt_mode"] = str(payload.get("prompt_mode") or "smart")
                _ART_JOBS[job_id]["elapsed_seconds"] = payload.get("elapsed_seconds")
                _ART_JOBS[job_id]["completed_at"] = time.time()
    except subprocess.TimeoutExpired:
        with _ART_JOB_LOCK:
            if job_id in _ART_JOBS:
                _ART_JOBS[job_id]["status"] = "error"
                _ART_JOBS[job_id]["error"] = "Standalone Art Worker exceeded the 30-minute adapter timeout"
    except Exception as exc:
        print(f"[art-adapter] job {job_id} failed: {exc}", flush=True)
        with _ART_JOB_LOCK:
            if job_id in _ART_JOBS:
                _ART_JOBS[job_id]["status"] = "error"
                _ART_JOBS[job_id]["error"] = str(exc)[:1200]
    finally:
        try:
            _cognition_rewarm_async()
        except Exception:
            pass''')

text = replace_function(text, "_art_status", r'''def _art_status(job_id: str) -> dict:
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
        "prompt_mode": job.get("prompt_mode"),
        "elapsed_seconds": job.get("elapsed_seconds"),
        "worker": "VexArtWorker",
    }''')

text = replace_function(text, "_art_result", r'''def _art_result(job_id: str) -> tuple[bytes, str] | None:
    with _ART_JOB_LOCK:
        job = dict(_ART_JOBS.get(str(job_id or "")) or {})
    if job.get("status") != "done" or not job.get("image_path"):
        return None
    try:
        path = Path(str(job["image_path"]))
        if not path.exists() or path.stat().st_size > 30_000_000:
            return None
        return path.read_bytes(), str(job.get("content_type") or "image/png")
    except Exception:
        return None''')

# Replace the public health route only; the existing iOS contract remains intact.
health_start = text.find('        if parsed.path == "/art/health":')
status_start = text.find('        if parsed.path == "/art/status":', health_start)
if health_start < 0 or status_start < 0:
    raise SystemExit("art health/status route markers missing")
health_route = r'''        if parsed.path == "/art/health":
            worker = _art_worker_exe()
            self._json(200, {
                "ok": worker is not None,
                "installed": worker is not None,
                "running": False,
                "model": "VexArtWorker" if worker is not None else None,
                "ownership": "standalone-worker",
                "bridge_role": "broker-only",
            })
            return

'''
text = text[:health_start] + health_route + text[status_start:]

# Do not advertise the retired Bridge-owned SDXL checkpoint in /status.
text = text.replace('"local_art_model": ART_CHECKPOINT if (ART_COMFY_DIR / "models" / "checkpoints" / ART_CHECKPOINT).exists() else None,', '"local_art_model": "VexArtWorker" if _art_worker_exe() is not None else None,')

bridge_path.write_text(text, encoding="utf-8")

# ---------------------------------------------------------------------------
# Art Worker: add a result-file channel. The GUI stays windowed/no-console, while
# Bridge gets the full local render result (including image_path) without relying
# on stdout from a PyInstaller --windowed executable.
# ---------------------------------------------------------------------------
art_path = Path("Tools/VexArtWorker.py")
art = art_path.read_text(encoding="utf-8")
if 'VERSION = "0.10.6"' not in art:
    raise SystemExit("VexArtWorker v0.10.6 marker missing")
art = art.replace('VERSION = "0.10.6"', 'VERSION = "0.10.7"', 1)

arg_marker = '    parser.add_argument("--raw-prompt", action="store_true", help="Disable Smart Prompt compilation")\n'
if arg_marker not in art:
    raise SystemExit("Art Worker raw-prompt marker missing")
art = art.replace(arg_marker, arg_marker + '    parser.add_argument("--result-file", default="", help="Write full local JSON result for Bridge adapter")\n', 1)

prompt_block = '''    if args.prompt:\n        result = render(args.prompt, orientation=args.orientation, seed=args.seed, smart_prompt=not args.raw_prompt)\n        _json_print(sanitized(result))\n        stop_owned_comfy()\n        return 0 if result.get("ok") else 2\n'''
if prompt_block not in art:
    raise SystemExit("Art Worker prompt CLI block missing")
prompt_new = '''    if args.prompt:\n        result = render(args.prompt, orientation=args.orientation, seed=args.seed, smart_prompt=not args.raw_prompt)\n        if args.result_file:\n            try:\n                target = Path(args.result_file).expanduser()\n                target.parent.mkdir(parents=True, exist_ok=True)\n                target.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")\n            except Exception as exc:\n                result = {**result, "ok": False, "status": "adapter-report-error", "error_class": exc.__class__.__name__, "message": str(exc)}\n        _json_print(sanitized(result))\n        stop_owned_comfy()\n        return 0 if result.get("ok") else 2\n'''
art = art.replace(prompt_block, prompt_new, 1)
art_path.write_text(art, encoding="utf-8")

# ---------------------------------------------------------------------------
# Manifest: the planned adapter is now implemented; Bridge is explicitly broker.
# ---------------------------------------------------------------------------
manifest_path = Path("Tools/VexToolManifest.json")
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest["version"] = "0.10.7"
for tool in manifest.get("tools", []):
    if tool.get("id") == "art":
        tool["executable"] = "VexArtWorker.exe"
        tool["adapter"] = "complete"
        tool["owner"] = "VexArtWorker"
        tool["bridge_role"] = "broker-only"
planned = [item for item in manifest.get("planned_extractions", []) if "VexArtWorker adapter" not in str(item)]
manifest["planned_extractions"] = planned
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

# Launcher version identifies the Bridge bundle, not the model/checkpoint.
full_path = Path("Bridge/vex_bridge_full.py")
full = full_path.read_text(encoding="utf-8")
if 'VERSION = "0.9.8"' not in full:
    raise SystemExit("v0.9.8 Bridge launcher marker missing")
full = full.replace('VERSION = "0.9.8"', 'VERSION = "0.10.7"', 1)
full_path.write_text(full, encoding="utf-8")

# Deterministic build-time guarantees.
bridge_final = bridge_path.read_text(encoding="utf-8")
art_final = art_path.read_text(encoding="utf-8")
for required in [
    'VexArtWorker.exe', '--result-file', 'bridge_role": "broker-only"',
    'def _art_worker_exe', 'VexArtAdapter-', 'timeout=1800',
]:
    if required not in bridge_final:
        raise SystemExit(f"Bridge adapter missing marker: {required}")
for required in ['VERSION = "0.10.7"', '--result-file', 'target.write_text(json.dumps(result']:
    if required not in art_final:
        raise SystemExit(f"Art Worker adapter missing marker: {required}")
if 'VERSION = "0.10.7"' not in full_path.read_text(encoding="utf-8"):
    raise SystemExit("Bridge v0.10.7 launcher version missing")
print("Applied VexBridge v0.10.7 standalone Art Worker adapter")
