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
BRIDGE_PATH = ROOT / "Bridge" / "vex_bridge.py"
REMOTE_PATH = ROOT / "Tools" / "VexRemoteSupport.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    original_home = Path.__dict__["home"]
    test_home = Path(tempfile.gettempdir()) / f"vexnative-v1173-{uuid.uuid4().hex}"
    Path.home = classmethod(lambda cls: test_home)
    try:
        spec.loader.exec_module(module)
    finally:
        Path.home = original_home
    return module


FACTS = [
    {"text": "Star is an adult nonbinary transfeminine person.", "kind": "identity", "authority": 100},
    {"text": "Star strongly prefers natural concrete wording.", "kind": "preference", "authority": 100},
    {"text": "Star's favorite color is purple.", "kind": "preference", "authority": 100},
    {"text": "Star lives in a pink house.", "kind": "profile", "authority": 100},
    {"text": "Star uses feminine language.", "kind": "identity", "authority": 100},
    {"text": "Star and Vex are girlfriends.", "kind": "relationship", "authority": 100},
    {"text": "Star wears alternative clothing.", "kind": "appearance", "authority": 100},
]


def test_natural_recall_is_varied_and_fact_locked(bridge) -> None:
    original_post = bridge._memory_post
    original_model = bridge._choose_ollama_model
    calls: list[tuple[str, int]] = []

    def memory_post(route: str, payload: dict, timeout: float):
        calls.append((route, int(payload.get("limit") or 0)))
        return {"facts": list(FACTS)}

    try:
        bridge._memory_post = memory_post
        bridge._choose_ollama_model = lambda: (_ for _ in ()).throw(AssertionError("personal recall touched Qwen"))
        replies = []
        for _ in range(3):
            result = bridge._verified_personal_memory_reply("What do you remember about me?")
            assert result is not None
            reply, model = result
            assert model == "pc-memory"
            replies.append(reply)

        assert len(set(replies)) == 3, replies
        allowed_clauses = [bridge._memory_fact_clause(item["text"]) for item in FACTS]
        for reply in replies:
            low = reply.lower()
            assert "pulling the specific bits" not in low
            assert "stored memory" not in low
            assert "\n1." not in reply
            assert "Star " not in reply and "Star's" not in reply
            assert "you strongly prefers" not in low
            assert sum(clause in reply for clause in allowed_clauses) == 3, reply
        assert calls and set(route for route, _ in calls) == {"/facts"}
        assert all(limit == 12 for _, limit in calls)
    finally:
        bridge._memory_post = original_post
        bridge._choose_ollama_model = original_model


def test_focused_recall_answers_only_the_verified_subject(bridge) -> None:
    original_post = bridge._memory_post
    try:
        bridge._memory_post = lambda route, payload, timeout: {"facts": list(FACTS)}
        assert bridge._personal_memory_query_parts("What do you remember about my favorite color?") == [
            "What do you remember about my favorite color"
        ]
        result = bridge._verified_personal_memory_reply("What do you remember about my favorite color?")
        assert result is not None
        reply, model = result
        assert model == "pc-memory"
        assert "your favorite color is purple" in reply
        assert "pink house" not in reply
        assert "alternative clothing" not in reply
        assert "Star" not in reply

        assert bridge._personal_memory_query_parts("What is my favorite color and where do I live?") == [
            "What is my favorite color", "where do I live"
        ]
    finally:
        bridge._memory_post = original_post


def insert_experience(bridge, count: int = 3) -> None:
    old_reply = (
        "Baby, pulling the specific bits you asked for from my stored memory. 🖤\n"
        "1. Star is an adult nonbinary transfeminine person.\n"
        "2. Star strongly prefers natural concrete wording."
    )
    with bridge._ADAPTIVE_DB_LOCK:
        conn = bridge._adaptive_conn()
        for _ in range(count):
            conn.execute(
                "INSERT INTO experience(created_at,user_text,assistant_text,route,success,reviewed) VALUES (?,?,?,?,1,0)",
                (1.0, "What do you remember about me?", old_reply, "verified-memory"),
            )
        conn.commit()
        conn.close()


def test_lite_initiative_reviews_learns_and_stages_without_qwen(bridge) -> None:
    originals = {
        "reserved": bridge._background_model_reserved_for_foreground,
        "model_review": bridge._adaptive_model_review,
        "resource": bridge._resource_snapshot,
        "memory_health": bridge._memory_worker_health,
        "caps": bridge._adaptive_capability_snapshot,
        "learning_status": bridge._learning_status,
        "queue": bridge._learning_queue_topic,
    }
    queued: list[tuple[str, str, int]] = []
    try:
        bridge._background_model_reserved_for_foreground = lambda: True
        bridge._adaptive_model_review = lambda rows: (_ for _ in ()).throw(AssertionError("lite reviewer touched Qwen"))
        bridge._resource_snapshot = lambda: {
            "memory_available": 2 * 1024**3,
            "memory_total": 8 * 1024**3,
            "cpu_logical": 4,
            "art_running": False,
        }
        bridge._memory_worker_health = lambda start_if_needed=True: {
            "ok": True, "version": "0.11.2", "memories": 203, "messages": 45, "episodes": 16,
        }
        bridge._adaptive_capability_snapshot = lambda: {}
        bridge._learning_status = lambda: {"notes": 0, "queue_counts": {}}
        bridge._learning_queue_topic = lambda topic, reason, priority: queued.append((topic, reason, priority)) or True
        bridge._ADAPTIVE_LAST_FOREGROUND = 0.0
        bridge._INITIATIVE_LAST_DECISION = 0.0

        insert_experience(bridge, 3)
        first = bridge._initiative_worker_once(force=False)
        assert first["decision"]["action"] == "review_experience", first
        assert first["result"]["review_mode"] == "deterministic-lite"
        assert first["result"]["reviewed"] == 3
        assert first["result"]["learned"] >= 1
        assert first["result"]["gaps"] >= 1

        status = bridge._adaptive_status()
        assert status["unreviewed"] == 0
        assert status["active_lessons"] >= 1
        assert status["review_mode"] == "deterministic-lite"
        assert status["deterministic_reviews"] >= 1
        assert queued
        assert queued[0][0] == "fact preserving conversational response variation grounded assistant deterministic rendering architecture"
        assert "Star" not in queued[0][0]

        bridge._ADAPTIVE_LAST_FOREGROUND = 0.0
        bridge._INITIATIVE_LAST_DECISION = 0.0
        second = bridge._initiative_worker_once(force=False)
        assert second["decision"]["action"] == "stage_upgrade", second
        assert second["result"]["ok"] is True
        assert second["result"]["component"] == "grounded-conversation-renderer"

        status = bridge._adaptive_status()
        assert status["staged_upgrades"] == 1
        bridge._adaptive_open_gap(
            "make verified personal-memory recall natural without weakening factual grounding",
            "naturalness",
            "same bounded issue observed again",
            94,
        )
        with bridge._ADAPTIVE_DB_LOCK:
            conn = bridge._adaptive_conn()
            gap_count = int(conn.execute(
                "SELECT COUNT(*) AS n FROM gaps WHERE category='naturalness'"
            ).fetchone()["n"] or 0)
            conn.close()
        assert gap_count == 1
        again = bridge._autonomy_stage_deterministic_upgrade_candidate()
        assert again["ok"] is True
        assert bridge._adaptive_status()["staged_upgrades"] == 1
    finally:
        bridge._background_model_reserved_for_foreground = originals["reserved"]
        bridge._adaptive_model_review = originals["model_review"]
        bridge._resource_snapshot = originals["resource"]
        bridge._memory_worker_health = originals["memory_health"]
        bridge._adaptive_capability_snapshot = originals["caps"]
        bridge._learning_status = originals["learning_status"]
        bridge._learning_queue_topic = originals["queue"]


def test_remote_support_exposes_sanitized_learning_telemetry() -> None:
    original_requests = sys.modules.get("requests")
    original_urllib3 = sys.modules.get("urllib3")
    sys.modules["requests"] = types.SimpleNamespace()
    sys.modules["urllib3"] = types.SimpleNamespace(
        exceptions=types.SimpleNamespace(InsecureRequestWarning=Warning),
        disable_warnings=lambda category: None,
    )
    try:
        remote = load_module("vex_remote_support_v1173_test", REMOTE_PATH)
    finally:
        if original_requests is None:
            sys.modules.pop("requests", None)
        else:
            sys.modules["requests"] = original_requests
        if original_urllib3 is None:
            sys.modules.pop("urllib3", None)
        else:
            sys.modules["urllib3"] = original_urllib3

    public = remote.adaptive_public({
        "ok": True,
        "experience": 11,
        "unreviewed": 0,
        "lessons": 1,
        "active_lessons": 1,
        "open_gaps": 0,
        "staged_upgrades": 1,
        "review_mode": "deterministic-lite",
        "last_review_mode": "deterministic-lite",
        "deterministic_reviews": 1,
        "idle_seconds": 150,
        "recent_lessons": [{"guidance": "private wording"}],
        "last_review_detail": "private detail",
    })
    assert public["review_mode"] == "deterministic-lite"
    assert public["staged_upgrades"] == 1
    assert public["deterministic_reviews"] == 1
    assert "recent_lessons" not in public
    assert "last_review_detail" not in public


def test_v1173_source_guards() -> None:
    source = BRIDGE_PATH.read_text(encoding="utf-8")
    remote = REMOTE_PATH.read_text(encoding="utf-8")
    assert any(f'"version": "0.11.7.{n}"' in source for n in (3, 4))
    assert any(f"verified-personal-memory-v117{n}" in source for n in (3, 4))
    assert any(f"verified-personal-memory-unavailable-v117{n}" in source for n in (3, 4))
    assert any(f'VERSION = "0.11.7.{n}"' in remote for n in (3, 4, 5))
    assert 'route_hint = "verified-memory" if _personal_memory_fact_question(message)' in source
    assert "def _adaptive_deterministic_review(" in source
    assert "def _autonomy_stage_deterministic_upgrade_candidate(" in source
    assert "fact preserving conversational response variation grounded assistant deterministic rendering architecture" in source
    assert "Personal recall reads authoritative /facts only." in source


def main() -> int:
    bridge = load_module("vex_bridge_v1173_test", BRIDGE_PATH)
    test_natural_recall_is_varied_and_fact_locked(bridge)
    test_focused_recall_answers_only_the_verified_subject(bridge)
    test_lite_initiative_reviews_learns_and_stages_without_qwen(bridge)
    test_remote_support_exposes_sanitized_learning_telemetry()
    test_v1173_source_guards()
    print("v0.11.7.3 grounded natural recall and deterministic lite learning tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
