#!/usr/bin/env python3
from pathlib import Path

path = Path("Tools/VexRemoteSupport.py")
text = path.read_text(encoding="utf-8")

old = '''def fetch_comments() -> list[dict]:
    data = gh_api([f"repos/{REPO}/issues/{ISSUE_NUMBER}/comments?per_page=100"], timeout=30)
    return data if isinstance(data, list) else []
'''
new = '''def fetch_comments() -> list[dict]:
    # Issue #52 is a long-lived diagnostic relay and can exceed one GitHub API page.
    # The old implementation permanently stopped seeing new VEXCMD comments after
    # comment 100 even though the session UI still said active.
    comments: list[dict] = []
    for page in range(1, 21):
        data = gh_api([
            f"repos/{REPO}/issues/{ISSUE_NUMBER}/comments?per_page=100&page={page}"
        ], timeout=30)
        if not isinstance(data, list):
            break
        comments.extend(item for item in data if isinstance(item, dict))
        if len(data) < 100:
            break
    return comments
'''
if old not in text:
    raise SystemExit("Remote Support pagination anchor missing")
text = text.replace(old, new, 1)

# Include local personal-memory health in sanitized snapshots. Counts only; no
# private memory contents are ever published to the public relay.
old_collect = '''    maintenance = bridge_get("/maintenance/status", timeout=20)
    snap = {
'''
new_collect = '''    maintenance = bridge_get("/maintenance/status", timeout=20)
    memory = bridge_get("/memory/status", timeout=8)
    snap = {
'''
if old_collect in text:
    text = text.replace(old_collect, new_collect, 1)

old_storage = '''        "maintenance": maintenance_public(maintenance),
        "storage": disk_summary(),
'''
new_storage = '''        "maintenance": maintenance_public(maintenance),
        "memory": {
            "ok": yes(memory.get("ok")),
            "version": str(memory.get("version") or "")[:40] or None,
            "memories": integer(memory.get("memories")),
            "messages": integer(memory.get("messages")),
            "episodes": integer(memory.get("episodes")),
            "fts": yes(memory.get("fts")),
        },
        "storage": disk_summary(),
'''
if old_storage in text:
    text = text.replace(old_storage, new_storage, 1)

old_action = '''    if action == "learning_status":
        return {"learning": learning_public(bridge_get("/learning/status", timeout=12))}
'''
new_action = '''    if action == "memory_status":
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
    if action == "learning_status":
        return {"learning": learning_public(bridge_get("/learning/status", timeout=12))}
'''
if old_action in text:
    text = text.replace(old_action, new_action, 1)

text = text.replace('VERSION = "0.9.9"', 'VERSION = "0.11.1"', 1)
path.write_text(text, encoding="utf-8")
compile(text, str(path), "exec")
for marker in ["page={page}", 'action == "memory_status"', '"memory": {', 'VERSION = "0.11.1"']:
    if marker not in text:
        raise SystemExit(f"missing v0.11.1 relay marker: {marker}")
print("Applied v0.11.1 Remote Support pagination + memory telemetry hotfix")
