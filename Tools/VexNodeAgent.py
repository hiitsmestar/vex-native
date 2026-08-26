from __future__ import annotations

import json
import os
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VERSION = "0.11.7.33"
DEFAULT_PORT = 8770
APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "VexNode"
APP_DIR.mkdir(parents=True, exist_ok=True)
STATE_PATH = APP_DIR / "state.json"


def load_state() -> dict:
    try:
        state = json.loads(STATE_PATH.read_text("utf-8"))
    except Exception:
        state = {}
    if not state.get("token"):
        state["token"] = secrets.token_urlsafe(32)
    if not state.get("node_name"):
        state["node_name"] = socket.gethostname()
    if not state.get("port"):
        state["port"] = DEFAULT_PORT
    STATE_PATH.write_text(json.dumps(state, indent=2), "utf-8")
    return state


STATE = load_state()
STARTED = time.time()


def drives() -> list[str]:
    if os.name != "nt":
        return ["/"]
    found = []
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        root = f"{letter}:\\"
        if os.path.exists(root):
            found.append(root)
    return found


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def reply(self, code: int, payload: dict):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def authorized(self) -> bool:
        return secrets.compare_digest(self.headers.get("X-Vex-Node-Token", ""), str(STATE.get("token") or ""))

    def do_GET(self):
        if not self.authorized():
            return self.reply(401, {"ok": False, "error": "unauthorized"})
        if self.path.startswith("/status"):
            return self.reply(200, {
                "ok": True,
                "version": VERSION,
                "node_name": STATE.get("node_name"),
                "hostname": socket.gethostname(),
                "uptime_seconds": int(time.time() - STARTED),
                "drives": drives(),
            })
        if self.path.startswith("/ping"):
            return self.reply(200, {"ok": True, "node_name": STATE.get("node_name"), "time": time.time()})
        return self.reply(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if not self.authorized():
            return self.reply(401, {"ok": False, "error": "unauthorized"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(size).decode("utf-8")) if size else {}
        except Exception:
            body = {}
        if self.path == "/message":
            text = str(body.get("text") or "").strip()[:8000]
            if not text:
                return self.reply(400, {"ok": False, "error": "empty message"})
            return self.reply(200, {"ok": True, "node_name": STATE.get("node_name"), "accepted": True, "text": text})
        return self.reply(404, {"ok": False, "error": "not found"})


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", int(STATE.get("port") or DEFAULT_PORT)), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
