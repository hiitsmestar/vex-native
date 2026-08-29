#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path.cwd()
SAVE = "Remember this test fact: my imaginary fox is named Mica"
CORRECT = "Correction: my imaginary fox is named Nyx, not Mica. Replace the old fact and remember Nyx as the current name."
RECALL = "What is my imaginary fox's current name?"
OLD = "my imaginary fox is named Mica"
NEW = "my imaginary fox is named Nyx"


def opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def get_json(url, timeout=3):
    with opener().open(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def post_json(url, payload, timeout=8):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with opener().open(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body}") from exc


def wait_json(url, predicate, seconds, label):
    deadline = time.time() + seconds
    last = None
    while time.time() < deadline:
        try:
            value = get_json(url, 2.5)
            if predicate(value):
                return value
            last = value
        except Exception as exc:
            last = f"{type(exc).__name__}: {exc}"
        time.sleep(0.4)
    raise RuntimeError(f"{label} not ready: {last}")


def psq(value):
    return str(value).replace("'", "''")


def start_win(exe, env):
    script = f"$p=Start-Process -FilePath '{psq(exe)}' -WorkingDirectory '{psq(exe.parent)}' -PassThru; Write-Output $p.Id"
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], env=env, text=True, capture_output=True, check=True)
    return int([x.strip() for x in result.stdout.splitlines() if x.strip()][-1])


def stop(pid):
    if pid:
        subprocess.run(["taskkill.exe", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    src = (ROOT / "Bridge/vex_bridge.py").read_text("utf-8")
    for marker in [
        "explicit-personal-memory-write-v11751",
        "explicit-personal-memory-correction-v11752",
        '"memory_correction": bool(replaced)',
        '"agent_runtime_bundle": "0.11.7.56"',
        "PROJECT_LEARNING_DB",
        "def _windows_native_capabilities(",
        "PROJECT_PROPOSAL_PER_TASK_CAP = 6",
        "_v11756_windows_native_capabilities_base",
    ]:
        if marker not in src:
            raise RuntimeError(f"missing .56 memory/project/native marker: {marker}")

    base = Path(tempfile.mkdtemp(prefix="Vex11756MemoryRegression-"))
    roam, local = base / "Roaming", base / "Local"
    roam.mkdir(); local.mkdir()
    env = os.environ.copy()
    env.update({"APPDATA": str(roam), "LOCALAPPDATA": str(local), "PYTHONUTF8": "0", "PYTHONIOENCODING": "cp1252"})
    mem = ROOT / "dist/VexMemoryWorker/VexMemoryWorker.exe"
    bridge = ROOT / "dist/VexBridge/VexBridge.exe"
    mp = subprocess.Popen([str(mem), "--serve", "--port", "8806"], cwd=str(mem.parent), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    bp = None
    try:
        wait_json("http://127.0.0.1:8806/health", lambda d: d.get("ok") is True, 30, "memory")
        bp = start_win(bridge, env)
        cfgp = roam / "VexBridge/config.json"
        deadline = time.time() + 90
        cfg = None
        while time.time() < deadline:
            try:
                if cfgp.exists():
                    candidate = json.loads(cfgp.read_text("utf-8"))
                    if candidate.get("token") and candidate.get("local_control_port"):
                        cfg = candidate
                        break
            except Exception:
                pass
            time.sleep(0.4)
        if not cfg:
            raise RuntimeError("Bridge config missing")
        query = urllib.parse.urlencode({"token": cfg["token"]})
        port = int(cfg["local_control_port"])
        status = wait_json(f"http://127.0.0.1:{port}/status?{query}", lambda d: d.get("version") == "0.11.7.39", 60, "Bridge")
        print(json.dumps(status, ensure_ascii=True), flush=True)

        auto = wait_json(
            f"http://127.0.0.1:{port}/autolearn/status?{query}",
            lambda d: d.get("ok") is True
            and d.get("version") == "0.11.7.56"
            and d.get("mode") == "autonomous-source-grounded-project-learning-guarded"
            and d.get("proposal_dedupe") is True
            and d.get("evidence_change_required") is True,
            30,
            "autolearn",
        )
        print(json.dumps(auto, ensure_ascii=True), flush=True)
        native = wait_json(
            f"http://127.0.0.1:{port}/windows/capabilities?{query}",
            lambda d: d.get("ok") is True
            and d.get("version") == "0.11.7.56"
            and d.get("supported_windows_primitives") is True
            and d.get("cortana_private_api_dependency") is False,
            30,
            "windows native",
        )
        print(json.dumps(native, ensure_ascii=True), flush=True)

        chat = f"http://127.0.0.1:{port}/llm/chat?{query}"
        first = post_json(chat, {"message": SAVE, "history": []})
        if first.get("memory_write") is not True:
            raise RuntimeError(f"Mica write failed: {first}")
        corr = post_json(chat, {"message": CORRECT, "history": []})
        if corr.get("memory_correction") is not True or corr.get("grounding") != "explicit-personal-memory-correction-v11752":
            raise RuntimeError(f"correction route failed: {corr}")
        found = post_json("http://127.0.0.1:8806/search", {"query": "imaginary fox Mica Nyx", "memory_limit": 24, "episode_limit": 0})
        texts = [str(x.get("text") or "").strip() for x in found.get("memories", []) if isinstance(x, dict)]
        if NEW not in texts or OLD in texts:
            raise RuntimeError(f"newest-correction memory regression: {texts}")
        recall = post_json(chat, {"message": RECALL, "history": []}, timeout=12)
        reply = str(recall.get("reply") or "")
        if recall.get("ok") is not True or "Nyx" not in reply or "Mica" in reply:
            raise RuntimeError(f"fresh recall regression: {recall}")
        print("[v11756-memory] PASS .51 write + .52 correction + natural Nyx recall under .56", flush=True)
    finally:
        stop(bp)
        try:
            mp.terminate(); mp.wait(timeout=5)
        except Exception:
            try: mp.kill()
            except Exception: pass
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    main()
