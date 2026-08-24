#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import time
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRIDGE_PATH = ROOT / "Bridge" / "vex_bridge.py"
REMOTE_PATH = ROOT / "Tools" / "VexRemoteSupport.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    original_home = Path.__dict__["home"]
    Path.home = classmethod(lambda cls: Path(tempfile.gettempdir()) / "vexnative-v1172-test-home")
    try:
        spec.loader.exec_module(module)
    finally:
        Path.home = original_home
    return module


def test_personal_recall_classifier(bridge) -> None:
    positives = [
        "What do you remember about me?",
        "What memories do you have of us?",
        "Do you remember my favorite color?",
        "What do you know about me?",
        "Tell me what you know about our relationship.",
    ]
    negatives = [
        "Do you remember where the file is?",
        "What have you been doing while I was away?",
        "What model are you running?",
    ]
    for value in positives:
        assert bridge._personal_memory_fact_question(value), value
    for value in negatives:
        assert not bridge._personal_memory_fact_question(value), value


def test_verified_facts_are_authoritative(bridge) -> None:
    original_post = bridge._memory_post
    calls: list[str] = []

    def memory_post(route: str, payload: dict, timeout: float):
        calls.append(route)
        assert route == "/facts"
        return {
            "facts": [
                {
                    "text": "Star's favorite color is purple.",
                    "kind": "preference",
                    "authority": 100,
                }
            ]
        }

    try:
        bridge._memory_post = memory_post
        result = bridge._verified_personal_memory_reply("What do you remember about me?")
        assert result is not None
        reply, model = result
        assert model == "pc-memory"
        assert "your favorite color is purple" in reply
        assert "Star's" not in reply
        assert "pulling the specific bits" not in reply.lower()
        assert calls and set(calls) == {"/facts"}
    finally:
        bridge._memory_post = original_post


def test_generated_episode_text_is_not_factual_grounding(bridge) -> None:
    original_retrieval = bridge._personal_memory_retrieval
    try:
        bridge._personal_memory_retrieval = lambda query: {
            "memories": [],
            "episodes": [
                {
                    "text": (
                        "Star: My favorite color is purple.\n"
                        "Vex: I explained why the stars are blue.\n"
                        "Vex: You are a glitter-brained little e-girl."
                    )
                }
            ],
        }
        grounding = bridge._personal_memory_grounding("favorite color")
        assert "Star said: My favorite color is purple." in grounding
        assert "stars are blue" not in grounding
        assert "glitter-brained" not in grounding
    finally:
        bridge._personal_memory_retrieval = original_retrieval


def test_lite_node_reserves_model_for_foreground(bridge) -> None:
    original_capacity = bridge._cognition_capacity
    original_requests = sys.modules.get("requests")
    original_deferred = bridge._BACKGROUND_OLLAMA_DEFERRED
    requests = types.SimpleNamespace()
    sys.modules["requests"] = requests
    calls = 0

    class FinishedResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def iter_lines(self):
            yield json.dumps({"message": {"content": "ready"}, "done": True}).encode()

        def close(self) -> None:
            return None

    def post(*args, **kwargs):
        nonlocal calls
        calls += 1
        return FinishedResponse()

    try:
        bridge._cognition_capacity = lambda: {"tier": "lite", "pressure": "memory"}
        requests.post = post
        bridge._BACKGROUND_OLLAMA_DEFERRED = 0

        try:
            bridge._background_ollama_post(
                {
                    "model": "fake",
                    "messages": [{"role": "user", "content": "perform idle synthesis"}],
                    "options": {"num_ctx": 4096, "num_predict": 300},
                },
                timeout=20,
            )
            raise AssertionError("lite node allowed optional idle inference")
        except bridge._ForegroundCognitionPreempted:
            pass

        assert calls == 0, "reserved background request reached Ollama"
        status = bridge._cognition_coordination_status()
        assert status["background_model_policy"] == "foreground-reserved-lite"
        assert status["background_deferred"] == 1

        response = bridge._background_ollama_post(
            {
                "model": "fake",
                "messages": [{"role": "user", "content": "Reply only: ready"}],
                "options": {"num_ctx": 512, "num_predict": 2},
            },
            timeout=20,
        )
        assert response.json()["message"]["content"] == "ready"
        assert calls == 1, "two-token warmup was not allowed"
    finally:
        bridge._cognition_capacity = original_capacity
        bridge._BACKGROUND_OLLAMA_DEFERRED = original_deferred
        if original_requests is None:
            sys.modules.pop("requests", None)
        else:
            sys.modules["requests"] = original_requests


def test_source_routes_cannot_fall_through_to_qwen() -> None:
    source = BRIDGE_PATH.read_text(encoding="utf-8")
    handler = source[source.index('        if parsed.path == "/llm/chat":'):]
    handler = handler[:handler.index('        if parsed.path == "/tts/speak":')]
    personal = handler[handler.index("if _personal_memory_fact_question(message):"):]
    personal = personal[:personal.index("if _runtime_fact_question(message):")]

    assert handler.index("if _personal_memory_fact_question(message):") < handler.index("result = _ollama_chat(")
    assert '"grounding": "verified-personal-memory-v1173"' in personal
    assert '"grounding": "verified-personal-memory-unavailable-v1173"' in personal
    assert "self._json(503" not in personal
    assert "not going to fill the gap with a guess" in personal
    assert 'parsed.path == "/cognition/coordination"' in source
    assert 'snapshot["scheduler_mode"] = _background_model_policy_label()' in source


def test_remote_support_retries_transient_relay_errors() -> None:
    original_requests = sys.modules.get("requests")
    original_urllib3 = sys.modules.get("urllib3")
    sys.modules["requests"] = types.SimpleNamespace()
    sys.modules["urllib3"] = types.SimpleNamespace(
        exceptions=types.SimpleNamespace(InsecureRequestWarning=Warning),
        disable_warnings=lambda category: None,
    )
    try:
        remote = load_module("vex_remote_support_v1172_test", REMOTE_PATH)
    finally:
        if original_requests is None:
            sys.modules.pop("requests", None)
        else:
            sys.modules["requests"] = original_requests
        if original_urllib3 is None:
            sys.modules.pop("urllib3", None)
        else:
            sys.modules["urllib3"] = original_urllib3
    posts: list[tuple[str, dict]] = []
    statuses: list[str] = []
    fetch_count = 0

    remote.POLL_SECONDS = 0.001
    remote.SESSION_SECONDS = 5
    remote.gh_ready = lambda: (True, "ready")
    remote.load_state = lambda: {"last_comment_id": 0}
    remote.save_state = lambda data: None
    remote.collect_snapshot = lambda include_doctor=False: {"ok": True}
    remote.post_comment = lambda kind, payload: posts.append((kind, payload))

    worker = remote.SupportWorker(lambda: False)
    worker.started_at = time.time()
    worker.on_status = statuses.append

    def fetch_comments():
        nonlocal fetch_count
        fetch_count += 1
        if fetch_count == 1:
            raise RuntimeError("temporary GitHub relay failure")
        worker.stop_event.set()
        return []

    remote.fetch_comments = fetch_comments
    worker.loop()

    assert fetch_count >= 2, "session died instead of retrying"
    assert any("session remains active" in value for value in statuses)
    assert posts[0][0] == "session_started"
    assert posts[-1] == ("session_ended", {"reason": "stopped"})


def main() -> int:
    bridge = load_module("vex_bridge_v1172_test", BRIDGE_PATH)
    test_personal_recall_classifier(bridge)
    test_verified_facts_are_authoritative(bridge)
    test_generated_episode_text_is_not_factual_grounding(bridge)
    test_lite_node_reserves_model_for_foreground(bridge)
    test_source_routes_cannot_fall_through_to_qwen()
    test_remote_support_retries_transient_relay_errors()
    print("v0.11.7.2 authoritative recall, lite foreground reservation, and resilient relay tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
