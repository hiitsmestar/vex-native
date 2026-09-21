#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
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
import VexVisualQA

VERSION = "0.10.13"
COMFY_BASE = "http://127.0.0.1:8188"
CHECKPOINT_NAME = "RealVisXL_V5.0_Lightning_fp16.safetensors"
LITE_CHECKPOINT_NAME = "v1-5-pruned-emaonly-fp16.safetensors"
LITE_CHECKPOINT_URL = "https://huggingface.co/Comfy-Org/stable-diffusion-v1-5-archive/resolve/main/v1-5-pruned-emaonly-fp16.safetensors?download=true"
LITE_CHECKPOINT_SHA256 = "e9476a13728cd75d8279f6ec8bad753a66a1957ca375a1464dc63b37db6e3916"
REALISM_CHECKPOINT_NAME = "realismByStableYogi_sd15V9.safetensors"
REALISM_CHECKPOINT_URL = "https://huggingface.co/Stableyogi/Realism-Checkpoints/resolve/main/realismByStableYogi_sd15V9.safetensors?download=true"
REALISM_CHECKPOINT_SHA256 = "f592c30e3fde778007bf103d37e5405f3212b73af7be3ed553d7511599555d56"
REALISM_NEGATIVE = "illustration, anime, cartoon, painting, drawing, 3d render, cgi, large breasts, huge breasts, exaggerated breasts, cropped body, close-up, missing arms, missing hands, missing legs, missing feet, extra limbs, deformed hands, bad anatomy, blurry, low quality, text, watermark, logo"
SMART_NEGATIVE = "wrong clothing colors, swapped clothing colors, unintended extra clothing, unintended duplicate subject, cropped head, cropped feet, out of frame, visible light stands, visible backdrop stands, visible clamps, studio equipment"
VEX_CHARACTER_PRESET = (
    "(same Vex identity:1.25), adult woman, narrow angular face, very pale skin, very slim wiry build, "
    "completely flat chest, narrow wiry torso, narrow waist and hips, long slender legs, small compact butt, "
    "messy black hair with (vivid violet-magenta streaks:1.2), heavy dark eyeliner, "
    "consistent facial and ear piercings, navel piercing, belly chain when visible, "
    "same face and body proportions across front, side, rear and group views"
)
VEX_SINGLE_NEGATIVE = (
    "large breasts, huge breasts, busty, curvy hourglass body, thick body, wide hips, big butt, huge butt, "
    "exaggerated curves, bodybuilder physique, missing violet-magenta hair streaks, missing piercings, "
    "plastic doll anatomy, featureless doll anatomy, distorted body proportions"
)
VEX_MULTI_NEGATIVE = "duplicate Vex, cloned primary woman, second Vex, extra woman, multiple women when men are requested, feminine male faces, female-looking male partners, curvy Vex, hourglass Vex, thick thighs on Vex, wide hips on Vex, large breasts on Vex, violet-magenta hair on anyone except Vex, Vex facial features on other people, inconsistent Vex face, missing Vex hair streaks, missing Vex piercings"
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
_BUSY = False


def _write_report(payload: dict) -> None:
    WORKER_ROOT.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), "utf-8")


def _json_print(payload: dict) -> None:
    try:
        print(json.dumps(payload, ensure_ascii=False), flush=True)
    except (OSError, ValueError):
        pass


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
        "realism_model_installed": _realism_model_installed(),
        "realism_checkpoint": REALISM_CHECKPOINT_NAME,
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


def _is_multi_subject(value: str) -> bool:
    import re
    low = " ".join(str(value or "").lower().split())
    tokens = (
        "with a man", "with a woman", "with another", "two men", "two guys", "two women",
        "three people", "three adults", "group", "crowd", "couple", "pair of people",
        "multiple people", "other people", "other adults", "beside him", "beside her",
    )
    if any(token in low for token in tokens):
        return True
    return bool(re.search(r"\b(?:2|3|4|two|three|four)\s+(?:(?:consenting|distinct|visible|naked|adult)\s+){0,4}(?:people|persons|adults|men|women|guys|girls)\b", low))


def _apply_vex_preset(prompt: str, negative: str, raw_request: str) -> tuple[str, str, bool]:
    multi = _is_multi_subject(raw_request)
    positive = VEX_CHARACTER_PRESET + ", " + str(prompt or "").strip()
    extra_negative = VEX_MULTI_NEGATIVE if multi else VEX_SINGLE_NEGATIVE + ", unintended extra people"
    combined_negative = ", ".join(x for x in (negative, extra_negative) if x)
    return positive, combined_negative, multi

def _smart_prompt(user_prompt: str, orientation: str = "portrait") -> tuple[str, str]:
    """Compile ordinary language into a stable SD1.5 realism prompt.

    Deterministic/local by design: no Bridge, Ollama or cloud API is loaded.
    Human-specific scaffolding is only applied to human/fashion requests.
    """
    import re

    raw = " ".join(str(user_prompt or "").split()).strip()
    negative = REALISM_NEGATIVE + ", " + SMART_NEGATIVE
    if not raw:
        return raw, negative

    low = raw.lower()
    photo_prefix = "photorealistic fashion photograph" if any(k in low for k in ("vex", "fashion", "woman", "girl", "model", "outfit", "thong", "crop top")) else "photorealistic photograph"

    human_terms = (
        "vex", "woman", "women", "girl", "female", "man", "men", "guy", "male", "person", "people", "model", "body", "face",
        "hair", "eyeliner", "chest", "stomach", "thong", "crop top", "dress", "skirt",
        "pants", "shorts", "sandals", "shoes", "boots", "choker",
    )
    is_human = any(term in low for term in human_terms)

    # Generic object/scene requests should remain generic. Smart Prompt only adds a
    # realism bias and removes literal studio-equipment wording.
    if not is_human:
        remainder = re.sub(r"studio\s+(?:photo|photograph)", "photograph", raw, flags=re.IGNORECASE)
        remainder = re.sub(r"(?:plain\s+)?(?:[a-z]+\s+)?studio\s+background", "simple seamless backdrop", remainder, flags=re.IGNORECASE)
        return f"{photo_prefix}, {remainder}, realistic materials, natural lighting", negative

    parts: list[str] = [photo_prefix]
    wants_full = any(k in low for k in ("full body", "full-body", "head to toe", "feet visible", "visible feet", "platform sandals", "shoes", "boots"))

    multi_subject = _is_multi_subject(raw)
    if multi_subject:
        male_pair = bool(re.search(r"\b(?:2|two)\s+(?:(?:consenting|distinct|visible|naked|adult)\s+){0,4}(?:men|guys|males)\b", low)) or (low.count("adult man") >= 2) or ("one distinct adult man on each side" in low)
        if male_pair:
            subject = "exactly three distinct adults: exactly one Vex, the only adult woman, plus exactly two adult men; Vex is extremely slim and wiry with narrow hips, completely flat chest, narrow wiry torso, long thin legs and a small compact butt; both men have clearly masculine faces and bodies, short non-Vex hair, no makeup, no feminine traits, and identities different from Vex and each other"
            negative += ", second woman, extra woman, female partner, feminine man, curvy Vex, hourglass Vex, thick thighs on Vex, wide hips on Vex, large breasts on Vex, duplicate Vex, cloned Vex"
        else:
            subject = "one and only one Vex as the primary adult woman, with every other adult exactly as described; Vex traits apply only to Vex and never to another person"
    elif "woman" in low or "girl" in low or "female" in low or "vex" in low:
        subject = "single adult woman"
    elif "man" in low or "male" in low:
        subject = "single adult man"
    else:
        subject = "single adult person"

    if wants_full:
        parts.append(subject + ", full body, head to toe in frame, complete limbs visible, coherent hands and feet")
    else:
        parts.append(subject)

    # Reinforce attribute bindings that the small checkpoint commonly swaps or drops.
    bindings: list[str] = []
    patterns = [
        (r"(?:long\s+)?(?:straight\s+)?black hair(?:\s+with\s+(?:hot\s+)?pink streaks)?", "long straight black hair with clearly visible hot pink streaks" if "pink streak" in low else "black hair"),
        (r"(?:tiny\s+|micro\s+)?(?:bright\s+)?pink\s+(?:crop top|cropped top|top)", "tiny bright pink crop top"),
        (r"black\s+(?:side[- ]string\s+)?thong", "black side-string thong"),
        (r"black\s+platform\s+sandals", "black platform sandals"),
        (r"dark\s+(?:smudged\s+)?eyeliner", "dark smudged eyeliner"),
        (r"black\s+choker", "black choker"),
        (r"small\s+chest", "small chest"),
        (r"flat\s+stomach", "flat stomach"),
        (r"very\s+slim|very\s+skinny|skinny", "very slim body"),
        (r"pale\s+skin|very\s+pale|pale\s+(?=woman|girl|female|person)", "pale skin"),
    ]

    remainder = raw
    for pattern, canonical in patterns:
        if re.search(pattern, remainder, flags=re.IGNORECASE):
            bindings.append(canonical)
            remainder = re.sub(pattern, " ", remainder, flags=re.IGNORECASE)

    if bindings:
        parts.append(", ".join(bindings))
        parts.append("clothing colors exactly as described, do not swap garment colors")

    remainder = re.sub(r"studio\s+(?:photo|photograph)", "fashion photograph", remainder, flags=re.IGNORECASE)
    remainder = re.sub(r"(?:plain\s+)?pink\s+studio\s+background", "solid plain pink seamless backdrop", remainder, flags=re.IGNORECASE)
    remainder = re.sub(r"\s+,", ",", remainder)
    remainder = " ".join(remainder.replace(", ,", ",").split()).strip(" ,")
    if remainder:
        parts.append(remainder)

    if "background" not in low and "backdrop" not in low:
        parts.append("simple seamless neutral backdrop")
    elif "pink" in low and ("background" in low or "backdrop" in low):
        parts.append("solid plain pink seamless backdrop, no visible photography equipment")

    parts.append("natural human proportions, realistic skin texture, anatomically coherent hands and feet")
    return ", ".join(p for p in parts if p), negative

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


def _memory_profile() -> dict:
    result = {
        "total_physical_mb": None,
        "available_physical_mb": None,
        "total_commit_mb": None,
        "available_commit_mb": None,
        "low_memory": False,
    }
    if os.name != "nt":
        return result
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            result["total_physical_mb"] = int(status.ullTotalPhys // (1024 * 1024))
            result["available_physical_mb"] = int(status.ullAvailPhys // (1024 * 1024))
            result["total_commit_mb"] = int(status.ullTotalPageFile // (1024 * 1024))
            result["available_commit_mb"] = int(status.ullAvailPageFile // (1024 * 1024))
            result["low_memory"] = result["total_physical_mb"] <= 12 * 1024
    except Exception:
        pass
    return result

def _start_process(args: list[str]) -> subprocess.Popen:
    WORKER_ROOT.mkdir(parents=True, exist_ok=True)
    log = open(LOG_PATH, "a", encoding="utf-8", errors="replace")
    env = os.environ.copy()
    # On the 8 GB CPU node, rendering must never starve Remote Support or the UI.
    threads = max(2, min(4, int(os.cpu_count() or 2) // 2 or 2))
    for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[key] = str(threads)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    flags |= getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
    return subprocess.Popen(
        args,
        cwd=str(COMFY_DIR),
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=flags,
        env=env,
    )

def ensure_comfy() -> tuple[bool, dict]:
    global _COMFY_PROCESS, _COMFY_OWNED
    # Modular ownership rule: Bridge/watchdog/manual ComfyUI copies may not be
    # silently adopted. One renderer process, one owner.
    if comfy_health():
        if _COMFY_OWNED and _COMFY_PROCESS is not None:
            return True, {"mode": "worker-owned", "owned": True, "memory": _memory_profile()}
        return False, {
            "error": "ComfyUI is already running outside Vex Art Worker. Stop the other ComfyUI process first.",
            "error_class": "ArtOwnershipConflict",
            "memory": _memory_profile(),
        }

    state = installed_state()
    if not state["installed"] or not state["checkpoint_exists"]:
        return False, {"error": "Vex Art installation is incomplete", **state}

    profile = _memory_profile()
    probe = _torch_probe()
    mode = "gpu" if probe.get("ok") and probe.get("cuda") else "cpu-lowmem"
    base = [str(ART_PYTHON), "main.py", "--listen", "127.0.0.1", "--port", "8188", "--disable-auto-launch"]

    if mode == "cpu-lowmem":
        total_mb = int(profile.get("total_physical_mb") or 0)
        if total_mb >= 14 * 1024:
            # 16 GB HP: this is the launch profile verified stable in the field.
            attempts = [
                base + ["--cpu", "--force-fp32", "--fp32-vae", "--disable-xformers", "--preview-method", "none"],
                base + ["--cpu", "--disable-xformers", "--preview-method", "none"],
                base + ["--cpu", "--lowvram", "--disable-xformers", "--preview-method", "none"],
            ]
        else:
            attempts = [
                base + ["--cpu", "--lowvram", "--disable-smart-memory", "--disable-xformers", "--preview-method", "none"],
                base + ["--cpu", "--lowvram", "--disable-xformers", "--preview-method", "none"],
                base + ["--cpu", "--disable-xformers", "--preview-method", "none"],
            ]
    else:
        attempts = [base + ["--preview-method", "none"], base]

    for number, args in enumerate(attempts, start=1):
        try:
            _COMFY_PROCESS = _start_process(args)
            _COMFY_OWNED = True
            deadline = time.time() + (300 if mode == "cpu-lowmem" else 210)
            while time.time() < deadline:
                if comfy_health(timeout=1.5):
                    return True, {
                        "mode": mode,
                        "owned": True,
                        "attempt": number,
                        "torch": probe,
                        "memory": profile,
                    }
                if _COMFY_PROCESS.poll() is not None:
                    break
                time.sleep(1.5)
        except Exception as exc:
            if number == len(attempts):
                return False, {"error": f"{exc.__class__.__name__}: {exc}", "mode": mode, "torch": probe, "memory": profile}
        try:
            if _COMFY_PROCESS and _COMFY_PROCESS.poll() is None:
                _COMFY_PROCESS.terminate()
                _COMFY_PROCESS.wait(timeout=8)
        except Exception:
            pass
        _COMFY_PROCESS = None
        _COMFY_OWNED = False

    return False, {
        "error": "ComfyUI did not become ready in any low-memory launch mode",
        "mode": mode,
        "torch": probe,
        "memory": profile,
        "log_tail": _read_log_tail(),
    }

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


def _select_checkpoint(mode: str) -> tuple[str | None, str]:
    if mode != "gpu":
        if _realism_model_installed():
            return REALISM_CHECKPOINT_NAME, "sd15-realism"
        if _lite_model_installed():
            return LITE_CHECKPOINT_NAME, "sd15-lite"
        return None, "lite-model-required"
    return _checkpoint_name(), "sdxl"

def _dimensions(orientation: str, mode: str, test: bool) -> tuple[int, int]:
    cpu = mode != "gpu"
    if test:
        return (320, 320) if cpu else (512, 512)
    low = str(orientation or "portrait").lower()
    if low in {"square", "1:1"}:
        return (384, 384) if cpu else (1024, 1024)
    if low in {"landscape", "wide", "horizontal"}:
        return (512, 320) if cpu else (1216, 832)
    return (320, 512) if cpu else (832, 1216)

def _workflow(prompt: str, checkpoint: str, width: int, height: int, seed: int, steps: int, cfg: float = 6.0, negative: str = NEGATIVE, sampler_name: str = "euler", scheduler: str = "normal") -> dict:
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": steps, "cfg": cfg, "sampler_name": sampler_name, "scheduler": scheduler, "denoise": 1.0, "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0]}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": "VexArtWorker", "images": ["6", 0]}},
    }

def render(prompt: str, *, orientation: str = "portrait", seed: int | None = None, test: bool = False, timeout: int = 1200, smart_prompt: bool = True, vex_preset: bool = True) -> dict:
    global _LAST_ACTIVITY, _BUSY
    _BUSY = True
    _LAST_ACTIVITY = time.time()
    started = time.time()
    prompt = " ".join(str(prompt or "").split()).strip()
    raw_request = prompt
    multi_subject = False
    if not prompt:
        _BUSY = False
        _LAST_ACTIVITY = time.time()
        return {"ok": False, "error_class": "InputError", "message": "Prompt is empty"}
    _write_stage("starting", "Starting local art engine")
    ok, launch = ensure_comfy()
    if not ok:
        result = {"ok": False, "status": "start_failed", "error_class": "ComfyStartError", "message": str(launch.get("error") or "ComfyUI could not start")[:1200], "elapsed_seconds": round(time.time() - started, 1)}
        _write_report(result)
        _BUSY = False
        _LAST_ACTIVITY = time.time()
        return result
    mode = str(launch.get("mode") or "cpu-lowmem")
    if mode == "worker-owned":
        mode = "cpu-lowmem"
    checkpoint, model_profile = _select_checkpoint(mode)
    if not checkpoint:
        result = {"ok": False, "status": "lite_model_required", "error_class": "LiteModelRequired", "message": "Install the free Lite CPU model in Vex Art Worker before rendering on this CPU-only node."}
        _write_report(result)
        _BUSY = False
        _LAST_ACTIVITY = time.time()
        return result
    width, height = _dimensions(orientation, mode, test)
    seed = int(seed if seed is not None else random.randint(1, 2_147_483_647))
    if model_profile == "sd15-realism":
        steps = 6 if test else 12
        cfg = 6.5
        sampler_name = "dpmpp_2m"
        scheduler = "karras"
        if smart_prompt and not test:
            prompt, negative = _smart_prompt(prompt, orientation)
        else:
            negative = REALISM_NEGATIVE
    elif model_profile == "sd15-lite":
        steps = 4 if test else 8
        cfg = 6.0
        sampler_name = "euler"
        scheduler = "normal"
        negative = NEGATIVE
    else:
        steps = 3 if test else 5
        cfg = 1.6
        sampler_name = "euler"
        scheduler = "normal"
        negative = NEGATIVE
    if vex_preset and not test:
        prompt, negative, multi_subject = _apply_vex_preset(prompt, negative, raw_request)
    _write_stage("loading_model", f"Loading {model_profile} checkpoint", checkpoint=checkpoint, width=width, height=height)
    workflow = _workflow(prompt, checkpoint, width, height, seed, steps, cfg=cfg, negative=negative, sampler_name=sampler_name, scheduler=scheduler)
    try:
        status_code, queued = _http_json("POST", "/prompt", json_body={"prompt": workflow, "client_id": f"vexart-{seed}"}, timeout=30)
        _write_stage("sampling", "ComfyUI accepted the workflow; sampling", checkpoint=checkpoint, width=width, height=height)
        if status_code >= 400:
            result = {"ok": False, "status": "rejected", **_validation_error(queued), "width": width, "height": height, "seed": seed, "mode": mode, "elapsed_seconds": round(time.time() - started, 1)}
            _write_report(result)
            _BUSY = False
            _LAST_ACTIVITY = time.time()
            return result
        prompt_id = str(queued.get("prompt_id") if isinstance(queued, dict) else "").strip()
        if not prompt_id:
            result = {"ok": False, "status": "rejected", "error_class": "QueueError", "message": "ComfyUI returned no prompt id"}
            _write_report(result)
            _BUSY = False
            _LAST_ACTIVITY = time.time()
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
            _BUSY = False
            _LAST_ACTIVITY = time.time()
            return result
        params = {"filename": str(image_meta.get("filename") or ""), "subfolder": str(image_meta.get("subfolder") or ""), "type": str(image_meta.get("type") or "output")}
        response = requests.get(f"{COMFY_BASE}/view", params=params, timeout=60)
        response.raise_for_status()
        data = response.content
        if len(data) < 1000:
            raise RuntimeError("Rendered image payload was unexpectedly small")
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        target = OUTPUT_DIR / f"Vex_{time.strftime('%Y%m%d_%H%M%S')}_{seed}.png"
        _write_stage("saving", "Saving completed render")
        target.write_bytes(data)
        _LAST_ACTIVITY = time.time()
        result = {"ok": True, "status": "done", "width": width, "height": height, "seed": seed, "mode": mode, "checkpoint": checkpoint, "prompt_mode": "smart" if (smart_prompt and model_profile == "sd15-realism" and not test) else "raw", "character_preset": "vex-v1" if (vex_preset and not test) else "off", "multi_subject": bool(multi_subject), "image_path": str(target), "image_bytes": len(data), "elapsed_seconds": round(time.time() - started, 1)}
        _write_report(result)
        _BUSY = False
        _LAST_ACTIVITY = time.time()
        return result
    except Exception as exc:
        result = {"ok": False, "status": "exception", "error_class": exc.__class__.__name__, "message": str(exc)[:1200], "width": width, "height": height, "seed": seed, "mode": mode, "elapsed_seconds": round(time.time() - started, 1)}
        _write_report(result)
        _BUSY = False
        _LAST_ACTIVITY = time.time()
        return result


def reviewed_render(prompt: str, *, orientation: str = "portrait", seed: int | None = None, smart_prompt: bool = True, vex_preset: bool = True, visual_review: bool = True) -> dict:
    result = render(prompt, orientation=orientation, seed=seed, smart_prompt=smart_prompt, vex_preset=vex_preset)
    if not visual_review:
        stop_owned_comfy()
        return result
    return VexVisualQA.review_and_correct(
        result,
        prompt,
        orientation,
        vex_preset,
        render,
        stop_owned_comfy,
        allow_correction=True,
    )


def sanitized(result: dict) -> dict:
    allowed = {"ok", "status", "installed", "python_exists", "comfy_exists", "checkpoint", "checkpoint_exists", "comfy_reachable", "error_class", "node_id", "node_type", "message", "width", "height", "seed", "mode", "image_bytes", "elapsed_seconds", "memory_total_mb", "memory_available_mb", "commit_total_mb", "commit_available_mb", "low_memory", "stage", "lite_model_installed", "lite_checkpoint", "realism_model_installed", "realism_checkpoint", "prompt_mode", "character_preset", "multi_subject", "visual_review_used", "visual_review_pass", "visual_review_summary", "visual_review_issues", "visual_review_confidence", "visual_review_model", "visual_review_corrected", "visual_review_correction_attempted", "visual_review_correction_failed"}
    return {k: v for k, v in result.items() if k in allowed}


def headless_status() -> dict:
    state = installed_state()
    probe = _torch_probe() if state["installed"] else {"ok": False, "mode": "missing"}
    state["mode"] = "gpu" if probe.get("ok") and probe.get("cuda") else ("cpu-lowmem" if state["installed"] else "missing")
    memory = _memory_profile()
    state.update({
        "memory_total_mb": memory.get("total_physical_mb"),
        "memory_available_mb": memory.get("available_physical_mb"),
        "commit_total_mb": memory.get("total_commit_mb"),
        "commit_available_mb": memory.get("available_commit_mb"),
        "low_memory": memory.get("low_memory"),
    })
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
    # Explicit Windows-friendly clipboard behavior for the prompt editor.
    # ScrolledText/Tk defaults vary across frozen builds, so bind everything
    # ourselves instead of making the user fight the widget.
    def _prompt_copy(event=None):
        try:
            selected = prompt_box.get("sel.first", "sel.last")
            root.clipboard_clear()
            root.clipboard_append(selected)
        except tk.TclError:
            pass
        return "break"

    def _prompt_cut(event=None):
        try:
            selected = prompt_box.get("sel.first", "sel.last")
            root.clipboard_clear()
            root.clipboard_append(selected)
            prompt_box.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        return "break"

    def _prompt_paste(event=None):
        try:
            value = root.clipboard_get()
        except tk.TclError:
            return "break"
        try:
            prompt_box.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        prompt_box.insert("insert", value)
        prompt_box.focus_set()
        return "break"

    def _prompt_select_all(event=None):
        prompt_box.tag_add("sel", "1.0", "end-1c")
        prompt_box.mark_set("insert", "1.0")
        prompt_box.see("insert")
        return "break"

    def _prompt_clear():
        prompt_box.delete("1.0", "end")
        prompt_box.focus_set()

    for seq, handler in (
        ("<Control-c>", _prompt_copy),
        ("<Control-C>", _prompt_copy),
        ("<Control-x>", _prompt_cut),
        ("<Control-X>", _prompt_cut),
        ("<Control-v>", _prompt_paste),
        ("<Control-V>", _prompt_paste),
        ("<Control-a>", _prompt_select_all),
        ("<Control-A>", _prompt_select_all),
    ):
        prompt_box.bind(seq, handler)

    prompt_menu = tk.Menu(root, tearoff=0)
    prompt_menu.add_command(label="Cut", command=_prompt_cut)
    prompt_menu.add_command(label="Copy", command=_prompt_copy)
    prompt_menu.add_command(label="Paste", command=_prompt_paste)
    prompt_menu.add_separator()
    prompt_menu.add_command(label="Select All", command=_prompt_select_all)
    prompt_menu.add_command(label="Clear", command=_prompt_clear)

    def _show_prompt_menu(event):
        try:
            prompt_menu.tk_popup(event.x_root, event.y_root)
        finally:
            prompt_menu.grab_release()
        return "break"

    prompt_box.bind("<Button-3>", _show_prompt_menu)

    prompt_tools = tk.Frame(top)
    prompt_tools.pack(fill="x", pady=(0, 6))
    tk.Button(prompt_tools, text="Paste", command=_prompt_paste, width=10).pack(side="left", padx=(0, 4))
    tk.Button(prompt_tools, text="Copy", command=_prompt_copy, width=10).pack(side="left", padx=4)
    tk.Button(prompt_tools, text="Select All", command=_prompt_select_all, width=10).pack(side="left", padx=4)
    tk.Button(prompt_tools, text="Clear", command=_prompt_clear, width=10).pack(side="left", padx=4)
    def _preview_smart_prompt():
        raw = prompt_box.get("1.0", "end").strip()
        if not raw:
            messagebox.showinfo("Vex Art Worker", "Type a short request first.")
            return
        compiled, preview_negative = _smart_prompt(raw, orientation.get()) if smart_var.get() else (raw, REALISM_NEGATIVE)
        if vex_var.get():
            compiled, preview_negative, _ = _apply_vex_preset(compiled, preview_negative, raw)
        preview = tk.Toplevel(root)
        preview.title("Smart Prompt Preview")
        preview.geometry("760x420")
        tk.Label(preview, text="This is what Art Worker will send to the realism model:", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(12, 6))
        box = ScrolledText(preview, height=14, wrap="word", font=("Segoe UI", 10))
        box.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        box.insert("1.0", compiled)
        box.configure(state="disabled")
        tk.Button(preview, text="Close", command=preview.destroy, width=12).pack(pady=(0, 12))

    tk.Button(prompt_tools, text="Preview Smart Prompt", command=_preview_smart_prompt, width=18).pack(side="left", padx=8)

    controls = tk.Frame(top)
    controls.pack(fill="x", pady=(0, 8))
    tk.Label(controls, text="Orientation:").pack(side="left")
    orientation = tk.StringVar(value="portrait")
    ttk.Combobox(controls, textvariable=orientation, values=["portrait", "landscape", "square"], state="readonly", width=12).pack(side="left", padx=(5, 10))
    seed_var = tk.StringVar(value="")
    smart_var = tk.BooleanVar(value=True)
    vex_var = tk.BooleanVar(value=True)
    tk.Label(controls, text="Seed (blank=random):").pack(side="left")
    tk.Entry(controls, textvariable=seed_var, width=14).pack(side="left", padx=(5, 10))
    tk.Checkbutton(controls, text="Smart Prompt", variable=smart_var).pack(side="left", padx=(8, 4))
    tk.Checkbutton(controls, text="Vex preset", variable=vex_var).pack(side="left", padx=(8, 4))
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
        run_async(lambda: reviewed_render(prompt, orientation=orientation.get(), seed=seed, smart_prompt=smart_var.get(), vex_preset=vex_var.get(), visual_review=True), "Rendering + visual QA...")

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
    def install_lite() -> None:
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

    def install_realism() -> None:
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

    tk.Button(buttons, text="Stop Worker ComfyUI", command=lambda: status_var.set("Stopped worker-owned ComfyUI" if stop_owned_comfy() else "ComfyUI was not started by this app"), width=19).pack(side="left", padx=4)
    tk.Button(buttons, text="Install Lite Model", command=install_lite, width=17).pack(side="left", padx=4)
    tk.Button(prompt_tools, text="Install Realism Model", command=install_realism, width=18).pack(side="left", padx=8)
    refresh()

    def idle_loop() -> None:
        if _COMFY_OWNED and not _BUSY and time.time() - _LAST_ACTIVITY > 600:
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
    parser.add_argument("--quick-status", action="store_true")
    parser.add_argument("--install-lite-model", action="store_true")
    parser.add_argument("--install-realism-model", action="store_true")
    parser.add_argument("--render-test", action="store_true")
    parser.add_argument("--prompt", default="")
    parser.add_argument("--orientation", default="portrait")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--raw-prompt", action="store_true", help="Disable Smart Prompt compilation")
    parser.add_argument("--no-vex-preset", action="store_true", help="Disable the default Vex character preset")
    parser.add_argument("--result-file", default="", help="Write full local JSON result for Bridge adapter")
    parser.add_argument("--no-visual-review", action="store_true", help="Skip Q6 visual QA and one-pass correction")
    args = parser.parse_args()
    if args.quick_status:
        _json_print(_quick_status())
        return 0
    if args.install_lite_model:
        result = _download_lite_model()
        _json_print(result)
        return 0 if result.get("ok") else 2
    if args.install_realism_model:
        result = _download_realism_model()
        _json_print(result)
        return 0 if result.get("ok") else 2
    if args.headless_status:
        _json_print(headless_status())
        return 0
    if args.render_test:
        result = render("photograph of a red ceramic mug on a wooden table, soft window light, realistic materials", orientation="square", seed=123456, test=True)
        _json_print(sanitized(result))
        stop_owned_comfy()
        return 0 if result.get("ok") else 2
    if args.prompt:
        cli_vex_preset = (not args.no_vex_preset) and ("vex" in args.prompt.lower())
        result = reviewed_render(
            args.prompt,
            orientation=args.orientation,
            seed=args.seed,
            smart_prompt=not args.raw_prompt,
            vex_preset=cli_vex_preset,
            visual_review=not args.no_visual_review,
        )
        if args.result_file:
            try:
                target = Path(args.result_file).expanduser()
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as exc:
                result = {**result, "ok": False, "status": "adapter-report-error", "error_class": exc.__class__.__name__, "message": str(exc)}
        _json_print(sanitized(result))
        stop_owned_comfy()
        return 0 if result.get("ok") else 2
    return _gui()


if __name__ == "__main__":
    raise SystemExit(main())

