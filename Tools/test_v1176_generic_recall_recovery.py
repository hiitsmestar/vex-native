#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRIDGE_PATH = ROOT / "Bridge" / "vex_bridge.py"


def load_bridge():
    test_root = Path(tempfile.gettempdir()) / f"vexnative-v1176-{uuid.uuid4().hex}"
    test_root.mkdir(parents=True, exist_ok=True)
    old_appdata = os.environ.get("APPDATA")
    os.environ["APPDATA"] = str(test_root)
    original_home = Path.__dict__["home"]
    Path.home = classmethod(lambda cls: test_root)
    spec = importlib.util.spec_from_file_location("vex_bridge_v1176_test", BRIDGE_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {BRIDGE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        Path.home = original_home
        if old_appdata is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = old_appdata
    return module


def test_conversational_framing_is_not_a_topic(bridge) -> None:
    assert bridge._personal_memory_fact_question("Okay babe, what do you actually know about me?") is True
    assert bridge._memory_query_tokens("Okay babe, what do you actually know about me?") == set()
    assert bridge._memory_query_tokens("Honestly gorgeous, tell me something else you remember about me today") == set()
    assert bridge._memory_query_tokens("Okay babe, what do you actually know about my hair?") == {"hair"}
    assert bridge._memory_query_tokens("What do you remember about where I live?") == {"live"}
    assert bridge._personal_memory_query_parts("Okay babe, what do you actually know about my hair?") == [
        "what do you actually know about my hair"
    ]


def test_generic_recall_uses_authoritative_top_facts(bridge) -> None:
    calls = []
    original_post = bridge._memory_post
    original_variant = bridge._MEMORY_REPLY_VARIANT
    try:
        bridge._MEMORY_REPLY_VARIANT = 0

        def fake_post(path, payload, timeout):
            calls.append((path, payload, timeout))
            return {
                "ok": True,
                "facts": [
                    {"text": "Star is an adult nonbinary transfeminine person.", "kind": "identity", "authority": 100},
                    {"text": "Star strongly prefers natural, concrete wording.", "kind": "preference", "authority": 100},
                    {"text": "Star and Vex are established girlfriends.", "kind": "relationship", "authority": 100},
                ],
            }

        bridge._memory_post = fake_post
        result = bridge._verified_personal_memory_reply("Okay babe, what do you actually know about me?")
    finally:
        bridge._memory_post = original_post
        bridge._MEMORY_REPLY_VARIANT = original_variant

    assert result is not None
    reply, model = result
    assert model == "pc-memory"
    assert calls == [("/facts", {"query": "", "limit": 12}, 1.4)]
    assert "adult nonbinary transfeminine person" in reply
    assert "natural, concrete wording" in reply
    assert "established girlfriends" in reply
    assert "verified memory store didn't return" not in reply


def test_focused_recall_keeps_the_real_topic(bridge) -> None:
    calls = []
    original_post = bridge._memory_post
    try:
        def fake_post(path, payload, timeout):
            calls.append((path, payload, timeout))
            return {
                "ok": True,
                "facts": [
                    {"text": "Star's hair is black.", "kind": "appearance", "authority": 100},
                    {"text": "Star strongly prefers natural wording.", "kind": "preference", "authority": 100},
                ],
            }

        bridge._memory_post = fake_post
        result = bridge._verified_personal_memory_reply("Okay babe, what do you actually know about my hair?")
    finally:
        bridge._memory_post = original_post

    assert result is not None
    reply, _ = result
    assert len(calls) == 1
    assert calls[0][0] == "/facts"
    assert "my hair" in calls[0][1]["query"].lower()
    assert "your hair is black" in reply.lower()
    assert "natural wording" not in reply


def test_source_guards() -> None:
    source = BRIDGE_PATH.read_text(encoding="utf-8")
    assert '"version": "0.11.7.6"' in source
    assert "verified-personal-memory-v1176" in source
    assert '"ok", "okay", "actually", "really", "honestly"' in source
    assert '{"query": "", "limit": 12}' in source
    assert "topical = [part for part in clean if _memory_query_tokens(part)]" in source


def main() -> int:
    bridge = load_bridge()
    test_conversational_framing_is_not_a_topic(bridge)
    test_generic_recall_uses_authoritative_top_facts(bridge)
    test_focused_recall_keeps_the_real_topic(bridge)
    test_source_guards()
    print("v0.11.7.6 generic conversational recall recovery tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
