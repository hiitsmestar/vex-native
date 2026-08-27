from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from tkinter import Tk, messagebox

BUNDLE_VERSION = "0.11.7.49"
BRIDGE_VERSION = "0.11.7.39"
REMOTE_VERSION = "0.11.7.29"
HOST_VERSION = "0.11.7.40"
MEMORY_PORT = 8806

ROOT_FILES = (
    "VexBridge.exe",
    "VexDoctor.exe",
    "VexToolbox.exe",
)
RUNTIME_DIRS = (
    "VexBridgeRuntime",
    "VexMemoryWorkerRuntime",
    "VexRemoteSupportRuntime",
    "VexWindowsHost",
    "VexNodeAgent",
)
KNOWN_PROCESSES = (
    "VexBridge",
    "VexMemoryWorker",
    "VexDoctor",
    "VexToolbox",
    "VexRemoteSupport",
    "VexWindowsHost",
    "VexNodeAgent",
)


def package_dir() -> Path:
    return Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent


def appdata_dir(name: str) -> Path:
    root = Path(os.environ.get("APPDATA") or Path.home())
    return root / name


def bridge_config() -> dict:
    path = appdata_dir("VexBridge") / "config.json"
    try:
        value = json.loads(path.read_text("utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _candidate_score(path: Path) -> tuple[int, float]:
    score = 0
    if (path / "VexBridge.exe").exists():
        score += 20
    if (path / "VexBridgeRuntime").is_dir():
        score += 10
    if (path / "VexRemoteSupportRuntime").is_dir():
        score += 8
    if (path / "VexMemoryWorkerRuntime" / "VexMemoryWorker.exe").exists():
        score += 4
    if (path / "VexMemoryWorker.exe").exists():
        score += 2
    if (path / "START-VEX-SELF-HEAL.cmd").exists():
        score += 2
    if "vex" in path.name.lower():
        score += 1
    try:
        stamp = path.stat().st_mtime
    except Exception:
        stamp = 0.0
    return score, stamp


def find_home() -> Path:
    forced = os.environ.get("VEX_HOME")
    if forced:
        path = Path(forced).expanduser().resolve()
        if (path / "VexBridge.exe").exists():
            return path
        raise RuntimeError("VEX_HOME does not contain the existing VexBridge.exe")

    roots = [Path.home() / "Downloads", Path.home() / "Desktop", Path.home() / "Documents"]
    candidates: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        try:
            for first in root.iterdir():
                if first.is_dir() and (first / "VexBridge.exe").exists():
                    candidates.append(first)
                if first.is_dir():
                    try:
                        for second in first.iterdir():
                            if second.is_dir() and (second / "VexBridge.exe").exists():
                                candidates.append(second)
                    except Exception:
                        pass
        except Exception:
            pass
    if not candidates:
        raise RuntimeError("Could not find the existing Vex install folder under Downloads, Desktop, or Documents.")
    candidates = list(dict.fromkeys(p.resolve() for p in candidates))
    candidates.sort(key=_candidate_score, reverse=True)
    return candidates[0]


def run_powershell(script: str, timeout: int = 50) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        timeout=timeout,
        capture_output=True,
        text=True,
    )


def stop_known_vex_processes() -> None:
    names = ",".join(f"'{name}.exe'" for name in KNOWN_PROCESSES)
    script = f"""
$ErrorActionPreference='SilentlyContinue'
$names=@({names})
$deadline=(Get-Date).AddSeconds(35)
do {{
  $targets=@(Get-CimInstance Win32_Process | Where-Object {{ $_.Name -in $names }})
  $targets | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}
  Start-Sleep -Milliseconds 600
  $left=@(Get-CimInstance Win32_Process | Where-Object {{ $_.Name -in $names }})
}} while ($left.Count -gt 0 -and (Get-Date) -lt $deadline)
if ($left.Count -gt 0) {{ exit 9 }}
"""
    result = run_powershell(script, timeout=45)
    if result.returncode != 0:
        raise RuntimeError("Could not stop the existing Vex runtime cleanly before install.")


def replace_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".vexnew")
    try:
        tmp.unlink(missing_ok=True)
    except Exception:
        pass
    shutil.copy2(src, tmp)
    os.replace(tmp, dst)


def replace_dir(src: Path, dst: Path) -> None:
    staged = dst.with_name(dst.name + ".vexnew")
    old = dst.with_name(dst.name + ".vexold")
    shutil.rmtree(staged, ignore_errors=True)
    shutil.rmtree(old, ignore_errors=True)
    shutil.copytree(src, staged)
    if dst.exists():
        try:
            dst.replace(old)
        except Exception:
            shutil.rmtree(dst, ignore_errors=True)
    staged.replace(dst)
    shutil.rmtree(old, ignore_errors=True)


def local_bridge_get(path: str, timeout: float = 4.0) -> dict:
    cfg = bridge_config()
    token = str(cfg.get("token") or "").strip()
    external = int(cfg.get("port") or 8765)
    preferred = int(cfg.get("local_control_port") or (external + 1))
    if not token:
        raise RuntimeError("Bridge token is unavailable in the existing local configuration.")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    last: Exception | None = None
    ports = [preferred] + [p for p in range(external + 1, external + 13) if p != preferred]
    for port in ports:
        url = f"http://127.0.0.1:{port}{path}?" + urllib.parse.urlencode({"token": token})
        try:
            with opener.open(url, timeout=timeout) as response:
                value = json.loads(response.read().decode("utf-8"))
            if isinstance(value, dict):
                return value
        except Exception as exc:
            last = exc
    raise RuntimeError(f"Local Bridge request {path} failed: {(last.__class__.__name__ if last else 'no response')}")


def wait_bridge(seconds: int = 120) -> dict:
    deadline = time.time() + seconds
    last = "no response"
    while time.time() < deadline:
        try:
            value = local_bridge_get("/status", timeout=3.0)
            if str(value.get("version") or "") == BRIDGE_VERSION and str(value.get("local_control_protocol") or "") == "vex-local-v1":
                return value
            last = f"unexpected identity {value.get('version')}"
        except Exception as exc:
            last = str(exc)
        time.sleep(1.0)
    raise RuntimeError(f"Bridge {BRIDGE_VERSION} did not become ready: {last}")


def wait_direct_memory(seconds: int = 30) -> dict:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.time() + seconds
    last = "no response"
    while time.time() < deadline:
        try:
            with opener.open(f"http://127.0.0.1:{MEMORY_PORT}/health", timeout=2.0) as response:
                value = json.loads(response.read().decode("utf-8"))
            if isinstance(value, dict) and bool(value.get("ok")):
                return value
            last = str(value)
        except Exception as exc:
            last = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"Persistent memory sidecar did not become ready: {last}")


def wait_memory(seconds: int = 40) -> dict:
    deadline = time.time() + seconds
    last = "no response"
    while time.time() < deadline:
        try:
            value = local_bridge_get("/memory/status", timeout=3.0)
            if bool(value.get("ok")):
                return value
            last = str(value.get("error") or "memory worker not ready")
        except Exception as exc:
            last = str(exc)
        time.sleep(0.8)
    raise RuntimeError(f"Persistent memory did not become ready: {last}")


def wait_adaptive(seconds: int = 40) -> dict:
    deadline = time.time() + seconds
    last = "no response"
    while time.time() < deadline:
        try:
            value = local_bridge_get("/adaptive/status", timeout=4.0)
            if bool(value.get("ok")) and bool(value.get("worker_started")):
                return value
            last = "adaptive worker has not started"
        except Exception as exc:
            last = str(exc)
        time.sleep(1.0)
    raise RuntimeError(f"Adaptive learning worker did not prove liveness: {last}")


def launch(path: Path, cwd: Path | None = None, args: list[str] | None = None) -> None:
    if not path.exists():
        raise RuntimeError(f"Runtime executable missing after install: {path.name}")
    child_env = os.environ.copy()
    child_env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    subprocess.Popen(
        [str(path), *(args or [])],
        cwd=str(cwd or path.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        env=child_env,
    )


def verify_package(pkg: Path) -> None:
    for name in ROOT_FILES:
        if not (pkg / name).exists():
            raise RuntimeError(f"Package file missing: {name}")
    for name in RUNTIME_DIRS:
        if not (pkg / name).is_dir():
            raise RuntimeError(f"Package runtime folder missing: {name}")
    required = (
        pkg / "VexMemoryWorkerRuntime" / "VexMemoryWorker.exe",
        pkg / "VexRemoteSupportRuntime" / "VexRemoteSupport.exe",
        pkg / "VexWindowsHost" / "VexWindowsHost.exe",
        pkg / "VexNodeAgent" / "VexNodeAgent.exe",
    )
    for path in required:
        if not path.exists():
            raise RuntimeError(f"Package executable missing: {path.name}")


def main() -> None:
    root = Tk()
    root.withdraw()
    try:
        pkg = package_dir()
        verify_package(pkg)
        home = find_home()
        stop_known_vex_processes()

        for name in ROOT_FILES:
            replace_file(pkg / name, home / name)
        for name in RUNTIME_DIRS:
            replace_dir(pkg / name, home / name)

        try:
            (home / "VexMemoryWorker.exe").unlink(missing_ok=True)
        except Exception:
            pass

        # Persistent memory is an independent local sidecar, not a child that must
        # be cold-started inside the first Bridge request. This keeps the first phone
        # turn responsive and lets Bridge reconnect to the same durable memory DB.
        memory_exe = home / "VexMemoryWorkerRuntime" / "VexMemoryWorker.exe"
        launch(memory_exe, memory_exe.parent, ["--serve", "--port", str(MEMORY_PORT)])
        wait_direct_memory()

        # Preserve APPDATA/LOCALAPPDATA private configuration, pairing, memory DB,
        # searchable folders and continuity. Public package contains none of it.
        launch(home / "VexBridge.exe", home)
        wait_bridge()
        memory = wait_memory()
        adaptive = wait_adaptive()

        launch(home / "VexRemoteSupportRuntime" / "VexRemoteSupport.exe", home / "VexRemoteSupportRuntime")
        launch(home / "VexWindowsHost" / "VexWindowsHost.exe", home / "VexWindowsHost")
        launch(home / "VexNodeAgent" / "VexNodeAgent.exe", home / "VexNodeAgent")

        messagebox.showinfo(
            "Vex Agent Runtime",
            "Vex Agent Runtime v0.11.7.49 installed.\n\n"
            f"Bridge {BRIDGE_VERSION}: ready\n"
            f"Persistent memory: ready ({memory.get('version') or 'local'})\n"
            f"Adaptive worker: started ({adaptive.get('review_mode') or 'local'})\n"
            f"Windows Host {HOST_VERSION}: started\n"
            "Remote Support: started\n\n"
            "Keep VexNative v0.11.7.48 on the iPhone; its working pairing is preserved.",
        )
    except Exception as exc:
        messagebox.showerror("Vex Agent Runtime", f"Install failed safely: {exc}")
        raise
    finally:
        root.destroy()


if __name__ == "__main__":
    main()
