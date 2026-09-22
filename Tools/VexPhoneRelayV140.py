#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import secrets
import ssl
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

APP = Path(os.environ.get("APPDATA", Path.home())) / "VexBridge"
CONFIG = APP / "config.json"
CERT = APP / "bridge-cert.pem"
KEY = APP / "bridge-key.pem"
STATE_FILE = APP / "phone-relay-state.json"
PORT = 8771
LOCK = threading.RLock()

def now() -> int:
    return int(time.time())

def load_config() -> dict:
    return json.loads(CONFIG.read_text("utf-8"))

def load_state() -> dict:
    try:
        data = json.loads(STATE_FILE.read_text("utf-8"))
        if isinstance(data, dict):
            data.setdefault("commands", [])
            data.setdefault("last_phone_seen", 0)
            return data
    except Exception:
        pass
    return {"commands": [], "last_phone_seen": 0}

STATE = load_state()

def save_state() -> None:
    APP.mkdir(parents=True, exist_ok=True)
    temp = STATE_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(STATE, indent=2), "utf-8")
    temp.replace(STATE_FILE)

def prune() -> None:
    cutoff = now() - 7 * 86400
    STATE["commands"] = [
        c for c in STATE["commands"]
        if int(c.get("created_at", 0)) >= cutoff
    ][-200:]

def find_command(command_id: str) -> dict | None:
    return next((c for c in STATE["commands"] if c.get("id") == command_id), None)

def take_next_command() -> dict | None:
    with LOCK:
        prune()
        STATE["last_phone_seen"] = now()
        command = next(
            (c for c in STATE["commands"] if c.get("state") == "queued"),
            None,
        )
        if command is not None:
            command["state"] = "delivered"
            command["delivered_at"] = now()
        save_state()
        return dict(command) if command is not None else None

class Handler(BaseHTTPRequestHandler):
    server_version = "VexPhoneRelay/0.13.10"

    def log_message(self, fmt: str, *args) -> None:
        print("[phone-relay] " + (fmt % args), flush=True)

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _auth(self, params: dict[str, list[str]]) -> bool:
        supplied = (params.get("token") or [""])[0]
        expected = str(load_config().get("token") or "")
        return bool(expected) and secrets.compare_digest(supplied, expected)

    def _parsed(self):
        parsed = urllib.parse.urlparse(self.path)
        return parsed, urllib.parse.parse_qs(parsed.query)

    def do_GET(self) -> None:
        parsed, params = self._parsed()
        if not self._auth(params):
            self._json(401, {"ok": False, "error": "invalid token"})
            return

        if parsed.path == "/phone/wait":
            deadline = time.monotonic() + 25.0
            command = None
            while time.monotonic() < deadline:
                command = take_next_command()
                if command is not None:
                    break
                time.sleep(0.5)
            self._json(200, {"ok": True, "command": command})
            return

        with LOCK:
            prune()
            if parsed.path == "/status":
                counts = {}
                for item in STATE["commands"]:
                    key = str(item.get("state") or "unknown")
                    counts[key] = counts.get(key, 0) + 1
                self._json(200, {
                    "ok": True,
                    "version": "0.13.10",
                    "port": PORT,
                    "last_phone_seen": STATE.get("last_phone_seen", 0),
                    "counts": counts,
                })
                return

            if parsed.path == "/phone/next":
                command = take_next_command()
                self._json(200, {"ok": True, "command": command})
                return

            if parsed.path == "/phone/result":
                command_id = (params.get("id") or [""])[0]
                command = find_command(command_id)
                self._json(
                    200 if command else 404,
                    {"ok": bool(command), "command": command},
                )
                return

            self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        parsed, params = self._parsed()
        if not self._auth(params):
            self._json(401, {"ok": False, "error": "invalid token"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0 or length > 16_000:
                raise ValueError("invalid payload size")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception as exc:
            self._json(400, {"ok": False, "error": str(exc)})
            return

        with LOCK:
            if parsed.path == "/phone/command":
                text = str(payload.get("command") or "").strip()
                if not text or len(text) > 2000:
                    self._json(400, {"ok": False, "error": "invalid command"})
                    return
                item = {
                    "id": uuid.uuid4().hex,
                    "command": text,
                    "source": str(payload.get("source") or "pc")[:80],
                    "state": "queued",
                    "created_at": now(),
                }
                STATE["commands"].append(item)
                prune()
                save_state()
                self._json(200, {"ok": True, "command": item})
                return

            if parsed.path == "/phone/result":
                command_id = str(payload.get("id") or "")
                item = find_command(command_id)
                if item is None:
                    self._json(404, {"ok": False, "error": "unknown command"})
                    return
                item["state"] = "completed" if bool(payload.get("ok")) else "failed"
                item["ok"] = bool(payload.get("ok"))
                item["result"] = str(payload.get("result") or "")[:4000]
                item["completed_at"] = now()
                STATE["last_phone_seen"] = now()
                save_state()
                self._json(200, {"ok": True, "command": item})
                return

            self._json(404, {"ok": False, "error": "not found"})

def main() -> None:
    cfg = load_config()
    if not cfg.get("token"):
        raise SystemExit("VexBridge pairing token is missing")
    if not CERT.exists() or not KEY.exists():
        raise SystemExit("VexBridge TLS certificate/key are missing")

    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=str(CERT), keyfile=str(KEY))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    print(f"VexPhoneRelay v0.13.10 listening on https://0.0.0.0:{PORT}", flush=True)
    server.serve_forever()

if __name__ == "__main__":
    main()
