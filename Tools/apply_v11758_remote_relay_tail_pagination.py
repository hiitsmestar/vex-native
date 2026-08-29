#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

REMOTE = Path("Tools/VexRemoteSupport.py")
remote = REMOTE.read_text(encoding="utf-8")

if 'VERSION = "0.11.7.57"' not in remote:
    raise SystemExit("v0.11.7.58 expected v0.11.7.57 Remote Support identity")

# v0.11.7.5 fixed the original 100-comment blindness by walking pages 1..100.
# Issue #52 has now grown large enough that replaying its whole history every 15s
# is wasteful and can delay fresh command handling. Replace the current assembled
# function by bounds, not by an obsolete exact-text anchor, so this patch applies
# cleanly after every carried .57 layer.
start = remote.find("def fetch_comments() -> list[dict]:")
if start < 0:
    raise SystemExit("v0.11.7.58 fetch_comments function missing")
end = remote.find("\n\ndef ", start + 5)
if end < 0:
    raise SystemExit("v0.11.7.58 could not bound fetch_comments function")
current = remote[start:end]
if "comments?per_page=100&page={page}" not in current:
    raise SystemExit("v0.11.7.58 expected paged relay source marker missing")

new = '''def fetch_comments() -> list[dict]:
    # Read only the newest two issue-comment pages. That keeps the relay bounded
    # while retaining overlap for commands posted during a page rollover.
    issue = gh_api([f"repos/{REPO}/issues/{ISSUE_NUMBER}"], timeout=30)
    total = integer(issue.get("comments")) if isinstance(issue, dict) else 0
    last_page = max(1, (total + 99) // 100)
    pages = sorted({max(1, last_page - 1), last_page})
    comments: list[dict] = []
    seen: set[int] = set()
    for page in pages:
        data = gh_api(
            [f"repos/{REPO}/issues/{ISSUE_NUMBER}/comments?per_page=100&page={page}"],
            timeout=30,
        )
        if not isinstance(data, list):
            continue
        for item in data:
            if not isinstance(item, dict):
                continue
            comment_id = integer(item.get("id"))
            if comment_id and comment_id in seen:
                continue
            if comment_id:
                seen.add(comment_id)
            comments.append(item)
    comments.sort(key=lambda item: integer(item.get("id")))
    return comments
'''
remote = remote[:start] + new.rstrip() + remote[end:]
remote = re.sub(r'^VERSION = "0\.11\.7\.57"', 'VERSION = "0.11.7.58"', remote, count=1, flags=re.M)

REMOTE.write_text(remote, encoding="utf-8")
compile(remote, str(REMOTE), "exec")

for marker in [
    'VERSION = "0.11.7.58"',
    'last_page = max(1, (total + 99) // 100)',
    'pages = sorted({max(1, last_page - 1), last_page})',
    'comments?per_page=100&page={page}',
    'comments.sort(key=lambda item: integer(item.get("id")))',
]:
    if marker not in remote:
        raise SystemExit(f"v0.11.7.58 relay marker missing: {marker}")

# The old full-history loop is the regression we are removing.
if "for page in range(1, 101)" in remote[start:remote.find("\n\ndef ", start + 5)]:
    raise SystemExit("v0.11.7.58 regression: full-history relay loop survived")

print("Applied v0.11.7.58 bounded newest-page Remote Support relay fix")
