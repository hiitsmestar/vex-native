#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import threading
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRIDGE_PATH = ROOT / "Bridge" / "vex_bridge.py"
REMOTE_PATH = ROOT / "Tools" / "VexRemoteSupport.py"


def load_bridge():
    spec = importlib.util.spec_from_file_location("vex_bridge_v117_test", BRIDGE_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load patched Bridge source")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    original_home = Path.__dict__["home"]
    Path.home = classmethod(lambda cls: Path(tempfile.gettempdir()) / "vexnative-v117-test-home")
    try:
        spec.loader.exec_module(module)
    finally:
        Path.home = original_home
    return module


def test_activity_route(bridge) -> None:
    positives = [
        "Hey babe, what have you been doing while I've been away?",
        "What did you work on recently?",
        "Catch me up on what you did.",
        "Anything new while I was gone?",
        "Give me an update since my last message.",
    ]
    negatives = [
        "What do you remember about me?",
        "What are you doing right now?",
        "Did you know my favorite color?",
    ]
    for value in positives:
        assert bridge._recent_self_activity_question(value), value
    for value in negatives:
        assert not bridge._recent_self_activity_question(value), value

    original = bridge._initiative_recent_events
    try:
        bridge._initiative_recent_events = lambda limit: []
        empty_reply, empty_model = bridge._verified_recent_self_activity_reply(positives[0])
        assert empty_model == "pc-self-state"
        assert "don't have a recorded idle action" in empty_reply

        bridge._initiative_recent_events = lambda limit: [
            {"action": "probe_capability", "goal_key": "system_health", "ok": 1, "detail": "checked memory health"}
        ]
        reply, model = bridge._verified_recent_self_activity_reply(positives[0])
        assert model == "pc-self-state"
        assert "probe capability: completed" in reply
        assert "checked memory health" in reply
    finally:
        bridge._initiative_recent_events = original


def test_streaming_preemption(bridge) -> None:
    original_requests = sys.modules.get("requests")
    requests = types.SimpleNamespace()
    sys.modules["requests"] = requests

    class FinishedResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def iter_lines(self):
            yield json.dumps({"message": {"content": "hel"}, "done": False}).encode()
            yield json.dumps({"message": {"content": "lo"}, "done": True}).encode()

        def close(self) -> None:
            return None

    try:
        requests.post = lambda *args, **kwargs: FinishedResponse()
        response = bridge._background_ollama_post({"model": "fake", "messages": []}, timeout=20)
        assert response.json()["message"]["content"] == "hello"

        registered = threading.Event()
        closed = threading.Event()

        class BlockingResponse:
            status_code = 200

            def raise_for_status(self) -> None:
                return None

            def iter_lines(self):
                registered.set()
                while not closed.wait(0.01):
                    pass
                raise RuntimeError("closed")

            def close(self) -> None:
                closed.set()

        requests.post = lambda *args, **kwargs: BlockingResponse()
        result: dict[str, str] = {}

        def run_background() -> None:
            try:
                bridge._background_ollama_post({"model": "fake", "messages": []}, timeout=20)
                result["value"] = "unexpected-success"
            except Exception as exc:
                result["type"] = type(exc).__name__

        worker = threading.Thread(target=run_background)
        worker.start()
        assert registered.wait(2), "background stream did not start"
        bridge._foreground_cognition_enter()
        worker.join(2)
        assert not worker.is_alive(), "foreground did not preempt background stream"
        assert result.get("type") == "_ForegroundCognitionPreempted", result
        assert bridge._FOREGROUND_COGNITION_ACTIVE.is_set()
        bridge._foreground_cognition_exit()
        assert not bridge._FOREGROUND_COGNITION_ACTIVE.is_set()
    finally:
        if original_requests is None:
            sys.modules.pop("requests", None)
        else:
            sys.modules["requests"] = original_requests
        while bridge._FOREGROUND_COGNITION_ACTIVE.is_set():
            bridge._foreground_cognition_exit()


def test_source_targets() -> None:
    source = BRIDGE_PATH.read_text(encoding="utf-8")
    planner = source[source.index("def _initiative_choose_action("):]
    planner = planner[:planner.index("\n\ndef ")]
    for marker in (
        "_background_ollama_post(",
        "foreground cognition arrived; initiative planner yielded",
        "except _ForegroundCognitionPreempted:",
    ):
        assert marker in planner, marker

    handler = source[source.index('        if parsed.path == "/llm/chat":'):]
    handler = handler[:handler.index('        if parsed.path == "/tts/speak":')]
    assert handler.index("_foreground_cognition_enter()") < handler.index("self.rfile.read")
    assert "finally:\n                _foreground_cognition_exit()" in handler

    remote = REMOTE_PATH.read_text(encoding="utf-8")
    for marker in (
        'VERSION = "0.11.7.1"',
        "def initiative_public(",
        "def adaptive_public(",
        'action == "initiative_status"',
        'action == "adaptive_status"',
    ):
        assert marker in remote, marker


def main() -> int:
    bridge = load_bridge()
    test_activity_route(bridge)
    test_streaming_preemption(bridge)
    test_source_targets()
    print("v0.11.7.1 grounded continuity and foreground preemption tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
