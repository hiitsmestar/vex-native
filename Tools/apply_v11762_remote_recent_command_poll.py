#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

REMOTE = Path("Tools/VexRemoteSupport.py")
remote = REMOTE.read_text(encoding="utf-8")

if 'VERSION = "0.11.7.61"' not in remote:
    raise SystemExit("v0.11.7.62 expected v0.11.7.61 Remote Support identity")

start = remote.find("def fetch_comments() -> list[dict]:")
if start < 0:
    raise SystemExit("v0.11.7.62 fetch_comments function missing")
end = remote.find("\n\ndef ", start + 5)
if end < 0:
    raise SystemExit("v0.11.7.62 could not bound fetch_comments function")

new = '''def fetch_comments() -> list[dict]:
    # GitHub's issue-level comments count can briefly lag the comments collection
    # at a 100-comment page boundary. Poll the calculated tail plus one page ahead
    # so a freshly posted command on the new page cannot become invisible.
    issue = gh_api([f"repos/{REPO}/issues/{ISSUE_NUMBER}"], timeout=30)
    total = integer(issue.get("comments")) if isinstance(issue, dict) else 0
    last_page = max(1, (total + 99) // 100)
    pages = sorted({max(1, last_page - 1), last_page, last_page + 1})
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
remote = re.sub(r'^VERSION = "0\.11\.7\.61"', 'VERSION = "0.11.7.62"', remote, count=1, flags=re.M)

REMOTE.write_text(remote, encoding="utf-8")
compile(remote, str(REMOTE), "exec")

checks = [
    'VERSION = "0.11.7.62"',
    'last_page + 1',
    'pages = sorted({max(1, last_page - 1), last_page, last_page + 1})',
    'comments?per_page=100&page={page}',
]
for marker in checks:
    if marker not in remote:
        raise SystemExit(f"v0.11.7.62 marker missing: {marker}")

print("Applied v0.11.7.62 Remote Support page-boundary fresh-command polling fix")
