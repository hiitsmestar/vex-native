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

text = text.replace('VERSION = "0.9.9"', 'VERSION = "0.11.2"', 1)
text = text.replace('VERSION = "0.11.1"', 'VERSION = "0.11.2"', 1)

# Some historical patch/build paths can collapse the Windows raw-string root into
# invalid source (r"C:\"). Normalize that single line before compiling.
lines = text.splitlines()
for index, line in enumerate(lines):
    if "usage = shutil.disk_usage(Path.home().anchor" in line:
        indent = line[:len(line) - len(line.lstrip())]
        lines[index] = indent + 'usage = shutil.disk_usage(Path.home().anchor or "C:\\\\")'
text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")

path.write_text(text, encoding="utf-8")
compile(text, str(path), "exec")
for marker in ["page={page}", 'action == "memory_status"', '"memory": {', 'VERSION = "0.11.2"']:
    if marker not in text:
        raise SystemExit(f"missing relay marker: {marker}")
print("Applied v0.11.2 Remote Support pagination + memory telemetry hotfix")
