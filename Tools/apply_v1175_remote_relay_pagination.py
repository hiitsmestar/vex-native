#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path


REMOTE_PATH = Path("Tools/VexRemoteSupport.py")
remote = REMOTE_PATH.read_text(encoding="utf-8")

if 'VERSION = "0.11.7.4"' not in remote:
    raise SystemExit("v0.11.7.5 expected the v0.11.7.4 Remote Support source")
remote = re.sub(
    r'^VERSION = "[^"]+"',
    'VERSION = "0.11.7.5"',
    remote,
    count=1,
    flags=re.M,
)


def replace_function(name: str, replacement: str) -> None:
    global remote
    start = remote.find(f"def {name}(")
    if start < 0:
        raise SystemExit(f"v0.11.7.5 missing Remote Support function: {name}")
    end = remote.find("\n\ndef ", start + 5)
    if end < 0:
        raise SystemExit(f"v0.11.7.5 could not bound Remote Support function: {name}")
    remote = remote[:start] + replacement.rstrip() + remote[end:]


# Issue #52 is a long-lived relay. Once it crossed 100 comments, the old single-page
# fetch made every new command invisible even though the support session stayed live.
replace_function(
    "fetch_comments",
    '''def fetch_comments() -> list[dict]:
    comments: list[dict] = []
    for page in range(1, 101):
        data = gh_api([
            f"repos/{REPO}/issues/{ISSUE_NUMBER}/comments?per_page=100&page={page}"
        ], timeout=30)
        if not isinstance(data, list):
            break
        comments.extend(item for item in data if isinstance(item, dict))
        if len(data) < 100:
            break
    return comments
''',
)


# The v0.10.0 Remote Support patch rebuilds collect_snapshot/execute_command from an
# older source shape. Restore the sanitized Memory Worker telemetry after that patch.
coordination_anchor = '''    coordination = bridge_get("/cognition/coordination", timeout=8)
    snap = {
'''
coordination_replacement = '''    coordination = bridge_get("/cognition/coordination", timeout=8)
    memory = bridge_get("/memory/status", timeout=8)
    snap = {
'''
if coordination_anchor not in remote:
    raise SystemExit("v0.11.7.5 memory snapshot request anchor missing")
remote = remote.replace(coordination_anchor, coordination_replacement, 1)

maintenance_anchor = '''        "maintenance": maintenance_public(maintenance),
        "initiative": initiative_public(initiative),
'''
maintenance_replacement = '''        "maintenance": maintenance_public(maintenance),
        "memory": {
            "ok": yes(memory.get("ok")),
            "version": str(memory.get("version") or "")[:40] or None,
            "memories": integer(memory.get("memories")),
            "messages": integer(memory.get("messages")),
            "episodes": integer(memory.get("episodes")),
            "fts": yes(memory.get("fts")),
        },
        "initiative": initiative_public(initiative),
'''
if maintenance_anchor not in remote:
    raise SystemExit("v0.11.7.5 memory snapshot payload anchor missing")
remote = remote.replace(maintenance_anchor, maintenance_replacement, 1)

art_anchor = '''    if action == "art_worker_status":
        return {"art_worker": art_worker_command(["--quick-status"], timeout=45)}
'''
memory_action = art_anchor + '''    if action == "memory_status":
        m = bridge_get("/memory/status", timeout=8)
        return {"memory": {
            "ok": yes(m.get("ok")),
            "version": str(m.get("version") or "")[:40] or None,
            "memories": integer(m.get("memories")),
            "messages": integer(m.get("messages")),
            "episodes": integer(m.get("episodes")),
            "fts": yes(m.get("fts")),
            "http_status": integer(m.get("http_status")),
        }}
'''
if art_anchor not in remote:
    raise SystemExit("v0.11.7.5 memory command anchor missing")
remote = remote.replace(art_anchor, memory_action, 1)

REMOTE_PATH.write_text(remote, encoding="utf-8")
compile(remote, str(REMOTE_PATH), "exec")

checks = [
    'VERSION = "0.11.7.5"',
    "for page in range(1, 101)",
    "comments.extend(item for item in data",
    'memory = bridge_get("/memory/status", timeout=8)',
    'action == "memory_status"',
    'action == "adaptive_run"',
    "session remains active",
]
final = REMOTE_PATH.read_text(encoding="utf-8")
for marker in checks:
    if marker not in final:
        raise SystemExit(f"v0.11.7.5 Remote Support verifier missing: {marker}")

print("Applied v0.11.7.5 Remote Support relay pagination + memory telemetry hotfix")
