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

# Bind the Bridge before the potentially slow initial file crawl. The regular
# periodic reindex remains unchanged.
old_index = "    state.index.rebuild()\n    start_background_reindex(state)\n"
new_index = "\n".join([
    "    def initial_index_rebuild() -> None:",
    "        try:",
    "            state.index.rebuild()",
    "        except Exception as exc:",
    "            print(f\"[bridge] initial index failed: {exc.__class__.__name__}\", flush=True)",
    "",
    "    threading.Thread(",
    "        target=initial_index_rebuild,",
    "        daemon=True,",
    "        name=\"VexInitialIndex\",",
    "    ).start()",
    "    start_background_reindex(state)",
    "",
])
if old_index not in bridge:
    raise SystemExit("v0.11.7.12 Bridge initial-index anchor missing")
bridge = bridge.replace(old_index, new_index, 1)
bridge = bridge.replace('"version": "0.11.7.6"', '"version": "0.11.7.12"')

# Sanitized local health state: no tokens, ports, usernames, command lines, or
# personal paths are published.
class_anchor = "\n\nclass SupportWorker:\n"
if class_anchor not in remote:
    raise SystemExit("v0.11.7.12 SupportWorker anchor missing")
health_helpers = '''


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
    """Restart only VexBridge; use the existing watchdog as the fallback."""
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

active_anchor = (
    '            self.on_status("Support session is active")\n'
    '            while not self.stop_event.wait(POLL_SECONDS):\n'
)
active_replace = "\n".join([
    '            self.on_status("Support session is active")',
    '            last_bridge_reachable = None',
    '            bridge_unreachable_since = 0.0',
    '            last_bridge_recovery = 0.0',
    '            last_health_heartbeat = 0.0',
    '            while not self.stop_event.wait(POLL_SECONDS):',
    '',
])
if active_anchor not in remote:
    raise SystemExit("v0.11.7.12 support-loop start anchor missing")
remote = remote.replace(active_anchor, active_replace, 1)

# Insert health observation immediately before the existing comment fetch. This
# uses a small stable anchor from the current support loop rather than matching
# the whole block, which had made the previous patch brittle.
comments_anchor = "                comments = fetch_comments()\n"
if comments_anchor not in remote:
    raise SystemExit("v0.11.7.12 support-loop comments anchor missing")
health_loop = "\n".join([
    '                now = time.time()',
    '                health = _bridge_health_public()',
    '                reachable = bool(health.get("reachable"))',
    '                if last_bridge_reachable is None or reachable != last_bridge_reachable:',
    '                    try:',
    '                        post_comment("bridge_health_changed", health)',
    '                    except Exception:',
    '                        pass',
    '                    last_bridge_reachable = reachable',
    '                if now - last_health_heartbeat >= 300:',
    '                    try:',
    '                        post_comment("health_heartbeat", {"bridge": health, "agent_version": VERSION})',
    '                    except Exception:',
    '                        pass',
    '                    last_health_heartbeat = now',
    '',
    '                if reachable:',
    '                    bridge_unreachable_since = 0.0',
    '                else:',
    '                    if bridge_unreachable_since <= 0:',
    '                        bridge_unreachable_since = now',
    '                    allowed = bool(self.allow_maintenance())',
    '                    if (',
    '                        allowed',
    '                        and now - bridge_unreachable_since >= 180',
    '                        and now - last_bridge_recovery >= 600',
    '                    ):',
    '                        recovery = _bounded_bridge_recovery()',
    '                        try:',
    '                            post_comment("bridge_auto_recovery", recovery)',
    '                        except Exception:',
    '                            pass',
    '                        last_bridge_recovery = now',
    '                        bridge_unreachable_since = now',
    '',
])
remote = remote.replace(comments_anchor, health_loop + comments_anchor, 1)

# Read-only health action while preserving the existing bounded project controls.
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
