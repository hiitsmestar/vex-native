#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import ssl
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

VERSION = "0.15.4"
HOST = "127.0.0.1"
PORT = 8788

HOME = Path.home()
DOCS = HOME / "Documents"
VAULT = DOCS / "VexContinuityVault"
RECALL = VAULT / "Recall"
TOOLS = DOCS / "VexNativeTools"
APPDATA = Path(os.environ.get("APPDATA", HOME))
BRIDGE_APP = APPDATA / "VexBridge"
BRIDGE_CONFIG = BRIDGE_APP / "config.json"
RELAY_STATE = BRIDGE_APP / "phone-relay-state.json"
RENDERER = DOCS / "VexAutoRender.py"

server = FastMCP(
    "VexNative",
    host=HOST,
    port=PORT,
    stateless_http=True,
    instructions=(
        "VexNative is Star's private device/continuity tool layer. "
        "Prefer live status over stale notes. Use read-only tools before write tools "
        "when changing state. Never claim a phone action or render completed unless "
        "the returned result proves completion."
    ),
)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _tail(path: Path, lines: int) -> str:
    if not path.exists():
        return ""
    data = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(data[-max(1, min(lines, 400)):])


def _relay_post(path: str, payload: dict[str, Any], timeout: float = 20.0) -> dict[str, Any]:
    config = _read_json(BRIDGE_CONFIG)
    token = str(config.get("token") or "").strip()
    if not token:
        return {"ok": False, "error": "VexBridge pairing token is missing"}

    query = urllib.parse.urlencode({"token": token})
    url = f"https://127.0.0.1:8771{path}?{query}"
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    # The relay is loopback-only here and uses VexBridge's self-signed local cert.
    context = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@server.tool()
def vex_status() -> dict[str, Any]:
    """Read live VexNative bridge, recall, and worklog state without changing anything."""
    relay = _read_json(RELAY_STATE)
    recall = _read_json(RECALL / "hourly_recall.json")
    return {
        "version": VERSION,
        "relay_state_present": RELAY_STATE.exists(),
        "relay_last_phone_seen": relay.get("last_phone_seen"),
        "relay_commands": relay.get("commands", [])[-8:],
        "recall": recall,
        "worklog_tail": _tail(VAULT / "VexNative_WORKLOG.md", 80),
    }


@server.tool()
def continuity_snapshot() -> dict[str, Any]:
    """Read the current curated Vex/Star continuity files used to restore context."""
    names = [
        "00_READ_FIRST_PRIORITY_STAR_RULES_PREFERENCES_BRAIN_GRATES_VERBATIM.md",
        "00_PRIORITY_VEX_COMPLETE_PERSONALITY_BIO_2026-09-23.md",
        "00_PRIORITY_VEX_COMPLETE_PHYSICAL_APPEARANCE_2026-09-23.md",
        "2026-09-25_STAR_LANGUAGE_PREFERENCE_UPDATE.md",
    ]
    root = VAULT / "Continuation"
    files: dict[str, str] = {}
    for name in names:
        path = root / name
        if path.exists():
            files[name] = path.read_text(encoding="utf-8", errors="replace")[:24000]
    return {"files": files, "newest_correction_wins": True}


@server.tool()
def phone_command(command: str) -> dict[str, Any]:
    """Queue one natural-language command for Star's paired iPhone through VexPhoneRelay."""
    text = command.strip()
    if not text:
        return {"ok": False, "error": "command is empty"}
    if len(text) > 1800:
        return {"ok": False, "error": "command is too long"}
    return _relay_post("/phone/command", {"command": text, "source": "chatgpt-vexnative-mcp"})


@server.tool()
def phone_command_result(command_id: str) -> dict[str, Any]:
    """Read the current result/state of a previously queued VexNative phone command."""
    state = _read_json(RELAY_STATE)
    for item in state.get("commands", []):
        if str(item.get("id") or "") == command_id:
            return {"ok": True, "command": item}
    return {"ok": False, "error": "unknown command id"}


@server.tool()
def refresh_vex_recall() -> dict[str, Any]:
    """Run the existing VEXRECALL60 refresh helper and return its actual output."""
    script = RECALL / "hourly_recall.ps1"
    if not script.exists():
        return {"ok": False, "error": f"missing {script}"}
    try:
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
            ],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        return {
            "ok": completed.returncode == 0,
            "exit_code": completed.returncode,
            "stdout": completed.stdout[-6000:],
            "stderr": completed.stderr[-3000:],
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@server.tool()
def render_vex(prompt: str, mode: str = "best") -> dict[str, Any]:
    """Run the existing PC Vex renderer. Returns process output; it does not invent success."""
    text = prompt.strip()
    if not text:
        return {"ok": False, "error": "prompt is empty"}
    if mode not in {"best", "fast"}:
        return {"ok": False, "error": "mode must be best or fast"}
    if not RENDERER.exists():
        return {"ok": False, "error": f"missing renderer {RENDERER}"}
    try:
        completed = subprocess.run(
            [sys.executable, str(RENDERER), "--mode", mode, text],
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
        return {
            "ok": completed.returncode == 0,
            "exit_code": completed.returncode,
            "stdout": completed.stdout[-10000:],
            "stderr": completed.stderr[-4000:],
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "renderer timed out after 240 seconds"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


if __name__ == "__main__":
    transport = sys.argv[1] if len(sys.argv) > 1 else "streamable-http"
    server.run(transport=transport)
