#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path.cwd()
PHRASE = "Remember this exact test phrase for me: violet raccoon 731."
EXPECTED = "violet raccoon 731."


def opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def get_json(url: str, timeout: float = 3.0) -> dict:
    with opener().open(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, payload: dict, timeout: float = 5.0) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with opener().open(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def safe_text(value) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def wait_json(url: str, predicate, seconds: float, label: str) -> dict:
    deadline = time.time() + seconds
    last = None
    while time.time() < deadline:
        try:
            value = get_json(url, 2.5)
            if predicate(value):
                print(f"[v11751-test] {label}: {safe_text(value)}", flush=True)
                return value
            last = value
        except Exception as exc:
            last = f"{exc.__class__.__name__}: {exc}"
        time.sleep(0.4)
    raise RuntimeError(f"{label} never became ready: {last}")


def ps_quote(value: str | Path) -> str:
    return str(value).replace("'", "''")


def start_windows_process(exe: Path, env: dict) -> int:
    script = (
        "$ErrorActionPreference='Stop'; "
        f"$p=Start-Process -FilePath '{ps_quote(exe)}' "
        f"-WorkingDirectory '{ps_quote(exe.parent)}' -PassThru; "
        "Write-Output $p.Id"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        cwd=str(exe.parent),
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("Bridge launcher returned no PID")
    return int(lines[-1])


def stop_pid(pid: int | None) -> None:
    if not pid:
        return
    subprocess.run(["taskkill.exe", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def main() -> None:
    source = (ROOT / "Bridge/vex_bridge.py").read_text("utf-8")
    for marker in [
        "def _explicit_memory_write_value(message: str) -> str | None:",
        "def _explicit_memory_store(value: str) -> bool:",
        '"explicit-personal-memory-write-v11751"',
        '"memory_write": bool(stored)',
        '"agent_runtime_bundle": "0.11.7.51"',
    ]:
        if marker not in source:
            raise RuntimeError(f"generated Bridge missing .51 marker: {marker}")

    base = Path(tempfile.mkdtemp(prefix="Vex11751MemoryWrite-"))
    roaming = base / "Roaming"
    local = base / "Local"
    roaming.mkdir(parents=True)
    local.mkdir(parents=True)
    env = os.environ.copy()
    env["APPDATA"] = str(roaming)
    env["LOCALAPPDATA"] = str(local)
    env["PYTHONUTF8"] = "0"
    env["PYTHONIOENCODING"] = "cp1252"

    memory_exe = ROOT / "dist/VexMemoryWorker/VexMemoryWorker.exe"
    bridge_exe = ROOT / "dist/VexBridge/VexBridge.exe"
    if not memory_exe.exists() or not bridge_exe.exists():
        raise RuntimeError("built .51 executables missing")

    memory = subprocess.Popen(
        [str(memory_exe), "--serve", "--port", "8806"],
        cwd=str(memory_exe.parent),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    bridge_pid = None
    try:
        wait_json("http://127.0.0.1:8806/health", lambda d: d.get("ok") is True, 30, "memory worker")
        bridge_pid = start_windows_process(bridge_exe, env)

        config_path = roaming / "VexBridge/config.json"
        deadline = time.time() + 90
        cfg = None
        while time.time() < deadline:
            try:
                if config_path.exists():
                    candidate = json.loads(config_path.read_text("utf-8"))
                    if candidate.get("token") and candidate.get("local_control_port"):
                        cfg = candidate
                        break
            except Exception:
                pass
            time.sleep(0.4)
        if not cfg:
            raise RuntimeError("Bridge local-control identity was not persisted")

        token = str(cfg["token"])
        port = int(cfg["local_control_port"])
        query = urllib.parse.urlencode({"token": token})
        status_url = f"http://127.0.0.1:{port}/status?{query}"
        wait_json(status_url, lambda d: d.get("version") == "0.11.7.39", 60, "Bridge status")

        chat_url = f"http://127.0.0.1:{port}/llm/chat?{query}"
        result = post_json(chat_url, {"message": PHRASE, "history": []}, timeout=12)
        print(f"[v11751-test] write reply: {safe_text(result)}", flush=True)
        if result.get("memory_write") is not True:
            raise RuntimeError(f"explicit write was not verified: {safe_text(result)}")
        if result.get("grounding") != "explicit-personal-memory-write-v11751":
            raise RuntimeError(f"explicit write fell into the wrong router: {safe_text(result)}")

        recalled = post_json(
            "http://127.0.0.1:8806/search",
            {"query": EXPECTED, "memory_limit": 16, "episode_limit": 0},
            timeout=5,
        )
        memories = recalled.get("memories") if isinstance(recalled.get("memories"), list) else []
        exact = any(str(item.get("text") or "").strip().casefold() == EXPECTED.casefold() for item in memories if isinstance(item, dict))
        if not exact:
            raise RuntimeError(f"written phrase did not read back from persistent memory: {safe_text(recalled)}")
        print("[v11751-test] PASS explicit remember -> trusted write -> readback", flush=True)
    finally:
        stop_pid(bridge_pid)
        try:
            memory.terminate()
            memory.wait(timeout=5)
        except Exception:
            try:
                memory.kill()
            except Exception:
                pass
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    main()
