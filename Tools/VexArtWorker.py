#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import requests

VERSION = "0.10.0"
COMFY_BASE = "http://127.0.0.1:8188"
CHECKPOINT_NAME = "RealVisXL_V5.0_Lightning_fp16.safetensors"
NEGATIVE = (
    "worst quality, low quality, blurry, bad anatomy, bad hands, extra fingers, missing fingers, "
    "deformed face, deformed eyes, mutation, disfigured, text, watermark, logo"
)
LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
APPDATA = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
ART_ROOT = LOCALAPPDATA / "VexArt"
COMFY_DIR = ART_ROOT / "ComfyUI"
ART_PYTHON = ART_ROOT / "venv" / "Scripts" / "python.exe"
CHECKPOINT_DIR = COMFY_DIR / "models" / "checkpoints"
OUTPUT_DIR = Path.home() / "Pictures" / "VexRenders"
WORKER_ROOT = APPDATA / "VexArtWorker"
REPORT_PATH = WORKER_ROOT / "latest.json"
LOG_PATH = WORKER_ROOT / "worker-comfy.log"

_COMFY_PROCESS: subprocess.Popen | None = None
_COMFY_OWNED = False
_LAST_ACTIVITY = time.time()


def _write_report(payload: dict) -> None:
    WORKER_ROOT.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), "utf-8")


def _json_print(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def _http_json(method: str, path: str, *, json_body: dict | None = None, params: dict | None = None, timeout: float = 10.0) -> tuple[int, Any]:
    url = f"{COMFY_BASE}{path}"
    response = requests.get(url, params=params, timeout=timeout) if method == "GET" else requests.post(url, params=params, json=json_body, timeout=timeout)
    try:
        body = response.json() if response.content else {}
    except Exception:
        body = {"text": response.text[:2000]}
    return response.status_code, body


def comfy_health(timeout: float = 2.0) -> bool:
    try:
        status, _ = _http_json("GET", "/system_stats", timeout=timeout)
        return status < 400
    except Exception:
        return False


def _checkpoint_name() -> str | None:
    exact = CHECKPOINT_DIR / CHECKPOINT_NAME
    if exact.exists():
        return CHECKPOINT_NAME
    if not CHECKPOINT_DIR.exists():
        return None
    candidates = [p for p in CHECKPOINT_DIR.rglob("*") if p.is_file() and p.suffix.lower() in {".safetensors", ".ckpt"}]
    candidates.sort(key=lambda p: p.stat().st_size if p.exists() else 0, reverse=True)
    if not candidates:
        return None
    try:
        return str(candidates[0].relative_to(CHECKPOINT_DIR)).replace("\\", "/")
    except Exception:
        return candidates[0].name


def installed_state() -> dict:
    checkpoint = _checkpoint_name()
    return {
        "installed": (COMFY_DIR / "main.py").exists() and ART_PYTHON.exists(),
        "python_exists": ART_PYTHON.exists(),
        "comfy_exists": (COMFY_DIR / "main.py").exists(),
        "checkpoint": checkpoint,
        "checkpoint_exists": checkpoint is not None,
        "comfy_reachable": comfy_health(),
    }


def _torch_probe() -> dict:
    if not ART_PYTHON.exists():
        return {"ok": False, "mode": "missing", "error": "Vex Art Python is missing"}
    script = "import json,torch;print(json.dumps({'torch':torch.__version__,'cuda':bool(torch.cuda.is_available()),'cuda_count':int(torch.cuda.device_count()) if torch.cuda.is_available() else 0}))"
    try:
        proc = subprocess.run(
            [str(ART_PYTHON), "-c", script], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, timeout=180, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        payload = {}
        for line in reversed([x.strip() for x in (proc.stdout or "").splitlines() if x.strip()]):
            if line.startswith("{"):
                try:
                    payload = json.loads(line)
                    break
                except Exception:
                    pass
        if proc.returncode == 0 and payload:
            payload["ok"] = True
            payload["mode"] = "gpu" if payload.get("cuda") else "cpu"
            return payload
        return {"ok": False, "mode": "cpu", "error": "Torch probe failed", "detail": (proc.stdout or "")[-1600:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "mode": "cpu", "error": "Torch probe timed out"}
    except Exception as exc:
        return {"ok": False, "mode": "cpu", "error": exc.__class__.__name__}


def _read_log_tail(limit: int = 2400) -> str:
    try:
        return LOG_PATH.read_text("utf-8", errors="replace")[-limit:]
    except Exception:
        return ""


def _start_process(args: list[str]) -> subprocess.Popen:
    WORKER_ROOT.mkdir(parents=True, exist_ok=True)
    log = open(LOG_PATH, "a", encoding="utf-8", errors="replace")
    return subprocess.Popen(args, cwd=str(COMFY_DIR), stdout=log, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def ensure_comfy() -> tuple[bool, dict]:
    global _COMFY_PROCESS, _COMFY_OWNED
    if comfy_health():
        return True, {"mode": "existing", "owned": False}
    state = installed_state()
    if not state["installed"] or not state["checkpoint_exists"]:
        return False, {"error": "Vex Art installation is incomplete", **state}
    probe = _torch_probe()
    mode = "gpu" if probe.get("ok") and probe.get("cuda") else "cpu"
    base = [str(ART_PYTHON), "main.py", "--listen", "127.0.0.1", "--port", "8188", "--disable-auto-launch"]
    if mode == "cpu":
        attempts = [
            base + ["--cpu", "--force-fp32", "--fp32-vae", "--disable-xformers", "--preview-method", "none"],
            base + ["--cpu", "--force-fp32", "--preview-method", "none"],
        ]
    else:
        attempts = [base + ["--preview-method", "none"], base]
    for number, args in enumerate(attempts, start=1):
        try:
            _COMFY_PROCESS = _start_process(args)
            _COMFY_OWNED = True
            deadline = time.time() + 210
            while time.time() < deadline:
                if comfy_health(timeout=1.5):
                    return True, {"mode": mode, "owned": True, "attempt": number, "torch": probe}
                if _COMFY_PROCESS.poll() is not None:
                    break
                time.sleep(1.5)
        except Exception as exc:
            if number == len(attempts):
                return False, {"error": exc.__class__.__name__, "mode": mode, "torch": probe}
        try:
            if _COMFY_PROCESS and _COMFY_PROCESS.poll() is None:
                _COMFY_PROCESS.terminate()
                _COMFY_PROCESS.wait(timeout=8)
        except Exception:
            pass
    return False, {"error": "ComfyUI did not become ready", "mode": mode, "torch": probe, "log_tail": _read_log_tail()}


def stop_owned_comfy() -> bool:
    global _COMFY_PROCESS, _COMFY_OWNED
    if not _COMFY_OWNED or _COMFY_PROCESS is None:
        return False
    try:
        if _COMFY_PROCESS.poll() is None:
            _COMFY_PROCESS.terminate()
            try:
                _COMFY_PROCESS.wait(timeout=10)
            except subprocess.TimeoutExpired:
                _COMFY_PROCESS.kill()
        return True
    finally:
        _COMFY_PROCESS = None
        _COMFY_OWNED = False


def _extract_error(record: dict) -> dict:
    status = record.get("status") if isinstance(record, dict) else {}
    messages = status.get("messages") if isinstance(status, dict) else []
    if not isinstance(messages, list):
        messages = []
    for item in reversed(messages):
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        kind = str(item[0] or "")
        payload = item[1] if isinstance(item[1], dict) else {}
        if kind != "execution_error" and not payload.get("exception_message"):
            continue
        return {
            "error_class": str(payload.get("exception_type") or "RenderError")[:120],
            "node_id": str(payload.get("node_id") or "?")[:80],
            "node_type": str(payload.get("node_type") or payload.get("class_type") or "unknown")[:160],
            "message": str(payload.get("exception_message") or payload.get("message") or "ComfyUI execution failed")[:1200],
        }
    return {"error_class": "RenderError", "node_id": "?", "node_type": "unknown", "message": "ComfyUI reported a render error"}


def _validation_error(body: Any) -> dict:
    message, node_id, node_type = "ComfyUI rejected the workflow", "?", "validation"
    if isinstance(body, dict):
        message = str(body.get("error") or body.get("message") or message)
        node_errors = body.get("node_errors")
        if isinstance(node_errors, dict) and node_errors:
            node_id = str(next(iter(node_errors.keys())))
            detail = node_errors.get(node_id)
            if isinstance(detail, dict):
                errors = detail.get("errors")
                if isinstance(errors, list) and errors and isinstance(errors[0], dict):
                    first = errors[0]
                    node_type = str(first.get("type") or detail.get("class_type") or "validation")
                    message = str(first.get("message") or first.get("details") or message)
    return {"error_class": "WorkflowValidationError", "node_id": node_id[:80], "node_type": node_type[:160], "message": message[:1200]}


def _dimensions(orientation: str, mode: str, test: bool) -> tuple[int, int]:
    if test:
        return 512, 512
    low = str(orientation or "portrait").lower()
    cpu = mode != "gpu"
    if low in {"square", "1:1"}:
        return (640, 640) if cpu else (1024, 1024)
    if low in {"landscape", "wide", "horizontal"}:
        return (768, 512) if cpu else (1216, 832)
    return (512, 768) if cpu else (832, 1216)


def _workflow(prompt: str, checkpoint: str, width: int, height: int, seed: int, steps: int) -> dict:
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": NEGATIVE, "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": steps, "cfg": 1.6, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0, "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0]}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": "VexArtWorker", "images": ["6", 0]}},
    }


def render(prompt: str, *, orientation: str = "portrait", seed: int | None = None, test: bool = False, timeout: int = 1200) -> dict:
    global _LAST_ACTIVITY
    started = time.time()
    prompt = " ".join(str(prompt or "").split()).strip()
    if not prompt:
        return {"ok": False, "error_class": "InputError", "message": "Prompt is empty"}
    ok, launch = ensure_comfy()
    if not ok:
        result = {"ok": False, "status": "start_failed", "error_class": "ComfyStartError", "message": str(launch.get("error") or "ComfyUI could not start")[:1200], "elapsed_seconds": round(time.time() - started, 1)}
        _write_report(result)
        return result
    checkpoint = _checkpoint_name()
    if not checkpoint:
        result = {"ok": False, "status": "missing_checkpoint", "error_class": "CheckpointError", "message": "No checkpoint was found"}
        _write_report(result)
        return result
    mode = str(launch.get("mode") or "existing")
    if mode == "existing":
        probe = _torch_probe()
        mode = "gpu" if probe.get("ok") and probe.get("cuda") else "cpu"
    width, height = _dimensions(orientation, mode, test)
    seed = int(seed if seed is not None else random.randint(1, 2_147_483_647))
    workflow = _workflow(prompt, checkpoint, width, height, seed, 4 if test else 6)
    try:
        status_code, queued = _http_json("POST", "/prompt", json_body={"prompt": workflow, "client_id": f"vexart-{seed}"}, timeout=30)
        if status_code >= 400:
            result = {"ok": False, "status": "rejected", **_validation_error(queued), "width": width, "height": height, "seed": seed, "mode": mode, "elapsed_seconds": round(time.time() - started, 1)}
            _write_report(result)
            return result
        prompt_id = str(queued.get("prompt_id") if isinstance(queued, dict) else "").strip()
        if not prompt_id:
            result = {"ok": False, "status": "rejected", "error_class": "QueueError", "message": "ComfyUI returned no prompt id"}
            _write_report(result)
            return result
        deadline = time.time() + timeout
        image_meta = None
        while time.time() < deadline:
            time.sleep(1.5)
            try:
                code, body = _http_json("GET", f"/history/{prompt_id}", timeout=15)
            except Exception:
                continue
            if code >= 400 or not isinstance(body, dict):
                continue
            record = body.get(prompt_id) or {}
            outputs = record.get("outputs") if isinstance(record, dict) else {}
            if isinstance(outputs, dict):
                for output in outputs.values():
                    if isinstance(output, dict) and isinstance(output.get("images"), list) and output.get("images"):
                        image_meta = output["images"][0]
                        break
            if image_meta:
                break
            status = record.get("status") if isinstance(record, dict) else {}
            if isinstance(status, dict) and status.get("status_str") == "error":
                result = {"ok": False, "status": "error", **_extract_error(record), "width": width, "height": height, "seed": seed, "mode": mode, "elapsed_seconds": round(time.time() - started, 1)}
                _write_report(result)
                return result
        if not image_meta:
            result = {"ok": False, "status": "timeout", "error_class": "RenderTimeout", "message": f"No finished image after {timeout} seconds", "width": width, "height": height, "seed": seed, "mode": mode, "elapsed_seconds": round(time.time() - started, 1)}
            _write_report(result)
            return result
        params = {"filename": str(image_meta.get("filename") or ""), "subfolder": str(image_meta.get("subfolder") or ""), "type": str(image_meta.get("type") or "output")}
        response = requests.get(f"{COMFY_BASE}/view", params=params, timeout=60)
        response.raise_for_status()
        data = response.content
        if len(data) < 1000:
            raise RuntimeError("Rendered image payload was unexpectedly small")
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        target = OUTPUT_DIR / f"Vex_{time.strftime('%Y%m%d_%H%M%S')}_{seed}.png"
        target.write_bytes(data)
        _LAST_ACTIVITY = time.time()
        result = {"ok": True, "status": "done", "width": width, "height": height, "seed": seed, "mode": mode, "checkpoint": checkpoint, "image_path": str(target), "image_bytes": len(data), "elapsed_seconds": round(time.time() - started, 1)}
        _write_report(result)
        return result
    except Exception as exc:
        result = {"ok": False, "status": "exception", "error_class": exc.__class__.__name__, "message": str(exc)[:1200], "width": width, "height": height, "seed": seed, "mode": mode, "elapsed_seconds": round(time.time() - started, 1)}
        _write_report(result)
        return result


def sanitized(result: dict) -> dict:
    allowed = {"ok", "status", "installed", "python_exists", "comfy_exists", "checkpoint", "checkpoint_exists", "comfy_reachable", "error_class", "node_id", "node_type", "message", "width", "height", "seed", "mode", "image_bytes", "elapsed_seconds"}
    return {k: v for k, v in result.items() if k in allowed}


def headless_status() -> dict:
    state = installed_state()
    probe = _torch_probe() if state["installed"] else {"ok": False, "mode": "missing"}
    state["mode"] = "gpu" if probe.get("ok") and probe.get("cuda") else ("cpu" if state["installed"] else "missing")
    state["ok"] = bool(state["installed"] and state["checkpoint_exists"])
    return sanitized(state)


def _open(path: Path) -> None:
    if os.name == "nt":
        os.startfile(str(path))


def _gui() -> int:
    import tkinter as tk
    from tkinter import messagebox, ttk
    from tkinter.scrolledtext import ScrolledText
    try:
        from PIL import Image, ImageTk
    except Exception:
        Image = None
        ImageTk = None
    root = tk.Tk()
    root.title(f"Vex Art Worker v{VERSION}")
    root.geometry("980x760")
    root.minsize(800, 650)
    tk.Label(root, text="Vex Art Worker", font=("Segoe UI", 20, "bold")).pack(pady=(14, 2))
    status_var = tk.StringVar(value="Checking local art engine...")
    tk.Label(root, textvariable=status_var, font=("Segoe UI", 10, "bold")).pack(pady=(0, 8))
    top = tk.Frame(root)
    top.pack(fill="x", padx=16)
    tk.Label(top, text="Prompt:").pack(anchor="w")
    prompt_box = ScrolledText(top, height=6, wrap="word", font=("Segoe UI", 10))
    prompt_box.pack(fill="x", pady=(3, 8))
    prompt_box.insert("1.0", "photorealistic portrait of a stylish alternative woman, natural skin texture, dramatic but believable lighting")
    controls = tk.Frame(top)
    controls.pack(fill="x", pady=(0, 8))
    tk.Label(controls, text="Orientation:").pack(side="left")
    orientation = tk.StringVar(value="portrait")
    ttk.Combobox(controls, textvariable=orientation, values=["portrait", "landscape", "square"], state="readonly", width=12).pack(side="left", padx=(5, 10))
    seed_var = tk.StringVar(value="")
    tk.Label(controls, text="Seed (blank=random):").pack(side="left")
    tk.Entry(controls, textvariable=seed_var, width=14).pack(side="left", padx=(5, 10))
    buttons = tk.Frame(top)
    buttons.pack(fill="x", pady=(0, 8))
    output = ScrolledText(root, height=14, wrap="word", font=("Consolas", 9))
    output.pack(fill="both", expand=False, padx=16, pady=(6, 8))
    preview_label = tk.Label(root, text="No render yet", anchor="center")
    preview_label.pack(fill="both", expand=True, padx=16, pady=(0, 12))
    preview_ref = {"image": None, "path": None}

    def show_result(result: dict) -> None:
        output.delete("1.0", "end")
        output.insert("end", json.dumps(result, indent=2, ensure_ascii=False))
        status_var.set(f"Render finished in {result.get('elapsed_seconds')}s" if result.get("ok") else f"Needs attention: {result.get('error_class') or result.get('status')}")
        path = result.get("image_path")
        if path and Image and ImageTk:
            try:
                image = Image.open(path)
                image.thumbnail((760, 340))
                photo = ImageTk.PhotoImage(image)
                preview_ref["image"] = photo
                preview_ref["path"] = path
                preview_label.configure(image=photo, text="")
            except Exception:
                preview_label.configure(text=str(path), image="")

    def run_async(fn, label: str) -> None:
        status_var.set(label)
        def worker() -> None:
            result = fn()
            root.after(0, lambda: show_result(result))
        threading.Thread(target=worker, daemon=True).start()

    def do_generate() -> None:
        prompt = prompt_box.get("1.0", "end").strip()
        seed_text = seed_var.get().strip()
        try:
            seed = int(seed_text) if seed_text else None
        except ValueError:
            messagebox.showwarning("Vex Art Worker", "Seed must be a whole number or blank.")
            return
        run_async(lambda: render(prompt, orientation=orientation.get(), seed=seed), "Rendering...")

    def do_test() -> None:
        run_async(lambda: render("photograph of a red ceramic mug on a wooden table, soft window light, realistic materials", orientation="square", seed=123456, test=True), "Running deterministic render test...")

    def refresh() -> None:
        state = headless_status()
        output.delete("1.0", "end")
        output.insert("end", json.dumps(state, indent=2, ensure_ascii=False))
        status_var.set("Ready" if state.get("ok") else "Art installation needs attention")

    tk.Button(buttons, text="Generate", command=do_generate, width=14).pack(side="left", padx=4)
    tk.Button(buttons, text="Render Test", command=do_test, width=14).pack(side="left", padx=4)
    tk.Button(buttons, text="Refresh Status", command=refresh, width=14).pack(side="left", padx=4)
    tk.Button(buttons, text="Open Renders", command=lambda: (OUTPUT_DIR.mkdir(parents=True, exist_ok=True), _open(OUTPUT_DIR)), width=14).pack(side="left", padx=4)
    tk.Button(buttons, text="Stop Worker ComfyUI", command=lambda: status_var.set("Stopped worker-owned ComfyUI" if stop_owned_comfy() else "ComfyUI was not started by this app"), width=19).pack(side="left", padx=4)
    refresh()

    def idle_loop() -> None:
        if _COMFY_OWNED and time.time() - _LAST_ACTIVITY > 600:
            stop_owned_comfy()
            status_var.set("ComfyUI stopped after 10 minutes idle")
        root.after(30000, idle_loop)
    idle_loop()

    def close() -> None:
        stop_owned_comfy()
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", close)
    root.mainloop()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless-status", action="store_true")
    parser.add_argument("--render-test", action="store_true")
    parser.add_argument("--prompt", default="")
    parser.add_argument("--orientation", default="portrait")
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()
    if args.headless_status:
        _json_print(headless_status())
        return 0
    if args.render_test:
        result = render("photograph of a red ceramic mug on a wooden table, soft window light, realistic materials", orientation="square", seed=123456, test=True)
        _json_print(sanitized(result))
        stop_owned_comfy()
        return 0 if result.get("ok") else 2
    if args.prompt:
        result = render(args.prompt, orientation=args.orientation, seed=args.seed)
        _json_print(sanitized(result))
        stop_owned_comfy()
        return 0 if result.get("ok") else 2
    return _gui()


if __name__ == "__main__":
    raise SystemExit(main())
