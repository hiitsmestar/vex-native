#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

REMOTE = Path("Tools/VexRemoteSupport.py")
remote = REMOTE.read_text(encoding="utf-8")

if 'VERSION = "0.11.7.10"' not in remote:
    raise SystemExit("v0.11.7.11 expected Remote Support v0.11.7.10 source")

helper_anchor = '\n\ndef execute_command(command: dict, allow_maintenance: bool) -> dict:\n'
if helper_anchor not in remote:
    raise SystemExit("v0.11.7.11 execute_command anchor missing")

helpers = r'''

PROJECT_ALLOWED_FILES = {
    "VexBridge.exe",
    "VexRemoteSupport.exe",
    "VexMemoryWorker.exe",
    "VexArtWorker.exe",
    "VexDoctor.exe",
    "VexToolbox.exe",
    "VexBrainSetup.ps1",
    "VexBridgeWatchdog.ps1",
    "START-VEX-SELF-HEAL.cmd",
    "STOP-VEX-SELF-HEAL.cmd",
}
PROJECT_PROCESS_NAMES = {
    "bridge": "VexBridge.exe",
    "remote": "VexRemoteSupport.exe",
    "memory": "VexMemoryWorker.exe",
    "art": "VexArtWorker.exe",
    "doctor": "VexDoctor.exe",
    "toolbox": "VexToolbox.exe",
}


def _vex_project_home() -> Path | None:
    downloads = Path.home() / "Downloads"
    if not downloads.exists():
        return None
    candidates = []
    try:
        for child in downloads.iterdir():
            if not child.is_dir():
                continue
            if (child / "START-VEX-SELF-HEAL.cmd").exists() and (child / "VexBridge.exe").exists():
                candidates.append(child)
    except Exception:
        return None
    if not candidates:
        return None
    preferred = [p for p in candidates if p.name.startswith("VexBridge-v0.11.0-Personal-Memory-Star-Seeded")]
    return (preferred or candidates)[0]


def _project_process_count(image_name: str) -> int:
    try:
        result = run_quiet(["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV", "/NH"], timeout=10)
        text = str(result.stdout or "")
        return sum(1 for line in text.splitlines() if image_name.lower() in line.lower())
    except Exception:
        return 0


def _project_status() -> dict:
    home = _vex_project_home()
    files = {}
    if home:
        for name in sorted(PROJECT_ALLOWED_FILES):
            path = home / name
            if path.exists() and path.is_file():
                try:
                    files[name] = {"present": True, "bytes": int(path.stat().st_size)}
                except Exception:
                    files[name] = {"present": True, "bytes": 0}
    return {
        "ok": home is not None,
        "home_found": home is not None,
        "files": files,
        "processes": {key: _project_process_count(image) for key, image in PROJECT_PROCESS_NAMES.items()},
        "control_scope": "user-owned-vex-project-only",
    }


def _project_stop(key: str) -> dict:
    image = PROJECT_PROCESS_NAMES.get(str(key or "").strip().lower())
    if not image:
        return {"ok": False, "error": "unsupported Vex process"}
    try:
        run_quiet(["taskkill", "/F", "/IM", image], timeout=15)
    except Exception:
        pass
    return {"ok": _project_process_count(image) == 0, "process": str(key or "")[:24]}


def _project_start(key: str) -> dict:
    home = _vex_project_home()
    if not home:
        return {"ok": False, "error": "Vex project folder not found"}
    key = str(key or "").strip().lower()
    if key == "watchdog":
        target = home / "START-VEX-SELF-HEAL.cmd"
        if not target.exists():
            return {"ok": False, "error": "watchdog launcher missing"}
        try:
            subprocess.Popen(["cmd.exe", "/c", "start", "", str(target)], cwd=str(home), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return {"ok": True, "process": "watchdog"}
        except Exception as exc:
            return {"ok": False, "error": exc.__class__.__name__}
    image = PROJECT_PROCESS_NAMES.get(key)
    if not image:
        return {"ok": False, "error": "unsupported Vex process"}
    target = home / image
    if not target.exists():
        return {"ok": False, "error": "Vex executable missing"}
    try:
        subprocess.Popen([str(target)], cwd=str(home), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return {"ok": True, "process": key}
    except Exception as exc:
        return {"ok": False, "error": exc.__class__.__name__}


def _project_hash(name: str) -> dict:
    import hashlib
    home = _vex_project_home()
    safe = Path(str(name or "")).name
    if not home or safe not in PROJECT_ALLOWED_FILES:
        return {"ok": False, "error": "unsupported project file"}
    target = home / safe
    if not target.exists() or not target.is_file():
        return {"ok": False, "error": "project file missing"}
    try:
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        return {"ok": True, "file": safe, "sha256": digest, "bytes": int(target.stat().st_size)}
    except Exception as exc:
        return {"ok": False, "error": exc.__class__.__name__}


def _find_update_package(label: str) -> Path | None:
    label = str(label or "").strip()
    if not label or len(label) > 120 or not re.fullmatch(r"[A-Za-z0-9._() -]+", label):
        return None
    downloads = Path.home() / "Downloads"
    matches = []
    try:
        for path in downloads.rglob("*"):
            if not path.is_dir():
                continue
            if label.lower() not in path.name.lower():
                continue
            if any((path / name).exists() for name in PROJECT_ALLOWED_FILES):
                matches.append(path)
            if len(matches) >= 20:
                break
    except Exception:
        return None
    matches.sort(key=lambda p: len(p.parts))
    return matches[0] if matches else None


def _schedule_safe_update(command: dict) -> dict:
    home = _vex_project_home()
    if not home:
        return {"ok": False, "error": "Vex project folder not found"}
    package = _find_update_package(str(command.get("package") or ""))
    if not package:
        return {"ok": False, "error": "update package not found under Downloads"}
    requested = command.get("files")
    if requested is None:
        requested = ["VexBridge.exe", "VexRemoteSupport.exe"]
    if not isinstance(requested, list) or not requested:
        return {"ok": False, "error": "update files list required"}
    files = []
    for item in requested[:10]:
        safe = Path(str(item or "")).name
        if safe not in PROJECT_ALLOWED_FILES:
            return {"ok": False, "error": f"unsupported update file: {safe}"}
        if not (package / safe).exists():
            return {"ok": False, "error": f"package file missing: {safe}"}
        files.append(safe)

    helper = app_root() / "apply-safe-update.ps1"
    status_file = app_root() / "last-safe-update.json"
    copy_lines = []
    for name in files:
        src = str(package / name).replace("'", "''")
        dst = str(home / name).replace("'", "''")
        copy_lines.append(f"Copy-Item -LiteralPath '{src}' -Destination '{dst}' -Force")
        copy_lines.append(f"if ((Get-FileHash -LiteralPath '{src}').Hash -ne (Get-FileHash -LiteralPath '{dst}').Hash) {{ throw 'hash mismatch: {name}' }}")
    home_q = str(home).replace("'", "''")
    status_q = str(status_file).replace("'", "''")
    script = "\n".join([
        "$ErrorActionPreference='Stop'",
        "Start-Sleep -Seconds 8",
        "$watch = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*VexBridgeWatchdog.ps1*' }",
        "foreach ($p in $watch) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }",
        "Stop-Process -Name VexBridge,VexRemoteSupport,VexMemoryWorker,VexArtWorker -Force -ErrorAction SilentlyContinue",
        "Start-Sleep -Seconds 2",
        *copy_lines,
        f"@{{ok=$true;time=(Get-Date).ToString('o');files=@({','.join(repr(x) for x in files)})}} | ConvertTo-Json | Set-Content -LiteralPath '{status_q}' -Encoding UTF8",
        f"if (Test-Path -LiteralPath '{home_q}\\START-VEX-SELF-HEAL.cmd') {{ Start-Process -FilePath '{home_q}\\START-VEX-SELF-HEAL.cmd' -WorkingDirectory '{home_q}' }}",
        f"if (Test-Path -LiteralPath '{home_q}\\VexRemoteSupport.exe') {{ Start-Sleep -Seconds 3; Start-Process -FilePath '{home_q}\\VexRemoteSupport.exe' -WorkingDirectory '{home_q}' }}",
    ])
    try:
        helper.write_text(script, encoding="utf-8")
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(helper)],
            cwd=str(home),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return {"ok": True, "scheduled": True, "files": files, "restart_expected": True}
    except Exception as exc:
        return {"ok": False, "error": exc.__class__.__name__}
'''

remote = remote.replace(helper_anchor, helpers + helper_anchor, 1)

old_tail = '    if action == "maintenance_run":\n'
if old_tail not in remote:
    raise SystemExit("v0.11.7.11 maintenance action anchor missing")
control_cases = r'''    if action == "project_status":
        return {"project": _project_status()}
    if action == "project_hash":
        return {"project_file": _project_hash(str(command.get("file") or ""))}
    if action == "project_stop":
        return {"project_process": _project_stop(str(command.get("process") or ""))}
    if action == "project_start":
        return {"project_process": _project_start(str(command.get("process") or ""))}
    if action == "project_restart":
        key = str(command.get("process") or "").strip().lower()
        stopped = _project_stop(key)
        time.sleep(1.5)
        started = _project_start(key)
        return {"project_process": {"ok": bool(stopped.get("ok") and started.get("ok")), "stopped": stopped, "started": started}}
    if action == "safe_update":
        return {"safe_update": _schedule_safe_update(command)}
'''
remote = remote.replace(old_tail, control_cases + old_tail, 1)
remote = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.11"', remote, count=1, flags=re.M)

REMOTE.write_text(remote, encoding="utf-8")
compile(remote, str(REMOTE), "exec")

for marker in [
    'VERSION = "0.11.7.11"',
    'action == "project_status"',
    'action == "safe_update"',
    'PROJECT_ALLOWED_FILES',
    'apply-safe-update.ps1',
    'user-owned-vex-project-only',
    'http://127.0.0.1:11434/api/chat',
]:
    if marker not in remote:
        raise SystemExit(f"v0.11.7.11 verifier missing: {marker}")

print("Applied v0.11.7.11 bounded Vex project control + self-update layer")
