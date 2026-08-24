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
    spec = importlib.util.spec_from_file_location("vex_remote_support_v1175_test", REMOTE_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {REMOTE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    original_home = Path.__dict__["home"]
    test_home = Path(tempfile.gettempdir()) / f"vexnative-v1175-{uuid.uuid4().hex}"
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


def test_fetches_commands_past_first_hundred(remote) -> None:
    calls: list[str] = []

    def fake_gh_api(args, timeout=30, input_json=None):
        endpoint = args[0]
        calls.append(endpoint)
        if endpoint.endswith("&page=1"):
            return [{"id": value} for value in range(1, 101)]
        if endpoint.endswith("&page=2"):
            return [{"id": value} for value in range(101, 112)]
        raise AssertionError(f"unexpected page request: {endpoint}")

    original = remote.gh_api
    try:
        remote.gh_api = fake_gh_api
        comments = remote.fetch_comments()
    finally:
        remote.gh_api = original

    assert len(comments) == 111
    assert comments[-1]["id"] == 111
    assert len(calls) == 2
    assert calls[0].endswith("&page=1")
    assert calls[1].endswith("&page=2")


def test_memory_worker_is_visible_without_private_content(remote) -> None:
    original_get = remote.bridge_get
    original_disk = remote.disk_summary
    original_node = remote.node_id

    def fake_get(path, timeout=8):
        if path == "/status":
            return {"http_status": 200, "version": "0.11.7.4"}
        if path == "/memory/status":
            return {
                "ok": True,
                "version": "0.11.2",
                "memories": 204,
                "messages": 53,
                "episodes": 18,
                "fts": True,
                "http_status": 200,
                "recent_facts": ["private fact must not leave the PC"],
            }
        return {"ok": True, "http_status": 200}

    try:
        remote.bridge_get = fake_get
        remote.disk_summary = lambda: {"free_gb": 1.0}
        remote.node_id = lambda: "vex-test"
        snapshot = remote.collect_snapshot(include_doctor=False)
        result = remote.execute_command({"action": "memory_status"}, allow_maintenance=False)
    finally:
        remote.bridge_get = original_get
        remote.disk_summary = original_disk
        remote.node_id = original_node

    expected = {
        "ok": True,
        "version": "0.11.2",
        "memories": 204,
        "messages": 53,
        "episodes": 18,
        "fts": True,
    }
    assert snapshot["memory"] == expected
    assert result["memory"] == {**expected, "http_status": 200}
    assert "private fact" not in json.dumps(snapshot)
    assert "private fact" not in json.dumps(result)


def test_source_guards() -> None:
    source = REMOTE_PATH.read_text(encoding="utf-8")
    assert 'VERSION = "0.11.7.5"' in source
    assert "for page in range(1, 101)" in source
    assert '?per_page=100&page={page}' in source
    assert 'action == "memory_status"' in source
    assert 'action == "adaptive_run"' in source
    assert "session remains active" in source


def main() -> int:
    remote = load_remote()
    test_fetches_commands_past_first_hundred(remote)
    test_memory_worker_is_visible_without_private_content(remote)
    test_source_guards()
    print("v0.11.7.5 Remote Support pagination and memory telemetry tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
