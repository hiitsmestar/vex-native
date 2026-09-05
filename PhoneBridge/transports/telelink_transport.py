"""TeleLink adapter for VexPhoneBridge.

TeleLink remains an external dependency. No TeleLink source or user secrets are
stored in VexNative; this adapter only invokes its documented CLI.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SendResult:
    ok: bool
    transport: str
    detail: str
    raw: dict | None = None


class TeleLinkTransport:
    name = "telelink"

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.entry = self.root / "telelink.ps1"

    def _run(self, *args: str, timeout: int = 40) -> subprocess.CompletedProcess[str]:
        if not self.entry.exists():
            raise FileNotFoundError(f"TeleLink not installed at {self.root}")
        return subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self.entry),
                *args,
            ],
            cwd=str(self.root),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )

    def status(self) -> dict:
        try:
            proc = self._run("agent", "context", timeout=20)
            parsed = json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else None
            return {
                "ok": proc.returncode == 0,
                "transport": self.name,
                "installed": self.entry.exists(),
                "telelink_root": str(self.root),
                "agent_context": parsed,
                "stderr": proc.stderr.strip() or None,
            }
        except Exception as exc:
            return {
                "ok": False,
                "transport": self.name,
                "installed": self.entry.exists(),
                "telelink_root": str(self.root),
                "error": str(exc),
            }

    def send(self, to: str, message: str) -> SendResult:
        if not to.strip() or not message:
            return SendResult(False, self.name, "recipient and message are required")
        try:
            proc = self._run("send", to, message)
        except Exception as exc:
            return SendResult(False, self.name, str(exc))

        output = (proc.stdout + "\n" + proc.stderr).strip()
        return SendResult(
            ok=proc.returncode == 0,
            transport=self.name,
            detail=output[-4000:] if output else f"TeleLink exited {proc.returncode}",
            raw={"returncode": proc.returncode},
        )
