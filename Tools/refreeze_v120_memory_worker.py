#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path.cwd()
DIST = ROOT / "dist" / "VexMemoryWorker"
PKG = ROOT / "Vex-Agent-Runtime-v0.12.0-FullAIFoundation" / "VexMemoryWorkerRuntime"
EMBEDDED = ROOT / "dist" / "VexBridge" / "VexMemoryWorkerRuntime"
SOURCE = ROOT / "Tools" / "VexMemoryWorker.py"


def run(*args: str) -> None:
    print("[v120-memory-refreeze] RUN " + " ".join(args), flush=True)
    subprocess.run(list(args), cwd=ROOT, check=True)


def replace_tree(source: Path, destination: Path) -> None:
    shutil.rmtree(destination, ignore_errors=True)
    shutil.copytree(source, destination)


source = SOURCE.read_text(encoding="utf-8")
for marker in [
    'V120_MEMORY_WINDOWS_FILE_LOCK = "v0.12-memory-windows-file-lock-v4"',
    "msvcrt.LK_NBLCK",
    "file lock already held",
]:
    if marker not in source:
        raise SystemExit(f"memory singleton source marker missing: {marker}")

pyinstaller = shutil.which("pyinstaller")
if not pyinstaller:
    raise SystemExit("pyinstaller missing")

shutil.rmtree(DIST, ignore_errors=True)
shutil.rmtree(ROOT / "build" / "VexMemoryWorker", ignore_errors=True)
run(
    pyinstaller,
    "--noconfirm", "--clean", "--onedir",
    "--contents-directory", "VexMemoryRuntime",
    "--noupx", "--windowed", "--name", "VexMemoryWorker",
    "--hidden-import", "sqlite3",
    "Tools/VexMemoryWorker.py",
)

exe = DIST / "VexMemoryWorker.exe"
if not exe.exists():
    raise SystemExit(f"frozen worker missing: {exe}")
replace_tree(DIST, PKG)
if EMBEDDED.parent.exists():
    replace_tree(DIST, EMBEDDED)

# Behavioral proof against the packaged executable: one owner survives and five
# competing launches must exit. This catches a patched source with a stale EXE.
base = Path(tempfile.mkdtemp(prefix="VexMemorySingleton-"))
roaming = base / "Roaming"
local = base / "Local"
roaming.mkdir(parents=True, exist_ok=True)
local.mkdir(parents=True, exist_ok=True)
env = os.environ.copy()
env["APPDATA"] = str(roaming)
env["LOCALAPPDATA"] = str(local)

probe = socket.socket()
probe.bind(("127.0.0.1", 0))
port = int(probe.getsockname()[1])
probe.close()
worker = PKG / "VexMemoryWorker.exe"
owner = None
competitors: list[subprocess.Popen] = []
try:
    owner = subprocess.Popen([str(worker), "--serve", "--port", str(port)], cwd=str(PKG), env=env)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.time() + 30
    while time.time() < deadline:
        if owner.poll() is not None:
            raise RuntimeError(f"owner exited early rc={owner.returncode}")
        try:
            with opener.open(f"http://127.0.0.1:{port}/health", timeout=2) as response:
                if response.status == 200:
                    break
        except Exception:
            time.sleep(0.25)
    else:
        raise RuntimeError("owner never became healthy")

    for _ in range(5):
        competitors.append(subprocess.Popen([str(worker), "--serve", "--port", str(port)], cwd=str(PKG), env=env))
    deadline = time.time() + 8
    while time.time() < deadline and any(p.poll() is None for p in competitors):
        time.sleep(0.2)
    alive = [p.pid for p in competitors if p.poll() is None]
    if alive:
        raise RuntimeError(f"singleton failed; competing workers survived: {alive}")
    if owner.poll() is not None:
        raise RuntimeError(f"singleton owner died rc={owner.returncode}")
    print("PASS frozen VexMemoryWorker singleton: 1 owner + 5 rejected competitors", flush=True)
finally:
    for proc in competitors:
        if proc.poll() is None:
            proc.kill()
    if owner is not None and owner.poll() is None:
        owner.kill()
    shutil.rmtree(base, ignore_errors=True)
