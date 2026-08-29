#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

REMOTE = Path("Tools/VexRemoteSupport.py")
remote = REMOTE.read_text(encoding="utf-8")

if 'VERSION = "0.11.7.57"' not in remote:
    raise SystemExit("v0.11.7.58 expected v0.11.7.57 Remote Support identity")

old = '''def fetch_comments() -> list[dict]:
    data = gh_api([f"repos/{REPO}/issues/{ISSUE_NUMBER}/comments?per_page=100"], timeout=30)
    return data if isinstance(data, list) else []
'''
new = '''def fetch_comments() -> list[dict]:
    # Issue #52 is a long-lived relay. GitHub returns the *oldest* 100 comments
    # when page is omitted, which eventually makes a healthy agent blind to new
    # VEXCMD messages. Read only the newest two pages: enough overlap for races,
    # bounded work every poll, and no full-history download.
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
if old not in remote:
    raise SystemExit("v0.11.7.58 first-page-only fetch_comments anchor missing")
remote = remote.replace(old, new, 1)
remote = re.sub(r'^VERSION = "0\.11\.7\.57"', 'VERSION = "0.11.7.58"', remote, count=1, flags=re.M)

REMOTE.write_text(remote, encoding="utf-8")
compile(remote, str(REMOTE), "exec")

for marker in [
    'VERSION = "0.11.7.58"',
    'last_page = max(1, (total + 99) // 100)',
    'max(1, last_page - 1)',
    'comments?per_page=100&page={page}',
]:
    if marker not in remote:
        raise SystemExit(f"v0.11.7.58 relay marker missing: {marker}")

if 'comments?per_page=100"], timeout=30)' in remote:
    raise SystemExit("v0.11.7.58 regression: unpaged first-page relay poll survived")

print("Applied v0.11.7.58 Remote Support newest-page relay polling fix")
