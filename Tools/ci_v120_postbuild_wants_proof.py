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
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path.cwd()
DIST = ROOT / "dist"
PKG_NAME = "Vex-Agent-Runtime-v0.12.0-FullAIFoundation"
PKG = ROOT / PKG_NAME
ZIP = ROOT / f"{PKG_NAME}.zip"
VERIFY = ROOT / "verify-package"
FIELD = "74"


def log(message: str) -> None:
    print(f"[v120-postbuild] {message}", flush=True)


def run(*args: str) -> None:
    log("RUN " + " ".join(args))
    subprocess.run(list(args), cwd=ROOT, check=True)


def replace_tree(source: Path, destination: Path) -> None:
    shutil.rmtree(destination, ignore_errors=True)
    shutil.copytree(source, destination)


def start_gui(exe: Path) -> int:
    command = (
        "$ErrorActionPreference='Stop'; "
        f"$p=Start-Process -FilePath '{str(exe).replace(chr(39), chr(39)*2)}' "
        f"-WorkingDirectory '{str(exe.parent).replace(chr(39), chr(39)*2)}' -PassThru; "
        "$p.Id"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        check=True,
    )
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(f"no PID returned for {exe}")
    return int(lines[-1])


def stop_pid(pid: int | None) -> None:
    if not pid:
        return
    subprocess.run(
        ["taskkill.exe", "/PID", str(pid), "/T", "/F"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def window_title(pid: int) -> str:
    command = f"$p=Get-Process -Id {pid} -ErrorAction SilentlyContinue; if ($p) {{ $p.MainWindowTitle }}"
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def prove_host_from_zip() -> None:
    exe = VERIFY / "VexWindowsHost" / "VexWindowsHost.exe"
    if not exe.exists():
        raise RuntimeError(f"rewritten ZIP Host missing: {exe}")
    pid = start_gui(exe)
    try:
        deadline = time.time() + 20
        last = ""
        while time.time() < deadline:
            last = window_title(pid)
            if f"wants{FIELD}" in last:
                log(f"PASS final ZIP Host title: {last}")
                return
            time.sleep(0.5)
        raise RuntimeError(f"final ZIP Host lacks wants{FIELD} title fingerprint; title={last!r}")
    finally:
        stop_pid(pid)


def no_proxy_json(url: str, timeout: float = 3.0) -> dict:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def prove_bridge_from_zip() -> None:
    exe = VERIFY / "VexBridge.exe"
    if not exe.exists():
        raise RuntimeError(f"rewritten ZIP Bridge missing: {exe}")
    base = Path(tempfile.mkdtemp(prefix="VexWants74-"))
    roaming = base / "Roaming"
    local = base / "Local"
    roaming.mkdir(parents=True, exist_ok=True)
    local.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["APPDATA"] = str(roaming)
    env["LOCALAPPDATA"] = str(local)
    proc = subprocess.Popen(
        [str(exe)],
        cwd=str(VERIFY),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        config = roaming / "VexBridge" / "config.json"
        deadline = time.time() + 35
        last = "config not created"
        while time.time() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(f"rewritten ZIP Bridge exited early rc={proc.returncode}")
            try:
                if not config.exists():
                    raise RuntimeError("config not created")
                cfg = json.loads(config.read_text(encoding="utf-8"))
                token = str(cfg.get("token") or "")
                port = int(cfg.get("local_control_port") or 0)
                if not token or not port:
                    raise RuntimeError("local-control identity incomplete")
                query = urllib.parse.urlencode({"token": token})
                status = no_proxy_json(f"http://127.0.0.1:{port}/status?{query}", timeout=3)
                if str(status.get("agent_runtime_bundle") or "") != "0.12.0":
                    raise RuntimeError(f"runtime bundle mismatch: {status}")
                requests_view = no_proxy_json(f"http://127.0.0.1:{port}/autonomy/requests?{query}", timeout=5)
                if requests_view.get("ok") is not True:
                    raise RuntimeError(f"local requests endpoint failed: {requests_view}")
                if not isinstance(requests_view.get("reconciliation"), dict):
                    raise RuntimeError(f"correctness reconciliation missing from local requests: {requests_view}")
                log("PASS final ZIP Bridge v0.12 + authenticated local requests + Wants reconciliation")
                return
            except Exception as exc:
                last = f"{exc.__class__.__name__}: {exc}"
                time.sleep(0.5)
        raise RuntimeError(f"rewritten ZIP Bridge proof timed out: {last}")
    finally:
        stop_pid(proc.pid)
        shutil.rmtree(base, ignore_errors=True)


def main() -> int:
    if not PKG.exists() or not ZIP.exists():
        raise RuntimeError("normal v0.12 package must exist before post-build proof")

    # Apply local-only UI and correctness work only after every legacy source
    # generator has finished. Then re-freeze the actual files we ship.
    run(sys.executable, "Tools/apply_v120_local_upgrade_requests.py")
    run(sys.executable, "Tools/apply_v120_wants_field_fingerprint.py")
    run(sys.executable, "apply_v120_correctness_upgrades.py")

    host_source = ROOT / "Tools" / "VexWindowsHost-v11740.py"
    bridge_source = ROOT / "Bridge" / "vex_bridge.py"
    py_compile.compile(str(host_source), doraise=True)
    py_compile.compile(str(bridge_source), doraise=True)
    host_text = host_source.read_text(encoding="utf-8")
    bridge_text = bridge_source.read_text(encoding="utf-8")
    for marker in [
        f"wants{FIELD}",
        'text="Vex wants / upgrade requests"',
        "def show_vex_wants(self):",
        'bridge_get("/autonomy/requests", timeout=8)',
    ]:
        if marker not in host_text:
            raise RuntimeError(f"post-build Host source marker missing: {marker}")
    for marker in [
        f'"vex_wants_field_build": "{FIELD}"',
        "def _v120_local_upgrade_requests() -> dict:",
        'parsed.path == "/autonomy/requests"',
        'V120_CORRECTNESS_UPGRADES = "v0.12-wants-reconcile-renderer-v1"',
        "def _v120_reconcile_wants() -> dict:",
        "V120_FACT_PRESERVING_RECALL",
    ]:
        if marker not in bridge_text:
            raise RuntimeError(f"post-build Bridge source marker missing: {marker}")

    pyinstaller = shutil.which("pyinstaller")
    if not pyinstaller:
        raise RuntimeError("pyinstaller is not on PATH")

    # Re-freeze only the two components changed by the post-build patches.
    shutil.rmtree(DIST / "VexBridge", ignore_errors=True)
    shutil.rmtree(DIST / "VexWindowsHost", ignore_errors=True)
    shutil.rmtree(ROOT / "build" / "VexBridge", ignore_errors=True)
    shutil.rmtree(ROOT / "build" / "VexWindowsHost", ignore_errors=True)

    run(
        pyinstaller, "--noconfirm", "--clean", "--onedir", "--contents-directory", "VexBridgeRuntime",
        "--noupx", "--windowed", "--name", "VexBridge", "--collect-all", "requests",
        "--collect-all", "bs4", "--collect-all", "pypdf", "--collect-all", "cryptography",
        "Bridge/vex_bridge.py",
    )
    run(
        pyinstaller, "--noconfirm", "--clean", "--onedir", "--noupx", "--windowed",
        "--name", "VexWindowsHost", "--collect-all", "requests", "Tools/VexWindowsHost-v11740.py",
    )

    # Keep the Bridge's staged memory-worker layout consistent with the normal build.
    embedded = DIST / "VexBridge" / "VexMemoryWorkerRuntime"
    shutil.rmtree(embedded, ignore_errors=True)
    shutil.copytree(DIST / "VexMemoryWorker", embedded)

    # Rewrite the already-complete package rather than regenerating all legacy components.
    shutil.copy2(DIST / "VexBridge" / "VexBridge.exe", PKG / "VexBridge.exe")
    replace_tree(DIST / "VexBridge" / "VexBridgeRuntime", PKG / "VexBridgeRuntime")
    replace_tree(DIST / "VexWindowsHost", PKG / "VexWindowsHost")

    if ZIP.exists():
        ZIP.unlink()
    shutil.make_archive(str(ROOT / PKG_NAME), "zip", root_dir=PKG)
    shutil.rmtree(VERIFY, ignore_errors=True)
    shutil.unpack_archive(str(ZIP), VERIFY, "zip")

    prove_host_from_zip()
    prove_bridge_from_zip()
    log(f"PASS final rewritten artifact is field-proven wants{FIELD} + correctness-v1: {ZIP.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
