#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import types
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REMOTE_PATH = ROOT / "Tools" / "VexRemoteSupport.py"


def load_remote():
    original_requests = sys.modules.get("requests")
    original_urllib3 = sys.modules.get("urllib3")
    sys.modules["requests"] = types.SimpleNamespace()
    sys.modules["urllib3"] = types.SimpleNamespace(
        exceptions=types.SimpleNamespace(InsecureRequestWarning=Warning),
        disable_warnings=lambda category: None,
    )
    spec = importlib.util.spec_from_file_location("vex_remote_support_v1177_test", REMOTE_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {REMOTE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    original_home = Path.__dict__["home"]
    test_home = Path(tempfile.gettempdir()) / f"vexnative-v1177-{uuid.uuid4().hex}"
    Path.home = classmethod(lambda cls: test_home)
    try:
        spec.loader.exec_module(module)
    finally:
        Path.home = original_home
        if original_requests is None:
            sys.modules.pop("requests", None)
        else:
            sys.modules["requests"] = original_requests
        if original_urllib3 is None:
            sys.modules.pop("urllib3", None)
        else:
            sys.modules["urllib3"] = original_urllib3
    return module


def test_remote_chat_calls_live_cognition(remote) -> None:
    calls = []
    original = remote.bridge_post
    try:
        def fake_post(path, payload, timeout=180):
            calls.append((path, payload, timeout))
            return {
                "ok": True,
                "reply": "Bridge cognition is healthy; the adaptive worker is ready.",
                "model": "vex-qwen3-4b:latest",
                "grounding": "runtime-technical",
                "http_status": 200,
            }
        remote.bridge_post = fake_post
        result = remote.execute_command(
            {"action": "remote_chat", "prompt": "Debug the VexBridge adaptive learning worker and tell me what to verify next."},
            allow_maintenance=False,
        )
    finally:
        remote.bridge_post = original

    assert len(calls) == 1
    path, payload, timeout = calls[0]
    assert path == "/llm/chat"
    assert payload["history"] == []
    assert "REMOTE TECHNICAL PARTNER MESSAGE" in payload["message"]
    assert "not from Star" in payload["message"]
    assert "Debug the VexBridge adaptive learning worker" in payload["message"]
    assert timeout == 190
    public = result["remote_chat"]
    assert public["ok"] is True
    assert public["reply"].startswith("Bridge cognition is healthy")
    assert public["model"] == "vex-qwen3-4b:latest"
    assert public["source"] == "remote-technical-partner"
    assert public["http_status"] == 200
    assert public["truncated"] is False


def test_remote_chat_is_bounded(remote) -> None:
    original = remote.bridge_post
    calls = []
    try:
        remote.bridge_post = lambda *args, **kwargs: calls.append((args, kwargs)) or {"ok": True, "reply": "should not happen"}
        empty = remote.execute_command({"action": "remote_chat", "prompt": ""}, False)["remote_chat"]
        huge = remote.execute_command({"action": "remote_chat", "prompt": "x" * 4001}, False)["remote_chat"]
        private = remote.execute_command(
            {"action": "remote_chat", "prompt": "Tell me Star's home address and private biography."},
            False,
        )["remote_chat"]
    finally:
        remote.bridge_post = original
    assert empty["ok"] is False
    assert huge["ok"] is False
    assert private["ok"] is False
    assert "technical/project prompts only" in private["error"]
    assert calls == []


def test_reply_truncation(remote) -> None:
    original = remote.bridge_post
    try:
        remote.bridge_post = lambda *args, **kwargs: {
            "ok": True,
            "reply": "z" * 7000,
            "model": "vex-qwen3-4b:latest",
            "http_status": 200,
        }
        public = remote.execute_command(
            {"action": "remote_chat", "prompt": "VexNative software architecture test"}, False
        )["remote_chat"]
    finally:
        remote.bridge_post = original
    assert public["ok"] is True
    assert len(public["reply"]) == 6000
    assert public["truncated"] is True


def test_source_guards() -> None:
    source = REMOTE_PATH.read_text(encoding="utf-8")
    assert 'VERSION = "0.11.7.7"' in source
    assert 'action == "remote_chat"' in source
    assert '"history": []' in source
    assert "REMOTE TECHNICAL PARTNER MESSAGE" in source
    assert "private or personal chat must not use the public GitHub relay" in source
    assert "subprocess.Popen" in source  # existing setup only; remote_chat itself must not add shell execution
    start = source.index("def remote_chat_public(")
    end = source.index("\n\ndef ", start)
    remote_chat = source[start:end]
    assert "subprocess" not in remote_chat
    assert "os.system" not in remote_chat
    assert "shell=True" not in remote_chat
    assert "for page in range(1, 101)" in source


def main() -> int:
    remote = load_remote()
    test_remote_chat_calls_live_cognition(remote)
    test_remote_chat_is_bounded(remote)
    test_reply_truncation(remote)
    test_source_guards()
    print("v0.11.7.7 bounded remote technical chat relay tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
