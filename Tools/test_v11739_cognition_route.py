import json
import os
import time
from pathlib import Path

import requests

config_path = Path(os.environ["APPDATA"]) / "VexBridge" / "config.json"
deadline = time.time() + 30
last = "no response"

while time.time() < deadline:
    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
        external_port = int(cfg.get("port", 8765))
        local_port = int(cfg.get("local_control_port") or (external_port + 1))
        response = requests.get(
            f"http://127.0.0.1:{local_port}/llm/status",
            params={"token": cfg["token"]},
            timeout=4,
        )
        last = response.text[:1500]
        if response.status_code == 200:
            body = response.json()
            if not isinstance(body, dict):
                raise RuntimeError("llm/status did not return an object")
            lowered = last.lower()
            if "not defined" in lowered or "nameerror" in lowered or "cognition failed" in lowered:
                raise RuntimeError("llm/status surfaced a cognition symbol failure: " + last)
            if "available_models" not in body or "hardware" not in body:
                raise RuntimeError("llm/status missing expected cognition fields: " + last)
            print(last)
            raise SystemExit(0)
    except SystemExit:
        raise
    except Exception as exc:
        last = exc.__class__.__name__ + ": " + str(exc)[:500]
    time.sleep(1)

raise SystemExit("Bridge cognition route did not answer cleanly: " + str(last))
