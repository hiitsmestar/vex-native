#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
CONFIG = Path(os.environ.get("APPDATA", Path.home())) / "VexBridge" / "config.json"
BASE = "https://127.0.0.1:8771"

def token() -> str:
    data = json.loads(CONFIG.read_text("utf-8"))
    value = str(data.get("token") or "")
    if not value:
        raise SystemExit("VexBridge token missing")
    return value

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command")
    parser.add_argument("--source", default="chatgpt-desktop-commander")
    parser.add_argument("--wait", type=int, default=120)
    parser.add_argument("--no-wait", action="store_true")
    args = parser.parse_args()

    params = {"token": token()}
    response = requests.post(
        BASE + "/phone/command",
        params=params,
        json={"command": args.command, "source": args.source},
        verify=False,
        timeout=8,
    )
    response.raise_for_status()
    item = response.json()["command"]
    command_id = item["id"]
    print(json.dumps({"queued": True, "id": command_id, "command": args.command}))

    if args.no_wait:
        return 0

    deadline = time.time() + max(1, args.wait)
    while time.time() < deadline:
        time.sleep(1.0)
        result = requests.get(
            BASE + "/phone/result",
            params={"token": params["token"], "id": command_id},
            verify=False,
            timeout=8,
        )
        if result.status_code == 404:
            continue
        result.raise_for_status()
        item = result.json().get("command") or {}
        state = item.get("state")
        if state in {"completed", "failed"}:
            print(json.dumps(item, ensure_ascii=False))
            return 0 if state == "completed" else 2

    print(json.dumps({"id": command_id, "state": "timeout"}))
    return 3

if __name__ == "__main__":
    raise SystemExit(main())