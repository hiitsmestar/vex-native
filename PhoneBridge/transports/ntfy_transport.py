"""Zero-recurring-cost ntfy transport for VexPhoneBridge.

Secrets live in a local private config or environment variables, never Git.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SendResult:
    ok: bool
    transport: str
    detail: str
    raw: dict | None = None


def default_private_config() -> Path:
    local = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    return local / "VexNative" / "PhoneBridge" / "private.json"


class NtfyTransport:
    name = "ntfy"

    def __init__(self, config_path: Path | None = None):
        self.config_path = (config_path or default_private_config()).resolve()
        self.config = self._load_config()

    def _load_config(self) -> dict:
        data: dict = {}
        if self.config_path.exists():
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        return {
            "base_url": os.environ.get("VEX_PHONE_NTFY_BASE_URL")
            or data.get("ntfy_base_url")
            or "https://ntfy.sh",
            "topic": os.environ.get("VEX_PHONE_NTFY_TOPIC")
            or data.get("ntfy_topic"),
            "title": data.get("ntfy_title") or "Vex 🖤",
        }

    def status(self) -> dict:
        topic = str(self.config.get("topic") or "").strip()
        return {
            "ok": bool(topic),
            "transport": self.name,
            "ready": bool(topic),
            "base_url": self.config["base_url"],
            "topic_configured": bool(topic),
            "private_config": str(self.config_path),
        }

    def send(self, to: str, message: str) -> SendResult:
        topic = str(self.config.get("topic") or "").strip()
        if not topic:
            return SendResult(False, self.name, "ntfy topic is not configured")
        if not message:
            return SendResult(False, self.name, "message is required")

        url = self.config["base_url"].rstrip("/") + "/" + topic
        request = urllib.request.Request(
            url,
            data=message.encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "text/plain; charset=utf-8",
                "Title": self.config["title"],
                "Tags": "black_heart",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                body = response.read().decode("utf-8", errors="replace")
                parsed = json.loads(body) if body.lstrip().startswith("{") else None
                return SendResult(True, self.name, "published", parsed)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            return SendResult(False, self.name, f"ntfy publish failed: {exc}")
