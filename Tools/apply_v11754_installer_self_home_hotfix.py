#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

INSTALLER = Path("Tools/VexAgentRuntimeInstall.py")
installer = INSTALLER.read_text(encoding="utf-8")

# Field hotfix: the extracted installer package itself contains VexBridge.exe and
# runtime folders, so the old candidate scorer could accidentally select the
# package directory as the existing installation. That caused replace_dir() to
# try to rename VexWindowsHost.vexnew over VexWindowsHost inside the package and
# Windows correctly returned WinError 5 / Access denied. Never install into the
# package that is currently executing.
forced_anchor = '''    forced = os.environ.get("VEX_HOME")\n    if forced:\n        path = Path(forced).expanduser().resolve()\n        if (path / "VexBridge.exe").exists():\n            return path\n        raise RuntimeError("VEX_HOME does not contain the existing VexBridge.exe")\n'''
forced_replacement = '''    forced = os.environ.get("VEX_HOME")\n    if forced:\n        path = Path(forced).expanduser().resolve()\n        pkg = package_dir().resolve()\n        if path == pkg:\n            raise RuntimeError("VEX_HOME points to this installer package, not the existing Vex installation.")\n        if (path / "VexBridge.exe").exists():\n            return path\n        raise RuntimeError("VEX_HOME does not contain the existing VexBridge.exe")\n'''
if forced_anchor not in installer:
    raise SystemExit("v0.11.7.54 installer VEX_HOME anchor missing")
installer = installer.replace(forced_anchor, forced_replacement, 1)

candidate_anchor = '''    if not candidates:\n        raise RuntimeError("Could not find the existing Vex install folder under Downloads, Desktop, or Documents.")\n    candidates = list(dict.fromkeys(p.resolve() for p in candidates))\n    candidates.sort(key=_candidate_score, reverse=True)\n    return candidates[0]\n'''
candidate_replacement = '''    if not candidates:\n        raise RuntimeError("Could not find the existing Vex install folder under Downloads, Desktop, or Documents.")\n    pkg = package_dir().resolve()\n    candidates = [p for p in dict.fromkeys(p.resolve() for p in candidates) if p != pkg]\n    if not candidates:\n        raise RuntimeError("Could not find an existing Vex install folder separate from this installer package.")\n    candidates.sort(key=_candidate_score, reverse=True)\n    return candidates[0]\n'''
if candidate_anchor not in installer:
    raise SystemExit("v0.11.7.54 installer candidate-selection anchor missing")
installer = installer.replace(candidate_anchor, candidate_replacement, 1)

INSTALLER.write_text(installer, encoding="utf-8")
print("Applied v0.11.7.54 installer self-home exclusion hotfix")
