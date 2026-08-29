#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

REMOTE = Path("Tools/VexRemoteSupport.py")
remote = REMOTE.read_text(encoding="utf-8")

if 'VERSION = "0.11.7.58"' not in remote:
    raise SystemExit("v0.11.7.59 expected v0.11.7.58 Remote Support identity")

remote = re.sub(r'^VERSION = "0\.11\.7\.58"', 'VERSION = "0.11.7.59"', remote, count=1, flags=re.M)

issue_anchor = 'ISSUE_NUMBER = 52\n'
if issue_anchor not in remote:
    raise SystemExit("v0.11.7.59 relay issue anchor missing")
remote = remote.replace(issue_anchor, issue_anchor + 'WORKLOG_ISSUE_NUMBER = 79\n', 1)

post_anchor = '''def post_comment(kind: str, payload: dict) -> None:\n    envelope = {\n        "kind": kind,\n        "node_id": node_id(),\n        "time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),\n        "payload": payload,\n    }\n    body = "VEXRESULT\\n```json\\n" + json.dumps(envelope, ensure_ascii=False, indent=2) + "\\n```"\n    gh_api(["-X", "POST", f"repos/{REPO}/issues/{ISSUE_NUMBER}/comments"], timeout=30, input_json={"body": body})\n'''
if post_anchor not in remote:
    raise SystemExit("v0.11.7.59 post_comment anchor missing")
post_replacement = post_anchor + '''\n\ndef post_worklog(event: str, payload: dict) -> None:\n    envelope = {\n        "event": str(event or "")[:80],\n        "node_id": node_id(),\n        "agent_version": VERSION,\n        "time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),\n        "payload": payload if isinstance(payload, dict) else {},\n    }\n    body = "VEXWORKLOG\\n```json\\n" + json.dumps(envelope, ensure_ascii=False, indent=2) + "\\n```"\n    gh_api(["-X", "POST", f"repos/{REPO}/issues/{WORKLOG_ISSUE_NUMBER}/comments"], timeout=30, input_json={"body": body})\n\n\ndef processed_command_ids() -> list[str]:\n    state = load_state()\n    raw = state.get("processed_command_ids_v59")\n    if not isinstance(raw, list):\n        return []\n    out: list[str] = []\n    for value in raw[-500:]:\n        item = str(value or "").strip()[:120]\n        if item and item not in out:\n            out.append(item)\n    return out\n\n\ndef remember_processed_command(command_id: str) -> None:\n    command_id = str(command_id or "").strip()[:120]\n    if not command_id:\n        return\n    state = load_state()\n    values = processed_command_ids()\n    if command_id not in values:\n        values.append(command_id)\n    state["processed_command_ids_v59"] = values[-500:]\n    save_state(state)\n'''
remote = remote.replace(post_anchor, post_replacement, 1)

start = remote.find('    def loop(self) -> None:\n')
if start < 0:
    raise SystemExit("v0.11.7.59 SupportWorker.loop missing")
end = remote.find('\n\ndef main() -> int:', start)
if end < 0:
    raise SystemExit("v0.11.7.59 could not bound SupportWorker.loop")
loop = '''    def loop(self) -> None:\n        try:\n            ready, detail = gh_ready()\n            if not ready:\n                self.on_status(detail)\n                return\n            snapshot = collect_snapshot(include_doctor=False)\n            post_comment("session_started", snapshot)\n            try:\n                post_worklog("remote_session_started", {\n                    "remote_support": VERSION,\n                    "bridge_reachable": bool((snapshot.get("bridge") or {}).get("reachable")),\n                    "bridge_version": str((snapshot.get("bridge") or {}).get("version") or "")[:40] or None,\n                })\n            except Exception:\n                pass\n            self.on_status("Support session is active")\n            while not self.stop_event.wait(POLL_SECONDS):\n                if time.time() - self.started_at >= SESSION_SECONDS:\n                    self.on_status("Support session ended after 2 hours")\n                    break\n                comments = fetch_comments()\n                done = set(processed_command_ids())\n                for comment in comments:\n                    user = comment.get("user") if isinstance(comment.get("user"), dict) else {}\n                    if str(user.get("login") or "").lower() != OWNER.lower():\n                        continue\n                    command = parse_command(str(comment.get("body") or ""))\n                    if not command:\n                        continue\n                    target = str(command.get("node_id") or "").strip()\n                    if target and target != node_id() and target != "all":\n                        continue\n                    cid = integer(comment.get("id"))\n                    command_id = str(command.get("id") or f"comment-{cid}")[:120]\n                    if command_id in done:\n                        continue\n                    # Persist before execution so a restart cannot duplicate a mutating allowlisted command.\n                    remember_processed_command(command_id)\n                    done.add(command_id)\n                    action = str(command.get("action") or "")[:80]\n                    self.on_status(f"Running {action or 'command'}…")\n                    try:\n                        result = execute_command(command, allow_maintenance=bool(self.allow_maintenance()))\n                        post_comment("command_result", {"command_id": command_id, "action": action, "result": result})\n                        try:\n                            post_worklog("remote_command_completed", {\n                                "command_id": command_id,\n                                "action": action,\n                                "remote_support": VERSION,\n                                "ok": True,\n                            })\n                        except Exception:\n                            pass\n                    except Exception as exc:\n                        try:\n                            post_comment("command_result", {\n                                "command_id": command_id,\n                                "action": action,\n                                "result": {"ok": False, "error_class": exc.__class__.__name__},\n                            })\n                        except Exception:\n                            pass\n                        try:\n                            post_worklog("remote_command_failed", {\n                                "command_id": command_id,\n                                "action": action,\n                                "remote_support": VERSION,\n                                "error_class": exc.__class__.__name__,\n                            })\n                        except Exception:\n                            pass\n                    self.on_status("Support session is active")\n        except Exception as exc:\n            self.on_status(f"Support error: {exc.__class__.__name__}")\n            try:\n                post_worklog("remote_session_error", {"remote_support": VERSION, "error_class": exc.__class__.__name__})\n            except Exception:\n                pass\n        finally:\n            try:\n                post_comment("session_ended", {"reason": "stopped" if self.stop_event.is_set() else "timeout_or_error"})\n            except Exception:\n                pass\n'''
remote = remote[:start] + loop.rstrip() + remote[end:]

REMOTE.write_text(remote, encoding="utf-8")
compile(remote, str(REMOTE), "exec")

checks = [
    'VERSION = "0.11.7.59"',
    'WORKLOG_ISSUE_NUMBER = 79',
    'processed_command_ids_v59',
    'remember_processed_command(command_id)',
    'post_worklog("remote_session_started"',
    'post_worklog("remote_command_completed"',
]
for marker in checks:
    if marker not in remote:
        raise SystemExit(f"v0.11.7.59 marker missing: {marker}")
if 'last_comment_id' in remote[start:end]:
    raise SystemExit("v0.11.7.59 regression: SupportWorker.loop still depends on last_comment_id")
print("Applied v0.11.7.59 durable Remote Support command ledger + continuity worklog")
