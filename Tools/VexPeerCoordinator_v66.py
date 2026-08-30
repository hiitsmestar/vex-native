# VexNative peer coordinator v0.11.7.66 startup-repair build
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

VERSION = "0.11.7.66"
REPO = "hiitsmestar/vex-native"
ISSUE_NUMBER = 52
DEFAULT_PEER_NODE = "vex-8d8b20e0"
DEFAULT_INTERVAL_SECONDS = 1800
DEFAULT_TIMEOUT_SECONDS = 90
APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "VexPeerCoordinator"
STATE_PATH = APP_DIR / "state.json"
LOG_PATH = APP_DIR / "coordinator.log"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log_event(event: str, **fields) -> None:
    try:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        row = {"time_utc": utc_now(), "event": event, "version": VERSION, **fields}
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, sort_keys=True) + "\n")
    except Exception:
        pass


def load_state() -> dict:
    try:
        state = json.loads(STATE_PATH.read_text("utf-8"))
    except Exception:
        state = {}
    state.setdefault("version", VERSION)
    state.setdefault("peer_node_id", DEFAULT_PEER_NODE)
    state.setdefault("role", "upstairs-primary")
    state.setdefault("interval_seconds", DEFAULT_INTERVAL_SECONDS)
    return state


def save_state(state: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    clean = dict(state)
    clean["version"] = VERSION
    STATE_PATH.write_text(json.dumps(clean, indent=2, sort_keys=True), "utf-8")


def run_gh(args: list[str], timeout: int = 45) -> str:
    candidates = ["gh"]
    pf = os.environ.get("ProgramFiles")
    if pf:
        candidates.append(str(Path(pf) / "GitHub CLI" / "gh.exe"))
    last_error: Exception | None = None
    for exe in candidates:
        try:
            proc = subprocess.run([exe, *args], text=True, capture_output=True, timeout=timeout, check=False)
            if proc.returncode == 0:
                return proc.stdout
            last_error = RuntimeError((proc.stderr or proc.stdout or "gh failed").strip()[:500])
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"GitHub CLI unavailable: {last_error.__class__.__name__ if last_error else 'unknown'}")


def gh_json(endpoint: str, timeout: int = 45):
    return json.loads(run_gh(["api", endpoint], timeout=timeout))


def post_command(peer_node_id: str, action: str) -> str:
    command_id = f"peer-v11766-{action}-{uuid.uuid4().hex[:10]}"
    body = "VEXCMD " + json.dumps({"id": command_id, "node_id": peer_node_id, "action": action}, separators=(",", ":"))
    run_gh(["api", "-X", "POST", f"repos/{REPO}/issues/{ISSUE_NUMBER}/comments", "-f", f"body={body}"])
    return command_id


def recent_comments() -> list[dict]:
    issue = gh_json(f"repos/{REPO}/issues/{ISSUE_NUMBER}")
    total = int(issue.get("comments") or 0) if isinstance(issue, dict) else 0
    last_page = max(1, (total + 99) // 100)
    pages = sorted({max(1, last_page - 1), last_page, last_page + 1})
    out: list[dict] = []
    seen: set[int] = set()
    for page in pages:
        data = gh_json(f"repos/{REPO}/issues/{ISSUE_NUMBER}/comments?per_page=100&page={page}")
        if not isinstance(data, list):
            continue
        for item in data:
            if not isinstance(item, dict):
                continue
            cid = int(item.get("id") or 0)
            if cid and cid in seen:
                continue
            if cid:
                seen.add(cid)
            out.append(item)
    out.sort(key=lambda item: int(item.get("id") or 0))
    return out


def parse_vexresult(body: str) -> dict | None:
    if not body.startswith("VEXRESULT"):
        return None
    match = re.search(r"```json\s*(\{.*?\})\s*```", body, flags=re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def wait_for_result(command_id: str, peer_node_id: str, timeout_seconds: int) -> dict:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        for comment in reversed(recent_comments()):
            envelope = parse_vexresult(str(comment.get("body") or ""))
            if not envelope or envelope.get("kind") != "command_result":
                continue
            if str(envelope.get("node_id") or "") != peer_node_id:
                continue
            payload = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else {}
            if str(payload.get("command_id") or "") == command_id:
                return payload
        time.sleep(5)
    raise TimeoutError("peer command timed out")


def summarize_status(payload: dict) -> dict:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    bridge = result.get("bridge") if isinstance(result.get("bridge"), dict) else {}
    cognition = result.get("cognition") if isinstance(result.get("cognition"), dict) else {}
    return {
        "online": True,
        "agent_version": result.get("agent_version"),
        "bridge_reachable": bool(bridge.get("reachable")),
        "bridge_version": bridge.get("version"),
        "cognition_ok": bool(cognition.get("ok")),
        "cognition_model": cognition.get("model"),
    }


def coordinate_once(state: dict, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> dict:
    peer = str(state.get("peer_node_id") or DEFAULT_PEER_NODE).strip()
    started = time.time()
    command_id = post_command(peer, "status")
    log_event("command_posted", command_id=command_id, peer_node_id=peer)
    payload = wait_for_result(command_id, peer, timeout_seconds)
    summary = summarize_status(payload)
    summary.update({"peer_node_id": peer, "command_id": command_id, "checked_at_utc": utc_now(), "round_trip_seconds": round(time.time() - started, 2), "secondary_ready": bool(summary.get("bridge_reachable") and summary.get("cognition_ok"))})
    state["last_peer"] = summary
    state["last_success_utc"] = summary["checked_at_utc"]
    state["consecutive_failures"] = 0
    save_state(state)
    log_event("coordination_success", command_id=command_id, secondary_ready=summary["secondary_ready"], round_trip_seconds=summary["round_trip_seconds"])
    return summary


def self_test() -> int:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    log_event("self_test")
    sample = {"payload": {"result": {"agent_version": "0.11.7.62", "bridge": {"reachable": True, "version": "0.11.7.39"}, "cognition": {"ok": True, "model": "test"}}}}
    summary = summarize_status(sample["payload"])
    assert summary["bridge_reachable"] and summary["cognition_ok"]
    print("VexPeerCoordinator v0.11.7.66 self-test OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="VexNative dual-PC peer coordinator")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--peer-node-id")
    parser.add_argument("--interval", type=int)
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    log_event("process_started")
    state = load_state()
    if args.peer_node_id:
        state["peer_node_id"] = args.peer_node_id.strip()
    if args.interval:
        state["interval_seconds"] = max(300, int(args.interval))
    save_state(state)
    if args.once:
        try:
            print(json.dumps(coordinate_once(state), indent=2))
            return 0
        except Exception as exc:
            log_event("coordination_failure", error_class=exc.__class__.__name__)
            return 2
    while True:
        try:
            coordinate_once(state)
        except Exception as exc:
            state["last_failure_utc"] = utc_now()
            state["last_error_class"] = exc.__class__.__name__
            state["consecutive_failures"] = int(state.get("consecutive_failures") or 0) + 1
            save_state(state)
            log_event("coordination_failure", error_class=exc.__class__.__name__, consecutive_failures=state["consecutive_failures"])
        time.sleep(max(300, int(state.get("interval_seconds") or DEFAULT_INTERVAL_SECONDS)))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        log_event("fatal_startup", error_class=exc.__class__.__name__)
        raise
