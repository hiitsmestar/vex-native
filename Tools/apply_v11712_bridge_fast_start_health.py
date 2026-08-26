#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
REMOTE = Path("Tools/VexRemoteSupport.py")
bridge = BRIDGE.read_text(encoding="utf-8")
remote = REMOTE.read_text(encoding="utf-8")

if '"version": "0.11.7.6"' not in bridge:
    raise SystemExit("v0.11.7.12 expected Bridge v0.11.7.6 source")
if 'VERSION = "0.11.7.11"' not in remote:
    raise SystemExit("v0.11.7.12 expected Remote Support v0.11.7.11 source")

# Bind Bridge quickly by moving the initial index crawl to a daemon thread.
old_index = "    state.index.rebuild()\n    start_background_reindex(state)\n"
new_index = '''    def initial_index_rebuild() -> None:\n        try:\n            state.index.rebuild()\n        except Exception as exc:\n            print(f"[bridge] initial index failed: {exc.__class__.__name__}", flush=True)\n\n    threading.Thread(\n        target=initial_index_rebuild,\n        daemon=True,\n        name="VexInitialIndex",\n    ).start()\n    start_background_reindex(state)\n'''
if old_index not in bridge:
    raise SystemExit("v0.11.7.12 Bridge initial-index anchor missing")
bridge = bridge.replace(old_index, new_index, 1)
bridge = bridge.replace('"version": "0.11.7.6"', '"version": "0.11.7.12"')

# Health helpers live outside SupportWorker so the main support loop structure is
# left untouched. This avoids brittle insertion inside its try/except block.
class_anchor = "\n\nclass SupportWorker:\n"
if class_anchor not in remote:
    raise SystemExit("v0.11.7.12 SupportWorker anchor missing")
health_helpers = r'''


def _bridge_health_public() -> dict:
    status = bridge_get("/status", timeout=4)
    http_status = integer(status.get("http_status"))
    reachable = http_status in range(200, 300)
    return {
        "reachable": reachable,
        "version": str(status.get("version") or "")[:40] or None,
        "indexed_files": integer(status.get("indexed_files")),
        "uptime_seconds": integer(status.get("uptime_seconds")),
        "process_count": _project_process_count("VexBridge.exe"),
        "error_class": None if reachable else str(status.get("error") or "unreachable")[:80],
        "fast_start_expected": True,
    }


def _bounded_bridge_recovery() -> dict:
    before = _project_process_count("VexBridge.exe")
    stopped = _project_stop("bridge")
    time.sleep(3.5)
    after = _project_process_count("VexBridge.exe")
    fallback = None
    if after == 0:
        fallback = _project_start("watchdog")
        time.sleep(2.0)
        after = _project_process_count("VexBridge.exe")
    return {
        "ok": bool(after > 0),
        "before_process_count": before,
        "after_process_count": after,
        "stop_ok": bool(stopped.get("ok")),
        "watchdog_fallback_started": bool((fallback or {}).get("ok")),
        "scope": "VexBridge-only",
    }


def _bridge_health_monitor(worker) -> None:
    last_reachable = None
    unreachable_since = 0.0
    last_recovery = 0.0
    last_heartbeat = 0.0
    while not worker.stop_event.wait(POLL_SECONDS):
        if time.time() - worker.started_at >= SESSION_SECONDS:
            return
        now = time.time()
        health = _bridge_health_public()
        reachable = bool(health.get("reachable"))
        if last_reachable is None or reachable != last_reachable:
            try:
                post_comment("bridge_health_changed", health)
            except Exception:
                pass
            last_reachable = reachable
        if now - last_heartbeat >= 300:
            try:
                post_comment("health_heartbeat", {"bridge": health, "agent_version": VERSION})
            except Exception:
                pass
            last_heartbeat = now
        if reachable:
            unreachable_since = 0.0
            continue
        if unreachable_since <= 0:
            unreachable_since = now
        try:
            allowed = bool(worker.allow_maintenance())
        except Exception:
            allowed = False
        if allowed and now - unreachable_since >= 180 and now - last_recovery >= 600:
            recovery = _bounded_bridge_recovery()
            try:
                post_comment("bridge_auto_recovery", recovery)
            except Exception:
                pass
            last_recovery = now
            unreachable_since = now
'''
remote = remote.replace(class_anchor, health_helpers + class_anchor, 1)

# Start the independent health monitor immediately after the support session is active.
active_anchor = '            self.on_status("Support session is active")\n            while not self.stop_event.wait(POLL_SECONDS):\n'
active_replace = '''            self.on_status("Support session is active")\n            threading.Thread(\n                target=_bridge_health_monitor,\n                args=(self,),\n                daemon=True,\n                name="VexBridgeHealthMonitor",\n            ).start()\n            while not self.stop_event.wait(POLL_SECONDS):\n'''
if active_anchor not in remote:
    raise SystemExit("v0.11.7.12 support-loop start anchor missing")
remote = remote.replace(active_anchor, active_replace, 1)

# Preserve a read-only explicit health action alongside the autonomous outbound reports.
action_anchor = '    if action == "project_status":\n'
if action_anchor not in remote:
    raise SystemExit("v0.11.7.12 project_status action anchor missing")
remote = remote.replace(
    action_anchor,
    '    if action == "bridge_health":\n        return {"bridge_health": _bridge_health_public()}\n' + action_anchor,
    1,
)
remote = re.sub(r'^VERSION = "[^"]+"', 'VERSION = "0.11.7.12"', remote, count=1, flags=re.M)

BRIDGE.write_text(bridge, encoding="utf-8")
REMOTE.write_text(remote, encoding="utf-8")
compile(bridge, str(BRIDGE), "exec")
compile(remote, str(REMOTE), "exec")

for marker in [
    '"version": "0.11.7.12"',
    'name="VexInitialIndex"',
    'target=initial_index_rebuild',
]:
    if marker not in bridge:
        raise SystemExit(f"v0.11.7.12 Bridge verifier missing: {marker}")
for marker in [
    'VERSION = "0.11.7.12"',
    'def _bridge_health_public()',
    'def _bounded_bridge_recovery()',
    'def _bridge_health_monitor(worker)',
    'name="VexBridgeHealthMonitor"',
    '"bridge_health_changed"',
    '"health_heartbeat"',
    '"bridge_auto_recovery"',
    'action == "bridge_health"',
    'action == "safe_update"',
    'http://127.0.0.1:11434/api/chat',
]:
    if marker not in remote:
        raise SystemExit(f"v0.11.7.12 Remote Support verifier missing: {marker}")

print("Applied v0.11.7.12 Bridge fast-start + autonomous bounded health recovery")
