#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import py_compile
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path.cwd()
DIST = ROOT / "dist"
PKG_NAME = "Vex-Agent-Runtime-v0.11.7.49-Greenline"
ZIP_PATH = ROOT / f"{PKG_NAME}.zip"


def log(msg: str) -> None:
    print(f"[greenline] {msg}", flush=True)


def run(*args: str) -> None:
    log("RUN " + " ".join(args))
    subprocess.run(list(args), cwd=ROOT, check=True)


def kill(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    try:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _ps_quote(value: str | Path) -> str:
    return str(value).replace("'", "''")


def start_windows_process(exe: Path, cwd: Path | None = None, env: dict | None = None) -> int:
    """Launch a frozen GUI executable with the same Start-Process path proven by earlier Greenline."""
    work = cwd or exe.parent
    script = (
        "$ErrorActionPreference='Stop'; "
        f"$p=Start-Process -FilePath '{_ps_quote(exe)}' "
        f"-WorkingDirectory '{_ps_quote(work)}' -PassThru; "
        "Write-Output $p.Id"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        cwd=str(work),
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(f"Windows launcher returned no PID for {exe.name}")
    pid = int(lines[-1])
    log(f"Windows launched {exe.name} as PID {pid}")
    return pid


def windows_process_alive(pid: int) -> bool:
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            f"if (Get-Process -Id {int(pid)} -ErrorAction SilentlyContinue) {{ exit 0 }} else {{ exit 1 }}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def stop_windows_process(pid: int | None) -> None:
    if not pid:
        return
    subprocess.run(
        ["taskkill.exe", "/PID", str(int(pid)), "/T", "/F"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def no_proxy_opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def get_json(url: str, timeout: float = 3.0) -> dict:
    with no_proxy_opener().open(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def wait_json(url: str, predicate, seconds: float, label: str) -> dict:
    deadline = time.time() + seconds
    last = None
    while time.time() < deadline:
        try:
            value = get_json(url, timeout=2.5)
            if predicate(value):
                log(f"{label}: {value}")
                return value
            last = value
        except Exception as exc:
            last = f"{exc.__class__.__name__}: {exc}"
        time.sleep(0.5)
    raise RuntimeError(f"{label} never became ready: {last}")


def isolated_env(name: str) -> dict:
    base = Path(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()) / name
    roaming = base / "Roaming"
    local = base / "Local"
    roaming.mkdir(parents=True, exist_ok=True)
    local.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["APPDATA"] = str(roaming)
    env["LOCALAPPDATA"] = str(local)
    return env


def popen(exe: Path, args: list[str] | None = None, cwd: Path | None = None, env: dict | None = None):
    return subprocess.Popen(
        [str(exe)] + list(args or []),
        cwd=str(cwd or exe.parent),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def assemble_source() -> None:
    scripts = [
        "Tools/build_v11728_chain.py",
        "Tools/apply_v11729_windows_defender_safe.py",
        "Tools/apply_v11729_bridge_onedir_hotfix.py",
        "Tools/apply_v11734_bridge_responsive_boot.py",
        "Tools/apply_v11737_ollama_recovery.py",
        "Tools/apply_v11738_cognition_capacity_hotfix.py",
        "Tools/apply_v11739_cognition_helper_bundle.py",
        "Tools/apply_v11749_agent_runtime_foundation.py",
        "Tools/apply_v11736_host_clipboard.py",
        "Tools/apply_v11740_host_phone_ping.py",
    ]
    for script in scripts:
        run(sys.executable, script)

    compile_paths = [
        "Bridge/vex_bridge.py",
        "Tools/VexMemoryWorker.py",
        "Tools/VexDoctor.py",
        "Tools/VexToolbox.py",
        "Tools/VexRemoteSupport.py",
        "Tools/VexWindowsHost-v11740.py",
        "Tools/VexNodeAgent.py",
        "Tools/VexAgentRuntimeInstall.py",
    ]
    for path in compile_paths:
        py_compile.compile(path, doraise=True)

    bridge = (ROOT / "Bridge/vex_bridge.py").read_text("utf-8")
    for marker in [
        '"version": "0.11.7.39"',
        '"agent_runtime_bundle": "0.11.7.49"',
        "MEMORY_WORKER_PORT = 8806",
        'parsed.path == "/memory/status"',
        'if parsed.path == "/adaptive/status"',
        'name="VexAdaptiveLearning"',
        'name="VexAutonomousImprovement"',
        'name="VexInitiativeScheduler"',
        "_vex_background_services()",
    ]:
        if marker not in bridge:
            raise RuntimeError(f"Agent Runtime marker missing: {marker}")

    installer = (ROOT / "Tools/VexAgentRuntimeInstall.py").read_text("utf-8")
    for marker in ["MEMORY_PORT = 8806", "wait_direct_memory()", "VexMemoryWorkerRuntime"]:
        if marker not in installer:
            raise RuntimeError(f"installer marker missing: {marker}")


def build_components() -> None:
    pyinstaller = shutil.which("pyinstaller")
    if not pyinstaller:
        raise RuntimeError("pyinstaller is not on PATH")

    commands = [
        [pyinstaller, "--noconfirm", "--clean", "--onedir", "--contents-directory", "VexBridgeRuntime", "--noupx", "--windowed", "--name", "VexBridge", "--collect-all", "requests", "--collect-all", "bs4", "--collect-all", "pypdf", "--collect-all", "cryptography", "Bridge/vex_bridge.py"],
        [pyinstaller, "--noconfirm", "--clean", "--onedir", "--contents-directory", "VexMemoryRuntime", "--noupx", "--windowed", "--name", "VexMemoryWorker", "--hidden-import", "sqlite3", "Tools/VexMemoryWorker.py"],
        [pyinstaller, "--noconfirm", "--clean", "--onefile", "--noupx", "--console", "--name", "VexDoctor", "--collect-all", "requests", "--hidden-import", "sqlite3", "Tools/VexDoctor.py"],
        [pyinstaller, "--noconfirm", "--clean", "--onefile", "--noupx", "--windowed", "--name", "VexToolbox", "--hidden-import", "tkinter", "Tools/VexToolbox.py"],
        [pyinstaller, "--noconfirm", "--clean", "--onedir", "--noupx", "--windowed", "--name", "VexRemoteSupport", "--collect-all", "requests", "Tools/VexRemoteSupport.py"],
        [pyinstaller, "--noconfirm", "--clean", "--onedir", "--noupx", "--windowed", "--name", "VexWindowsHost", "--collect-all", "requests", "Tools/VexWindowsHost-v11740.py"],
        [pyinstaller, "--noconfirm", "--clean", "--onedir", "--noupx", "--windowed", "--name", "VexNodeAgent", "Tools/VexNodeAgent.py"],
        [pyinstaller, "--noconfirm", "--clean", "--onefile", "--noupx", "--windowed", "--name", "Install-Vex-Agent-Runtime-v0.11.7.49", "Tools/VexAgentRuntimeInstall.py"],
    ]
    for command in commands:
        run(*command)

    embedded = DIST / "VexBridge" / "VexMemoryWorkerRuntime"
    shutil.rmtree(embedded, ignore_errors=True)
    shutil.copytree(DIST / "VexMemoryWorker", embedded)

    required = [
        DIST / "VexBridge/VexBridge.exe",
        embedded / "VexMemoryWorker.exe",
        DIST / "VexDoctor.exe",
        DIST / "VexToolbox.exe",
        DIST / "VexRemoteSupport/VexRemoteSupport.exe",
        DIST / "VexWindowsHost/VexWindowsHost.exe",
        DIST / "VexNodeAgent/VexNodeAgent.exe",
        DIST / "Install-Vex-Agent-Runtime-v0.11.7.49.exe",
    ]
    for path in required:
        if not path.exists():
            raise RuntimeError(f"built component missing: {path}")


def smoke_memory_worker() -> None:
    env = isolated_env("VexAgentMemorySmoke")
    worker = DIST / "VexMemoryWorker/VexMemoryWorker.exe"
    proc = popen(worker, ["--serve", "--port", "8806"], env=env)
    try:
        wait_json("http://127.0.0.1:8806/health", lambda d: d.get("ok") is True, 25, "memory worker")
    finally:
        kill(proc)


def smoke_staged_memory() -> None:
    env = isolated_env("VexAgentMemoryStagedSmoke")
    worker = DIST / "VexBridge/VexMemoryWorkerRuntime/VexMemoryWorker.exe"
    proc = popen(worker, ["--serve", "--port", "8806"], env=env)
    try:
        wait_json("http://127.0.0.1:8806/health", lambda d: d.get("ok") is True, 25, "staged memory")
    finally:
        kill(proc)


def local_control_request(config_path: Path, path: str) -> dict:
    cfg = json.loads(config_path.read_text("utf-8"))
    token = str(cfg.get("token") or "")
    port = int(cfg.get("local_control_port") or 0)
    if not token or not port:
        raise RuntimeError("local control identity not persisted yet")
    url = f"http://127.0.0.1:{port}{path}?" + urllib.parse.urlencode({"token": token})
    try:
        return get_json(url, timeout=5)
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except Exception:
            body = {"ok": False, "error": f"HTTP {exc.code}"}
        if isinstance(body, dict):
            body["http_status"] = exc.code
        return body


def bridge_failure_detail(env: dict, pid: int | None) -> str:
    details = [f"process_alive={windows_process_alive(pid) if pid else False}"]
    startup = Path(env["APPDATA"]) / "VexBridge/startup-health.json"
    try:
        details.append("startup=" + startup.read_text("utf-8")[:500])
    except Exception as exc:
        details.append(f"startup_unavailable={exc.__class__.__name__}")
    return "; ".join(details)


def smoke_bridge_agent_runtime() -> None:
    env = isolated_env("VexAgentBridgeSmoke")
    memory = DIST / "VexBridge/VexMemoryWorkerRuntime/VexMemoryWorker.exe"
    bridge = DIST / "VexBridge/VexBridge.exe"
    mp = popen(memory, ["--serve", "--port", "8806"], env=env)
    bridge_pid = None
    try:
        wait_json("http://127.0.0.1:8806/health", lambda d: d.get("ok") is True, 25, "production memory sidecar")
        bridge_pid = start_windows_process(bridge, cwd=bridge.parent, env=env)
        config_path = Path(env["APPDATA"]) / "VexBridge/config.json"
        deadline = time.time() + 80
        last = None
        while time.time() < deadline:
            try:
                if not config_path.exists():
                    raise RuntimeError("config not created")
                status = local_control_request(config_path, "/status")
                if status.get("version") == "0.11.7.39" and status.get("local_control_protocol") == "vex-local-v1":
                    log(f"Bridge status: {status}")
                    break
                last = status
            except Exception as exc:
                last = f"{exc.__class__.__name__}: {exc}"
            if bridge_pid and not windows_process_alive(bridge_pid):
                raise RuntimeError(f"Bridge exited before ready: {bridge_failure_detail(env, bridge_pid)}; last={last}")
            time.sleep(0.5)
        else:
            raise RuntimeError(f"Bridge never became ready: {last}; {bridge_failure_detail(env, bridge_pid)}")

        memory_status = local_control_request(config_path, "/memory/status")
        if not memory_status.get("ok"):
            raise RuntimeError(f"Bridge could not see memory sidecar: {memory_status}")
        log(f"Bridge memory status: {memory_status}")

        deadline = time.time() + 45
        last = None
        while time.time() < deadline:
            adaptive = local_control_request(config_path, "/adaptive/status")
            if adaptive.get("ok") and adaptive.get("worker_started") and adaptive.get("worker_alive"):
                log(f"Adaptive status: {adaptive}")
                return
            last = adaptive
            time.sleep(0.5)
        raise RuntimeError(f"Adaptive worker liveness failed: {last}")
    finally:
        stop_windows_process(bridge_pid)
        kill(mp)


def smoke_user_processes() -> None:
    tests = [
        (DIST / "VexRemoteSupport/VexRemoteSupport.exe", 7, "Remote Support"),
        (DIST / "VexWindowsHost/VexWindowsHost.exe", 6, "Windows Host"),
    ]
    for exe, seconds, label in tests:
        pid = start_windows_process(exe, cwd=exe.parent)
        try:
            time.sleep(seconds)
            if not windows_process_alive(pid):
                raise RuntimeError(f"{label} exited during startup")
            log(f"{label} remained alive for {seconds}s")
        finally:
            stop_windows_process(pid)


def package_runtime() -> None:
    pkg = ROOT / PKG_NAME
    verify = ROOT / "verify-package"
    shutil.rmtree(pkg, ignore_errors=True)
    shutil.rmtree(verify, ignore_errors=True)
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    pkg.mkdir()

    shutil.copy2(DIST / "VexBridge/VexBridge.exe", pkg / "VexBridge.exe")
    shutil.copytree(DIST / "VexBridge/VexBridgeRuntime", pkg / "VexBridgeRuntime")
    shutil.copytree(DIST / "VexMemoryWorker", pkg / "VexMemoryWorkerRuntime")
    shutil.copy2(DIST / "VexDoctor.exe", pkg / "VexDoctor.exe")
    shutil.copy2(DIST / "VexToolbox.exe", pkg / "VexToolbox.exe")
    shutil.copytree(DIST / "VexRemoteSupport", pkg / "VexRemoteSupportRuntime")
    shutil.copytree(DIST / "VexWindowsHost", pkg / "VexWindowsHost")
    shutil.copytree(DIST / "VexNodeAgent", pkg / "VexNodeAgent")
    shutil.copy2(DIST / "Install-Vex-Agent-Runtime-v0.11.7.49.exe", pkg / "Install-Vex-Agent-Runtime-v0.11.7.49.exe")
    (pkg / "README.txt").write_text(
        "Vex Agent Runtime v0.11.7.49 Greenline\n"
        "Production-shaped Agent Runtime around the proven v0.11.7.39 PC cognition Bridge and working v0.11.7.48 iPhone pairing.\n"
        "Persistent memory runs as a local-only sidecar on 127.0.0.1:8806 and starts before Bridge.\n"
        "Includes persistent memory, adaptive learning, autonomous improvement, initiative scheduling, Remote Support, Windows Host, Node Agent and diagnostics.\n"
        "No paid API or cloud inference is introduced. Private pairing, profile and memory data remain local.\n"
        "Extract completely, then run Install-Vex-Agent-Runtime-v0.11.7.49.exe.\n",
        encoding="utf-8",
    )

    shutil.make_archive(str(ROOT / PKG_NAME), "zip", root_dir=pkg)
    shutil.unpack_archive(str(ZIP_PATH), verify, "zip")
    required = [
        verify / "VexBridge.exe",
        verify / "VexMemoryWorkerRuntime/VexMemoryWorker.exe",
        verify / "VexRemoteSupportRuntime/VexRemoteSupport.exe",
        verify / "VexWindowsHost/VexWindowsHost.exe",
        verify / "VexNodeAgent/VexNodeAgent.exe",
        verify / "Install-Vex-Agent-Runtime-v0.11.7.49.exe",
        verify / "README.txt",
    ]
    for path in required:
        if not path.exists():
            raise RuntimeError(f"package verification missing: {path}")
    if ZIP_PATH.stat().st_size < 100_000:
        raise RuntimeError("packaged runtime zip is unexpectedly small")
    log(f"package ready: {ZIP_PATH.name} ({ZIP_PATH.stat().st_size} bytes)")


def main() -> int:
    assemble_source()
    build_components()
    smoke_memory_worker()
    smoke_staged_memory()
    smoke_bridge_agent_runtime()
    smoke_user_processes()
    package_runtime()
    log("ALL GREENLINE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
