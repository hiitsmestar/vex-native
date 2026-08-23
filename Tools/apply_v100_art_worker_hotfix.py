#!/usr/bin/env python3
from pathlib import Path

path = Path("Tools/VexArtWorker.py")
text = path.read_text(encoding="utf-8")

if "_BUSY = False" in text:
    print("Vex Art Worker busy-state hotfix already applied")
    raise SystemExit(0)

text = text.replace('_LAST_ACTIVITY = time.time()\n', '_LAST_ACTIVITY = time.time()\n_BUSY = False\n', 1)
text = text.replace('def render(prompt: str, *, orientation: str = "portrait", seed: int | None = None, test: bool = False, timeout: int = 1200) -> dict:\n    global _LAST_ACTIVITY\n', 'def render(prompt: str, *, orientation: str = "portrait", seed: int | None = None, test: bool = False, timeout: int = 1200) -> dict:\n    global _LAST_ACTIVITY, _BUSY\n    _BUSY = True\n    _LAST_ACTIVITY = time.time()\n', 1)
text = text.replace('    if not prompt:\n        return {"ok": False, "error_class": "InputError", "message": "Prompt is empty"}\n', '    if not prompt:\n        _BUSY = False\n        _LAST_ACTIVITY = time.time()\n        return {"ok": False, "error_class": "InputError", "message": "Prompt is empty"}\n', 1)
# Every report/return path clears the active-render flag so idle shutdown never
# races a long CPU render and a failed render never leaves the worker stuck busy.
text = text.replace('        _write_report(result)\n        return result\n', '        _write_report(result)\n        _BUSY = False\n        _LAST_ACTIVITY = time.time()\n        return result\n')
text = text.replace('            _write_report(result)\n            return result\n', '            _write_report(result)\n            _BUSY = False\n            _LAST_ACTIVITY = time.time()\n            return result\n')
text = text.replace('        if _COMFY_OWNED and time.time() - _LAST_ACTIVITY > 600:\n', '        if _COMFY_OWNED and not _BUSY and time.time() - _LAST_ACTIVITY > 600:\n', 1)

for marker in [
    "_BUSY = False",
    "global _LAST_ACTIVITY, _BUSY",
    "not _BUSY and time.time() - _LAST_ACTIVITY > 600",
    'if not prompt:\n        _BUSY = False',
]:
    if marker not in text:
        raise SystemExit(f"missing art worker hotfix marker: {marker}")

path.write_text(text, encoding="utf-8")
print("Applied Vex Art Worker busy-state hotfix")
