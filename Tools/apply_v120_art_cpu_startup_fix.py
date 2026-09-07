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

replacement = r'''
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
            ("cpu-safe", base + ["--cpu", "--force-fp32", "--fp32-vae", "--disable-xformers", "--preview-method", "none", "--disable-all-custom-nodes"]),
            ("cpu-basic", base + ["--cpu", "--force-fp32", "--preview-method", "none"]),
            ("cpu-minimal", base + ["--cpu", "--preview-method", "none"]),
        ]
        startup_timeout = 600
    else:
        attempts = [
            ("gpu-default", base + ["--preview-method", "none"]),
            ("gpu-minimal", base),
        ]
        startup_timeout = 300

    last_error = "ComfyUI did not become ready"
    for number, (label, args) in enumerate(attempts, start=1):
        if "--cpu" in args and any(flag in args for flag in ("--lowvram", "--novram", "--highvram", "--gpu-only")):
            raise RuntimeError("invalid ComfyUI launch contract: CPU mode cannot include GPU VRAM mode flags")
        try:
            _COMFY_PROCESS = _start_process(args)
            _COMFY_OWNED = True
            deadline = time.time() + startup_timeout
            while time.time() < deadline:
                if comfy_health(timeout=1.5):
                    return True, {"mode": mode, "owned": True, "attempt": number, "launch_profile": label, "torch": probe}
                if _COMFY_PROCESS.poll() is not None:
                    last_error = f"ComfyUI exited during {label} startup"
                    break
                time.sleep(1.5)
        except Exception as exc:
            last_error = f"{label}: {exc.__class__.__name__}: {exc}"
        try:
            if _COMFY_PROCESS and _COMFY_PROCESS.poll() is None:
                _COMFY_PROCESS.terminate()
                _COMFY_PROCESS.wait(timeout=8)
        except Exception:
            pass

    return False, {
        "error": last_error,
        "mode": mode,
        "torch": probe,
        "log_tail": _read_log_tail(),
    }
'''

text = replace_function(text, "ensure_comfy", replacement)

marker = 'V120_ART_CPU_STARTUP = "v0.12-cpu-startup-v1"\n'
if "V120_ART_CPU_STARTUP" not in text:
    version_pos = text.find("VERSION = ")
    if version_pos < 0:
        raise SystemExit("VERSION marker missing")
    line_end = text.find("\n", version_pos) + 1
    text = text[:line_end] + marker + text[line_end:]

compile(text, str(path), "exec")
path.write_text(text, encoding="utf-8")
print("Applied v0.12 CPU Comfy startup fix")
