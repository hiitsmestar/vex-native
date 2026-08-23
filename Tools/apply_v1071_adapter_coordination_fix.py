#!/usr/bin/env python3
from pathlib import Path

path = Path("Bridge/vex_bridge.py")
text = path.read_text(encoding="utf-8")

marker = "\n\ndef _art_worker_dimensions(orientation: str) -> tuple[int, int]:\n"
if marker not in text:
    raise SystemExit("v0.10.7 Art Worker adapter helper marker missing")
helper = r'''
def _adapter_release_cognition_memory() -> bool:
    """Release the local Ollama model immediately before a Bridge-owned art job.

    v0.10.2 correctly prevented an independent/manual Art Worker from evicting
    cognition behind Bridge's back. In the standalone-adapter generation the
    request originates through Bridge, so Bridge is again the resource coordinator
    and may deliberately free the 4B model on low-memory nodes, then rewarm it
    after the worker exits.
    """
    global _ART_COGNITION_WAS_RELEASED
    try:
        model = _choose_ollama_model()
        if not model:
            return False
        import requests
        response = requests.post(
            f"{OLLAMA_BASE}/api/generate",
            json={"model": model, "prompt": "", "stream": False, "keep_alive": 0},
            timeout=25,
        )
        if response.status_code < 400:
            _ART_COGNITION_WAS_RELEASED = True
            print(f"[art-adapter] released cognition for standalone worker: {model}", flush=True)
            time.sleep(2)
            return True
    except Exception as exc:
        print(f"[art-adapter] cognition release skipped: {exc}", flush=True)
    return False
'''
text = text.replace(marker, "\n\n" + helper.strip() + marker, 1)

old = '''    try:\n        _art_release_cognition_memory()\n    except Exception:\n        pass\n'''
new = '''    try:\n        _adapter_release_cognition_memory()\n    except Exception:\n        pass\n'''
if old not in text:
    raise SystemExit("adapter cognition-release call marker missing")
text = text.replace(old, new, 1)

# This patch is reused by the v0.10.8 build chain, so report the actual bundle
# version that the subsequent verifier expects instead of leaving a stale 0.10.7.
text = text.replace('"version": "0.10.2"', '"version": "0.10.8"')
text = text.replace('"version": "0.10.7"', '"version": "0.10.8"')

for required in ["def _adapter_release_cognition_memory", "_ART_COGNITION_WAS_RELEASED = True", '"version": "0.10.8"']:
    if required not in text:
        raise SystemExit(f"v0.10.8 coordination marker missing: {required}")
path.write_text(text, encoding="utf-8")
print("Applied v0.10.8 Bridge-controlled art/cognition coordination fix")
