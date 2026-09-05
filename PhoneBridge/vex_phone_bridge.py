#!/usr/bin/env python3
"""VexPhoneBridge: transport-neutral phone messaging boundary for VexNative."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from transports.telelink_transport import TeleLinkTransport


@dataclass
class SendResult:
    ok: bool
    transport: str
    detail: str
    raw: dict | None = None


def default_telelink_root() -> Path:
    local = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    return local / "VexNative" / "ThirdParty" / "telelink-master"


def build_transport(name: str, args):
    if name == "telelink":
        return TeleLinkTransport(Path(args.telelink_root).expanduser())
    raise ValueError(f"unknown transport: {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="VexNative phone transport bridge")
    parser.add_argument("--transport", default="telelink")
    parser.add_argument("--telelink-root", default=str(default_telelink_root()))
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status")
    send = sub.add_parser("send")
    send.add_argument("to")
    send.add_argument("message")

    args = parser.parse_args()
    transport = build_transport(args.transport, args)

    if args.command == "status":
        payload = transport.status()
    else:
        payload = asdict(transport.send(args.to, args.message))

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok", False) else 2


if __name__ == "__main__":
    raise SystemExit(main())
