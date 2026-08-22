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
# v0.9.7.2 field hotfix
#
# Live field result after v0.9.7.1:
# - the original WinError 1114/c10.dll failure was correctly recognized
# - Microsoft VC runtime was already present
# - the pinned PyTorch 2.8 CPU fallback installed successfully
# - BUT the post-install torch smoke test was declared failed only because
#   `import torch` took longer than the old 50-second test timeout
# - art recovery also unloaded Ollama aggressively, which could make the 4B
#   cognition node cold and push ordinary chat over the 85-second timeout
#
# This patch treats these as slow-host coordination problems rather than another
# corrupt-install problem. No paid API/cloud dependency is added.
# ---------------------------------------------------------------------------


# 1) Replace the art cognition-release helper with memory-aware release and add
#    an asynchronous rewarm after a heavy art job completes.
release_start = text.find("def _art_release_cognition_memory(")
release_end = text.find("\n\ndef _art_torch_smoke", release_start)
if release_start < 0 or release_end < 0:
    raise SystemExit("art cognition-release markers missing")

release_block = r'''_ART_COGNITION_REWARM_LOCK = threading.Lock()
_ART_COGNITION_WAS_RELEASED = False
_ART_COGNITION_REWARM_RUNNING = False


def _art_release_cognition_memory(force: bool = False) -> bool:
    """Unload Ollama only when art really needs the RAM; return whether we did."""
    global _ART_COGNITION_WAS_RELEASED
    try:
        should_release = bool(force)
        if not should_release:
            try:
                snapshot = _resource_snapshot()
                available = snapshot.get("memory_available")
                total = snapshot.get("memory_total")
                # Utility/low-memory nodes benefit from unloading. Bigger nodes
                # keep cognition warm so ordinary chat does not repeatedly cold-boot.
                should_release = (
                    (available is not None and int(available) < 7 * 1024**3)
                    or (total is not None and int(total) < 16 * 1024**3)
                )
            except Exception:
                should_release = bool(force)
        if not should_release:
            return False

        model = _choose_ollama_model()
        if not model:
            return False
        import requests
        requests.post(
            f"{OLLAMA_BASE}/api/generate",
            json={"model": model, "prompt": "", "stream": False, "keep_alive": 0},
            timeout=20,
        )
        _ART_COGNITION_WAS_RELEASED = True
        print(f"[art] released Ollama model for heavy art work: {model}", flush=True)
        time.sleep(2)
        return True
    except Exception:
        return False


def _cognition_rewarm_async() -> None:
    """Bring the 4B node back after art work without blocking the render reply."""
    global _ART_COGNITION_WAS_RELEASED, _ART_COGNITION_REWARM_RUNNING
    if not _ART_COGNITION_WAS_RELEASED:
        return
    with _ART_COGNITION_REWARM_LOCK:
        if _ART_COGNITION_REWARM_RUNNING:
            return
        _ART_COGNITION_REWARM_RUNNING = True

    def worker() -> None:
        global _ART_COGNITION_WAS_RELEASED, _ART_COGNITION_REWARM_RUNNING
        try:
            model = _choose_ollama_model()
            if not model:
                return
            import requests
            response = requests.post(
                f"{OLLAMA_BASE}/api/chat",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Reply only: ready"}],
                    "stream": False,
                    "think": False,
                    "keep_alive": "2h",
                    "options": {"temperature": 0.0, "num_ctx": 256, "num_predict": 2},
                },
                timeout=300,
            )
            if response.status_code < 400:
                _ART_COGNITION_WAS_RELEASED = False
                print(f"[cognition] rewarmed after art task: {model}", flush=True)
        except Exception as exc:
            print(f"[cognition] post-art rewarm deferred: {exc}", flush=True)
        finally:
            with _ART_COGNITION_REWARM_LOCK:
                _ART_COGNITION_REWARM_RUNNING = False

    threading.Thread(target=worker, daemon=True, name="VexPostArtCognitionRewarm").start()
'''
text = text[:release_start] + release_block + text[release_end:]


# 2) Slow Windows CPU hosts can legitimately need minutes for their first
#    `import torch` after a wheel replacement. A 50-second timeout was falsely
#    classifying the successful PyTorch 2.8 install as another broken runtime.
smoke_start = text.find("def _art_torch_smoke(")
smoke_end = text.find("\n\ndef _art_runtime_repair_needed", smoke_start)
if smoke_start < 0 or smoke_end < 0:
    raise SystemExit("torch smoke markers missing")

smoke_block = r'''def _art_torch_smoke(timeout_seconds: int = 420) -> tuple[bool, str]:
    try:
        import subprocess
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        limit = max(90, int(timeout_seconds or 420))
        result = subprocess.run(
            [str(ART_PYTHON), "-c", "import torch; print(torch.__version__); print('cuda=' + str(torch.cuda.is_available()))"],
            cwd=str(ART_ROOT),
            env=_art_clean_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=limit,
            creationflags=flags,
        )
        output = str(result.stdout or "").strip()[-5000:]
        return result.returncode == 0, output
    except subprocess.TimeoutExpired as exc:
        partial = ""
        try:
            partial = str(exc.stdout or exc.output or "")[-2200:]
        except Exception:
            pass
        return False, f"torch import still initializing after {max(90, int(timeout_seconds or 420))} seconds; partial={partial}"
    except Exception as exc:
        return False, str(exc)
'''
text = text[:smoke_start] + smoke_block + text[smoke_end:]


# 3) During a recognized DLL-repair event we do want a deliberate memory release,
#    but ordinary warmup/restart paths remain memory-aware instead of constantly
#    throwing the local chat model out of RAM.
recover_start = text.find("def _art_recover_dll_runtime(")
recover_end = text.find("\n\n", recover_start)
if recover_start < 0:
    raise SystemExit("DLL recovery function missing")
# Function is longer than one paragraph; restrict the replacement to a window.
window_end = text.find("\n\ndef ", recover_start + 20)
if window_end < 0:
    window_end = len(text)
recover = text[recover_start:window_end]
if "_art_release_cognition_memory()" in recover:
    recover = recover.replace("_art_release_cognition_memory()", "_art_release_cognition_memory(force=True)", 1)
    text = text[:recover_start] + recover + text[window_end:]


# 4) Keep the PC cognition model resident longer and give a true CPU-cold start
#    more room, while reducing needless prompt bulk. This fixes the 503 seen after
#    art recovery had evicted the model.
ollama_start = text.find("def _ollama_chat(")
ollama_end = text.find("\n\n", ollama_start)
if ollama_start < 0:
    raise SystemExit("ollama chat function missing")
# Find the next top-level def, not an inner blank line.
next_def = text.find("\n\ndef ", ollama_start + 20)
if next_def < 0:
    next_def = len(text)
ollama = text[ollama_start:next_def]
ollama = ollama.replace("history[-28:]", "history[-16:]")
ollama = ollama.replace("content[:5000]", "content[:3200]")
ollama = ollama.replace("str(message or \"\").strip()[:5000]", "str(message or \"\").strip()[:3500]")
ollama = ollama.replace('"keep_alive": "30m"', '"keep_alive": "2h"')
ollama = ollama.replace('"num_predict": 220', '"num_predict": 180')
ollama = ollama.replace("timeout=85,", "timeout=180,")
text = text[:ollama_start] + ollama + text[next_def:]

# Warmup should also keep the model resident instead of expiring after 30m.
text = text.replace('"keep_alive": "30m"', '"keep_alive": "2h"')


# 5) Rewarm cognition after an art job finishes or errors. This is intentionally
#    asynchronous so image delivery is never held hostage by the 4B cold boot.
success_marker = '            _ART_JOBS[job_id]["completed_at"] = time.time()\n'
if success_marker not in text:
    raise SystemExit("art job completion marker missing")
text = text.replace(success_marker, success_marker + '        _cognition_rewarm_async()\n', 1)

error_marker = '                _ART_JOBS[job_id]["error"] = str(exc)[:1200]\n'
if error_marker not in text:
    raise SystemExit("art job error marker missing")
text = text.replace(error_marker, error_marker + '        _cognition_rewarm_async()\n', 1)

# Also rewarm when dependency recovery fails before the render body starts.
pre_render_error = '''    if not ok:\n        with _ART_JOB_LOCK:\n            _ART_JOBS[job_id]["status"] = "error"\n            _ART_JOBS[job_id]["error"] = error\n        return\n'''
pre_render_new = '''    if not ok:\n        with _ART_JOB_LOCK:\n            _ART_JOBS[job_id]["status"] = "error"\n            _ART_JOBS[job_id]["error"] = error\n        _cognition_rewarm_async()\n        return\n'''
replace_once(pre_render_error, pre_render_new, "post-repair cognition rewarm")


bridge_path.write_text(text, encoding="utf-8")

full_path = Path("Bridge/vex_bridge_full.py")
full = full_path.read_text(encoding="utf-8")
if 'VERSION = "0.9.7.1"' not in full:
    raise SystemExit("v0.9.7.1 launcher marker missing")
full = full.replace('VERSION = "0.9.7.1"', 'VERSION = "0.9.7.2"', 1)
full_path.write_text(full, encoding="utf-8")

checks = [
    "def _art_torch_smoke(timeout_seconds: int = 420)",
    "def _cognition_rewarm_async",
    "_art_release_cognition_memory(force=True)",
    '"keep_alive": "2h"',
    "timeout=180",
    "VexPostArtCognitionRewarm",
]
final = bridge_path.read_text(encoding="utf-8")
for check in checks:
    if check not in final:
        raise SystemExit(f"v0.9.7.2 missing marker: {check}")
if 'VERSION = "0.9.7.2"' not in full_path.read_text(encoding="utf-8"):
    raise SystemExit("v0.9.7.2 launcher version missing")

print("Applied Vex v0.9.7.2 slow-CPU art/cognition coordination hotfix")
