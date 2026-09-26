#!/usr/bin/env python3
from __future__ import annotations
import json, os, subprocess, sys, time, traceback, urllib.request
from datetime import datetime, timezone
from pathlib import Path

VERSION = "0.15.6"
HOME = Path.home()
DEFAULT_ROOT = HOME / "Dropbox" / "VexRemoteBridge"
ROOT = Path(os.environ.get("VEX_DROPBOX_PARITY_ROOT", str(DEFAULT_ROOT)))
COMMANDS = ROOT / "commands"
RESULTS = ROOT / "results"
PROCESSING = ROOT / "processing"
FAILED = ROOT / "failed"
STATE = ROOT / "state.json"
PARITY_ROOT = Path(os.environ.get("LOCALAPPDATA", str(HOME))) / "VexNative" / "DesktopParity"
SECRETS = PARITY_ROOT / "secrets.json"
CONFIG = PARITY_ROOT / "install-config.json"
MAX_BYTES = 1024 * 1024
POLL_SECONDS = float(os.environ.get("VEX_DROPBOX_PARITY_POLL_SECONDS", "2.0"))

def utcnow():
    return datetime.now(timezone.utc).isoformat()

def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

def write_json_atomic(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)

def ensure_dirs():
    for p in (COMMANDS, RESULTS, PROCESSING, FAILED):
        p.mkdir(parents=True, exist_ok=True)

def endpoint_and_token():
    cfg = read_json(CONFIG)
    sec = read_json(SECRETS)
    port = int(cfg.get("hubPort", 8792))
    token = str(sec.get("hubToken") or "")
    if not token:
        raise RuntimeError("Vex Desktop Parity hub token missing")
    return f"http://127.0.0.1:{port}/mcp", token

def call_mcp(tool: str, args: dict):
    endpoint, token = endpoint_and_token()
    helper = PARITY_ROOT / "dropbox-call.mjs"
    if not helper.exists():
        raise RuntimeError(f"missing MCP helper: {helper}")
    payload = json.dumps({"endpoint": endpoint, "token": token, "tool": tool, "arguments": args})
    completed = subprocess.run(
        ["node.exe", str(helper), payload],
        cwd=str(PARITY_ROOT),
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "MCP call failed")[-8000:])
    return json.loads(completed.stdout)

def handle(path: Path):
    if path.stat().st_size > MAX_BYTES:
        raise RuntimeError("command envelope too large")
    cmd = read_json(path)
    request_id = str(cmd.get("request_id") or path.stem)
    tool = str(cmd.get("tool") or "").strip()
    args = cmd.get("arguments") or {}
    if not tool:
        raise RuntimeError("tool is required")
    if not isinstance(args, dict):
        raise RuntimeError("arguments must be an object")
    started = utcnow()
    result = call_mcp(tool, args)
    envelope = {
        "version": VERSION,
        "request_id": request_id,
        "device": os.environ.get("COMPUTERNAME", ""),
        "tool": tool,
        "started_at": started,
        "completed_at": utcnow(),
        "ok": True,
        "result": result,
    }
    write_json_atomic(RESULTS / f"{request_id}.json", envelope)
    return request_id

def main():
    ensure_dirs()
    write_json_atomic(STATE, {"version": VERSION, "pid": os.getpid(), "started_at": utcnow(), "root": str(ROOT)})
    while True:
        items = sorted(COMMANDS.glob("*.json"), key=lambda p: p.stat().st_mtime)
        if not items:
            time.sleep(POLL_SECONDS)
            continue
        for src in items:
            work = PROCESSING / src.name
            try:
                os.replace(src, work)
            except FileNotFoundError:
                continue
            try:
                request_id = handle(work)
                work.unlink(missing_ok=True)
                write_json_atomic(STATE, {"version": VERSION, "pid": os.getpid(), "last_request_id": request_id, "last_ok_at": utcnow(), "root": str(ROOT)})
            except Exception as exc:
                rid = work.stem
                write_json_atomic(
                    FAILED / f"{rid}.json",
                    {
                        "version": VERSION,
                        "request_id": rid,
                        "device": os.environ.get("COMPUTERNAME", ""),
                        "ok": False,
                        "error": str(exc),
                        "traceback": traceback.format_exc()[-12000:],
                        "failed_at": utcnow(),
                    },
                )
                work.unlink(missing_ok=True)
                write_json_atomic(STATE, {"version": VERSION, "pid": os.getpid(), "last_request_id": rid, "last_error": str(exc), "last_error_at": utcnow(), "root": str(ROOT)})

if __name__ == "__main__":
    main()
