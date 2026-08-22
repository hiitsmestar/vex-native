#!/usr/bin/env python3
from pathlib import Path

bridge_path = Path("Bridge/vex_bridge.py")
text = bridge_path.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global text
    if old not in text:
        raise SystemExit(f"{label}: expected source block not found")
    text = text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# 1) Fix the learned-skill configuration crash seen on the live Windows nodes.
# v0.8.4 introduced CONFIG_DIR but the base Bridge only owns CONFIG_PATH.
# Keep a compatibility alias for any older helper and make _skills_path use the
# canonical path directly so /status and skill loading cannot throw NameError.
# ---------------------------------------------------------------------------
config_marker = 'CONFIG_PATH = app_dir() / "config.json"\n'
if config_marker not in text:
    raise SystemExit("CONFIG_PATH marker missing")
if 'CONFIG_DIR = CONFIG_PATH.parent\n' not in text:
    text = text.replace(config_marker, config_marker + 'CONFIG_DIR = CONFIG_PATH.parent\n', 1)

if 'return CONFIG_DIR / "learned_skills.json"' in text:
    text = text.replace(
        'return CONFIG_DIR / "learned_skills.json"',
        'return CONFIG_PATH.parent / "learned_skills.json"',
        1,
    )
else:
    if 'return CONFIG_PATH.parent / "learned_skills.json"' not in text:
        raise SystemExit("learned skill path marker missing")


# ---------------------------------------------------------------------------
# 2) Make local ComfyUI startup self-diagnosing and CPU-safe.
# The art setup may deliberately install CPU-capable ComfyUI; launch it with
# --cpu when Torch reports no CUDA device. Cold starts get five minutes, and a
# startup failure returns the useful tail of comfyui-bridge.log instead of only
# saying that ComfyUI exited.
# ---------------------------------------------------------------------------
start = text.find("def _ensure_art_comfy() -> tuple[bool, str | None]:\n")
end = text.find("\n\ndef _art_is_stylized", start)
if start < 0 or end < 0:
    raise SystemExit("art startup function markers missing")

new_art_startup = r'''def _art_log_tail(max_bytes: int = 4200) -> str:
    log_path = ART_ROOT / "comfyui-bridge.log"
    try:
        if not log_path.exists():
            return ""
        data = log_path.read_bytes()
        tail = data[-max_bytes:].decode("utf-8", "replace")
        # Keep the phone error readable while preserving the lines that matter.
        lines = [line.rstrip() for line in tail.splitlines() if line.strip()]
        return "\n".join(lines[-24:])[-max_bytes:]
    except Exception:
        return ""


def _art_runtime_mode() -> str:
    """Return cuda when this VexArt venv can actually use CUDA; otherwise cpu."""
    try:
        import subprocess
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        result = subprocess.run(
            [
                str(ART_PYTHON), "-c",
                "import torch; print('cuda' if torch.cuda.is_available() else 'cpu')",
            ],
            cwd=str(ART_COMFY_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=25,
            creationflags=flags,
        )
        if result.returncode == 0 and "cuda" in str(result.stdout or "").lower():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def _ensure_art_comfy() -> tuple[bool, str | None]:
    global _ART_COMFY_PROCESS
    if _art_comfy_health():
        return True, None
    if not ART_PYTHON.exists() or not (ART_COMFY_DIR / "main.py").exists():
        return False, "Vex Art Engine is not installed on this PC. Run VexArtSetup.ps1 first."

    try:
        if _ART_COMFY_PROCESS is not None and _ART_COMFY_PROCESS.poll() is not None:
            _ART_COMFY_PROCESS = None
    except Exception:
        _ART_COMFY_PROCESS = None

    import subprocess
    ART_ROOT.mkdir(parents=True, exist_ok=True)
    log_path = ART_ROOT / "comfyui-bridge.log"
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    mode = _art_runtime_mode()
    args = [
        str(ART_PYTHON), "main.py",
        "--listen", "127.0.0.1",
        "--port", "8188",
        "--disable-auto-launch",
    ]
    if mode == "cpu":
        args.append("--cpu")

    try:
        with log_path.open("ab", buffering=0) as log:
            log.write(
                (f"\n[VexBridge] {time.strftime('%Y-%m-%d %H:%M:%S')} starting ComfyUI mode={mode} args={' '.join(args[1:])}\n")
                .encode("utf-8", "replace")
            )
            _ART_COMFY_PROCESS = subprocess.Popen(
                args,
                cwd=str(ART_COMFY_DIR),
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=flags,
            )

        # CPU-only Windows machines can need several minutes to import Torch,
        # scan models, and initialize the SDXL checkpoint on a true cold start.
        for _ in range(600):
            time.sleep(0.5)
            if _art_comfy_health(timeout=1.4):
                print(f"[art] ComfyUI ready in {mode} mode", flush=True)
                return True, None
            try:
                if _ART_COMFY_PROCESS is not None and _ART_COMFY_PROCESS.poll() is not None:
                    code = _ART_COMFY_PROCESS.returncode
                    _ART_COMFY_PROCESS = None
                    tail = _art_log_tail()
                    detail = f"\nComfyUI startup log tail:\n{tail}" if tail else ""
                    return False, f"ComfyUI exited during startup (code {code}). See {log_path}.{detail}"
            except Exception:
                pass

        tail = _art_log_tail()
        detail = f"\nComfyUI startup log tail:\n{tail}" if tail else ""
        return False, f"ComfyUI did not become ready within 300 seconds. See {log_path}.{detail}"
    except Exception as exc:
        tail = _art_log_tail()
        detail = f"\nComfyUI startup log tail:\n{tail}" if tail else ""
        return False, f"Could not start ComfyUI: {exc}.{detail}"
'''
text = text[:start] + new_art_startup + text[end:]


# ---------------------------------------------------------------------------
# 3) Stagger the heavy local services.
# Warm the 4B cognition model first, then wake ComfyUI. This prevents a cold
# Ollama load and a cold Torch/SDXL load from fighting for CPU/RAM at boot.
# ---------------------------------------------------------------------------
bg_start = text.find("def _vex_background_services() -> None:\n")
bg_end = text.find("\n\n_BROWSER_CONTROL_LOCK = threading.Lock()", bg_start)
if bg_start < 0 or bg_end < 0:
    raise SystemExit("background service markers missing")

new_background = r'''def _vex_background_services() -> None:
    cognition_settled = threading.Event()

    def warm_cognition() -> None:
        time.sleep(3)
        try:
            model = _choose_ollama_model()
            if not model:
                print("[cognition] no local Ollama model found for warmup", flush=True)
                return
            import requests
            response = requests.post(
                f"{OLLAMA_BASE}/api/chat",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Reply only: ready"}],
                    "stream": False,
                    "think": False,
                    "keep_alive": "30m",
                    "options": {
                        "temperature": 0.0,
                        "num_ctx": 512,
                        "num_predict": 2,
                    },
                },
                timeout=150,
            )
            if response.status_code < 400:
                print(f"[cognition] local model warm: {model}", flush=True)
            else:
                print(f"[cognition] warmup HTTP {response.status_code}", flush=True)
        except Exception as exc:
            print(f"[cognition] warmup deferred: {exc}", flush=True)
        finally:
            cognition_settled.set()

    def warm_art() -> None:
        # Give cognition first claim on CPU/RAM. If Ollama is unusually slow,
        # don't block art forever; proceed after the bounded wait.
        cognition_settled.wait(timeout=165)
        time.sleep(12)
        if ART_PYTHON.exists() and (ART_COMFY_DIR / "main.py").exists() and not _art_comfy_health(timeout=0.8):
            ok, error = _ensure_art_comfy()
            if ok:
                print("[art] ComfyUI warm and ready", flush=True)
            elif error:
                print(f"[art] warmup: {error}", flush=True)

    threading.Thread(target=warm_cognition, daemon=True, name="VexCognitionWarmup").start()
    threading.Thread(target=warm_art, daemon=True, name="VexArtWarmup").start()
    threading.Thread(target=_hk_maintenance_loop, daemon=True, name="VexHousekeeperMaintenance").start()
'''
text = text[:bg_start] + new_background + text[bg_end:]

bridge_path.write_text(text, encoding="utf-8")

# Windows launcher patch version.
full_path = Path("Bridge/vex_bridge_full.py")
full = full_path.read_text(encoding="utf-8")
if 'VERSION = "0.9.6"' not in full:
    raise SystemExit("full bridge v0.9.6 marker missing")
full = full.replace('VERSION = "0.9.6"', 'VERSION = "0.9.6.1"', 1)
full_path.write_text(full, encoding="utf-8")

checks = [
    "CONFIG_DIR = CONFIG_PATH.parent",
    'return CONFIG_PATH.parent / "learned_skills.json"',
    "def _art_log_tail",
    "def _art_runtime_mode",
    'args.append("--cpu")',
    "ComfyUI startup log tail",
    "VexCognitionWarmup",
    "cognition_settled.wait(timeout=165)",
]
final = bridge_path.read_text(encoding="utf-8")
for marker in checks:
    if marker not in final:
        raise SystemExit(f"missing v0.9.6.1 bridge marker: {marker}")
if 'VERSION = "0.9.6.1"' not in full_path.read_text(encoding="utf-8"):
    raise SystemExit("missing v0.9.6.1 launcher version")

print("Applied v0.9.6.1 CONFIG_DIR + staged cognition + CPU-safe art startup hotfix")
