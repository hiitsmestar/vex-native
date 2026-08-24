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

# The previous Bridge did its full initial file crawl before binding its HTTPS
# socket. On a large/slow corpus that makes an otherwise healthy process look
# dead to the phone and Remote Support for minutes. Start the index in a daemon
# thread so the server can bind immediately; normal 10-minute reindex remains.
old_index = "    state.index.rebuild()\n    start_background_reindex(state)\n"
new_index = '''    def initial_index_rebuild() -> None:\n        try:\n            state.index.rebuild()\n        except Exception as exc:\n            print(f"[bridge] initial index failed: {exc.__class__.__name__}", flush=True)\n\n    threading.Thread(\n        target=initial_index_rebuild,\n        daemon=True,\n        name="VexInitialIndex",\n    ).start()\n    start_background_reindex(state)\n'''
if old_index not in bridge:
    raise SystemExit("v0.11.7.12 Bridge initial-index anchor missing")
bridge = bridge.replace(old_index, new_index, 1)
bridge = bridge.replace('"version": "0.11.7.6"', '"version": "0.11.7.12"')

# Add sanitized local health state. This does not expose token, port, local path,
# usernames, or command line. It is used both for automatic outbound health
# reports and the existing bounded project-control UI.
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
    """Restart only VexBridge; let the existing watchdog relaunch it when present."""
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
'''
remote = remote.replace(class_anchor, health_helpers + class_anchor, 1)

# Initialize autonomous health tracking after a support session becomes active.
active_anchor = '            self.on_status("Support session is active")\n            while not self.stop_event.wait(POLL_SECONDS):\n'
active_replace = '''            self.on_status("Support session is active")\n            last_bridge_reachable = None\n            bridge_unreachable_since = 0.0\n            last_bridge_recovery = 0.0\n            last_health_heartbeat = 0.0\n            while not self.stop_event.wait(POLL_SECONDS):\n'''
if active_anchor not in remote:
    raise SystemExit("v0.11.7.12 support-loop start anchor missing")
remote = remote.replace(active_anchor, active_replace, 1)

# Perform local health observation before processing optional inbound commands.
# Reports are outbound and sanitized, so diagnostics no longer depend on a
# remote command being injected. Recovery is bounded to VexBridge and only runs
# when the user enabled the existing SAFE-maintenance checkbox for the session.
loop_anchor = '''                if time.time() - self.started_at >= SESSION_SECONDS:\n                    self.on_status("Support session ended after 2 hours")\n                    break\n                comments = fetch_comments()\n'''
loop_replace = '''                if time.time() - self.started_at >= SESSION_SECONDS:\n                    self.on_status("Support session ended after 2 hours")\n                    break\n\n                now = time.time()\n                health = _bridge_health_public()\n                reachable = bool(health.get("reachable"))\n                if last_bridge_reachable is None or reachable != last_bridge_reachable:\n                    try:\n                        post_comment("bridge_health_changed", health)\n                    except Exception:\n                        pass\n                    last_bridge_reachable = reachable\n                if now - last_health_heartbeat >= 300:\n                    try:\n                        post_comment("health_heartbeat", {"bridge": health, "agent_version": VERSION})\n                    except Exception:\n                        pass\n                    last_health_heartbeat = now\n\n                if reachable:\n                    bridge_unreachable_since = 0.0\n                else:\n                    if bridge_unreachable_since <= 0:\n                        bridge_unreachable_since = now\n                    allowed = bool(self.allow_maintenance())\n                    if (\n                        allowed\n                        and now - bridge_unreachable_since >= 180\n                        and now - last_bridge_recovery >= 600\n                    ):\n                        recovery = _bounded_bridge_recovery()\n                        try:\n                            post_comment("bridge_auto_recovery", recovery)\n                        except Exception:\n                            pass\n                        last_bridge_recovery = now\n                        bridge_unreachable_since = now\n\n                comments = fetch_comments()\n'''
if loop_anchor not in remote:
    raise SystemExit("v0.11.7.12 support-loop health anchor missing")
remote = remote.replace(loop_anchor, loop_replace, 1)

# Add a read-only local health action while preserving all v0.11.7.11 bounded controls.
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
