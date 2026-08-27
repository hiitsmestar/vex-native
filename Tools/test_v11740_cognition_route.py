import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests


class FakeOllamaHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        if self.path.startswith("/api/tags"):
            body = json.dumps({"models": [{"name": "qwen3:1.7b", "model": "qwen3:1.7b"}]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/api/version"):
            body = b'{"version":"ci-fake"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()


fake_server = ThreadingHTTPServer(("127.0.0.1", 11434), FakeOllamaHandler)
threading.Thread(target=fake_server.serve_forever, daemon=True).start()

config_path = Path(os.environ["APPDATA"]) / "VexBridge" / "config.json"
deadline = time.time() + 25
last = "no response"

try:
    while time.time() < deadline:
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            external_port = int(cfg.get("port", 8765))
            local_port = int(cfg.get("local_control_port") or (external_port + 1))
            response = requests.get(
                f"http://127.0.0.1:{local_port}/llm/status",
                params={"token": cfg["token"]},
                timeout=10,
            )
            last = response.text[:2000]
            if response.status_code == 200:
                body = response.json()
                if not isinstance(body, dict):
                    raise RuntimeError("llm/status did not return an object")
                lowered = last.lower()
                if "not defined" in lowered or "nameerror" in lowered or "cognition failed" in lowered:
                    raise RuntimeError("llm/status surfaced a cognition symbol failure: " + last)
                if body.get("model") != "qwen3:1.7b":
                    raise RuntimeError("unexpected model selection: " + last)
                if "available_models" not in body or "hardware" not in body:
                    raise RuntimeError("llm/status missing expected cognition fields: " + last)
                print(last)
                raise SystemExit(0)
        except SystemExit:
            raise
        except Exception as exc:
            last = exc.__class__.__name__ + ": " + str(exc)[:700]
        time.sleep(1)
finally:
    fake_server.shutdown()
    fake_server.server_close()

raise SystemExit("Bridge cognition route did not answer cleanly: " + str(last))
