#!/usr/bin/env python3
from __future__ import annotations

import ast
import importlib.util
import json
import sys
import tempfile
import time
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
    test_home = Path(tempfile.gettempdir()) / f"vexnative-v1174-{uuid.uuid4().hex}"
    Path.home = classmethod(lambda cls: test_home)
    try:
        spec.loader.exec_module(module)
    finally:
        Path.home = original_home
    return module


def function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            segment = ast.get_source_segment(source, node)
            if segment:
                return segment
    raise AssertionError(f"function {name} missing")


def test_adaptive_cycle_is_bounded_and_reports_health(bridge) -> None:
    original = bridge._adaptive_worker_once
    try:
        bridge._ADAPTIVE_WORKER_HEARTBEAT_AT = 0.0
        bridge._ADAPTIVE_WORKER_LAST_OK = None
        bridge._ADAPTIVE_WORKER_LAST_ERROR_CLASS = ""
        bridge._ADAPTIVE_WORKER_CYCLES = 0
        calls = []
        bridge._adaptive_worker_once = lambda force=False: calls.append(force) or {
            "ok": True, "reviewed": 3, "learned": 1, "gaps": 1, "review_mode": "deterministic-lite"
        }
        result = bridge._adaptive_worker_cycle(force=True)
        assert result["reviewed"] == 3
        assert calls == [True]
        assert bridge._ADAPTIVE_WORKER_CYCLES == 1
        assert bridge._ADAPTIVE_WORKER_LAST_OK is True
        assert bridge._ADAPTIVE_WORKER_LAST_ERROR_CLASS == ""
        assert bridge._ADAPTIVE_WORKER_HEARTBEAT_AT > 0

        def broken(force=False):
            raise RuntimeError("private failure detail")

        bridge._adaptive_worker_once = broken
        failed = bridge._adaptive_worker_cycle(force=False)
        assert failed == {"ok": False, "detail": "adaptive cycle failed", "error_class": "RuntimeError"}
        assert bridge._ADAPTIVE_WORKER_CYCLES == 2
        assert bridge._ADAPTIVE_WORKER_LAST_OK is False
        assert bridge._ADAPTIVE_WORKER_LAST_ERROR_CLASS == "RuntimeError"
        assert "private failure detail" not in json.dumps(failed)
    finally:
        bridge._adaptive_worker_once = original


def test_scheduler_loops_are_isolated() -> None:
    source = BRIDGE_PATH.read_text(encoding="utf-8")
    adaptive = function_source(source, "_adaptive_worker_loop")
    autonomy = function_source(source, "_autonomy_worker_loop")
    initiative = function_source(source, "_initiative_scheduler_loop")
    services = function_source(source, "_vex_background_services")

    assert "_adaptive_worker_cycle" in adaptive
    assert "_autonomy_worker_once" not in adaptive
    assert "_initiative_worker_once" not in adaptive
    assert "_autonomy_worker_once" in autonomy
    assert "_adaptive_worker_cycle" not in autonomy
    assert "_initiative_worker_once" not in autonomy
    assert "_initiative_worker_once" in initiative
    assert "_adaptive_worker_cycle" not in initiative
    assert "_autonomy_worker_once" not in initiative
    assert 'name="VexAdaptiveLearning"' in services
    assert 'name="VexAutonomousImprovement"' in services
    assert 'name="VexInitiativeScheduler"' in services


def test_adaptive_status_has_sanitized_worker_liveness(bridge) -> None:
    bridge._ADAPTIVE_WORKER_STARTED_AT = time.time() - 10
    bridge._ADAPTIVE_WORKER_HEARTBEAT_AT = time.time() - 2
    bridge._ADAPTIVE_WORKER_LAST_OK = True
    bridge._ADAPTIVE_WORKER_LAST_ERROR_CLASS = ""
    bridge._ADAPTIVE_WORKER_CYCLES = 4
    status = bridge._adaptive_status()
    assert status["worker_started"] is True
    assert status["worker_alive"] is True
    assert 0 <= status["worker_heartbeat_age_seconds"] <= 5
    assert status["worker_last_ok"] is True
    assert status["worker_last_error_class"] == ""
    assert status["worker_cycles"] == 4


def load_remote():
    original_requests = sys.modules.get("requests")
    original_urllib3 = sys.modules.get("urllib3")
    sys.modules["requests"] = types.SimpleNamespace()
    sys.modules["urllib3"] = types.SimpleNamespace(
        exceptions=types.SimpleNamespace(InsecureRequestWarning=Warning),
        disable_warnings=lambda category: None,
    )
    try:
        return load_module("vex_remote_support_v1174_test", REMOTE_PATH)
    finally:
        if original_requests is None:
            sys.modules.pop("requests", None)
        else:
            sys.modules["requests"] = original_requests
        if original_urllib3 is None:
            sys.modules.pop("urllib3", None)
        else:
            sys.modules["urllib3"] = original_urllib3


def test_remote_support_can_force_and_verify_without_private_content() -> None:
    remote = load_remote()
    original_post = remote.bridge_post
    try:
        remote.bridge_post = lambda path, payload, timeout: {
            "ok": True,
            "reviewed": 11,
            "learned": 1,
            "gaps": 1,
            "review_mode": "deterministic-lite",
            "reason_codes": ["private-correction-pattern"],
            "detail": "private dialogue wording",
            "http_status": 200,
        }
        result = remote.execute_command({"action": "adaptive_run"}, allow_maintenance=False)
        assert result["adaptive_run"] == {
            "ok": True,
            "reviewed": 11,
            "learned": 1,
            "gaps": 1,
            "review_mode": "deterministic-lite",
            "http_status": 200,
            "error_class": None,
        }
        encoded = json.dumps(result)
        assert "private-correction-pattern" not in encoded
        assert "private dialogue wording" not in encoded
    finally:
        remote.bridge_post = original_post

    public = remote.adaptive_public({
        "ok": True,
        "worker_started": True,
        "worker_alive": True,
        "worker_heartbeat_age_seconds": 3,
        "worker_last_ok": True,
        "worker_last_error_class": "",
        "worker_cycles": 7,
        "last_review_detail": "private detail",
        "recent_lessons": [{"guidance": "private guidance"}],
    })
    assert public["worker_alive"] is True
    assert public["worker_heartbeat_age_seconds"] == 3
    assert public["worker_cycles"] == 7
    assert "last_review_detail" not in public
    assert "recent_lessons" not in public


def test_v1174_source_guards() -> None:
    source = BRIDGE_PATH.read_text(encoding="utf-8")
    remote = REMOTE_PATH.read_text(encoding="utf-8")
    assert '"version": "0.11.7.4"' in source
    assert "verified-personal-memory-v1174" in source
    assert "verified-personal-memory-unavailable-v1174" in source
    assert 'VERSION = "0.11.7.4"' in remote
    assert 'result = _adaptive_worker_cycle(force=True)' in source
    assert 'action == "adaptive_run"' in remote
    assert '"worker_alive": yes(value.get("worker_alive"))' in remote


def main() -> int:
    bridge = load_module("vex_bridge_v1174_test", BRIDGE_PATH)
    test_adaptive_cycle_is_bounded_and_reports_health(bridge)
    test_scheduler_loops_are_isolated()
    test_adaptive_status_has_sanitized_worker_liveness(bridge)
    test_remote_support_can_force_and_verify_without_private_content()
    test_v1174_source_guards()
    print("v0.11.7.4 isolated lite learning and live worker verification tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
