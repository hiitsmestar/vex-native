#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

REMOTE = Path("Tools/VexRemoteSupport.py")
remote = REMOTE.read_text(encoding="utf-8")

if 'VERSION = "0.11.7.67"' not in remote:
    raise SystemExit("v0.11.7.68 expected reconstructed v0.11.7.67 source")

remote = re.sub(r'^VERSION = "0\.11\.7\.67"', 'VERSION = "0.11.7.68"', remote, count=1, flags=re.M)

# Replace GitHub auth check with a fast token probe. The token is never logged,
# posted, or persisted by Vex Remote Support.
start = remote.find('def gh_ready() -> tuple[bool, str]:\n')
end = remote.find('\n\ndef ', start + 5)
if start < 0 or end < 0:
    raise SystemExit('gh_ready block missing')
new_ready = '''def gh_ready() -> tuple[bool, str]:
    gh = gh_path()
    if not gh:
        return False, "GitHub CLI is not installed"
    try:
        result = run_quiet([gh, "auth", "token", "-h", "github.com"], timeout=10)
        token = (result.stdout or "").strip()
        if result.returncode == 0 and token:
            return True, "GitHub access is ready"
        return False, "GitHub CLI is installed but not signed in"
    except Exception as exc:
        return False, f"GitHub check failed: {exc.__class__.__name__}"
'''
remote = remote[:start] + new_ready.rstrip() + remote[end:]

# Insert a direct HTTPS transport using the locally authenticated gh token.
# This avoids long-lived `gh api` subprocess stalls while preserving gh as fallback.
anchor = 'def fetch_comments() -> list[dict]:\n'
pos = remote.find(anchor)
if pos < 0:
    raise SystemExit('fetch_comments missing')
helper = '''_RELAY_TOKEN_CACHE: str | None = None


def relay_token() -> str:
    global _RELAY_TOKEN_CACHE
    if _RELAY_TOKEN_CACHE:
        return _RELAY_TOKEN_CACHE
    gh = gh_path()
    if not gh:
        raise RuntimeError("GitHub CLI is not installed")
    result = run_quiet([gh, "auth", "token", "-h", "github.com"], timeout=10)
    token = (result.stdout or "").strip()
    if result.returncode != 0 or not token:
        raise RuntimeError("GitHub authentication unavailable")
    _RELAY_TOKEN_CACHE = token
    return token


def relay_http(method: str, path: str, payload: dict | None = None, timeout: int = 25) -> Any:
    url = "https://api.github.com/" + path.lstrip("/")
    token = relay_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "VexRemoteSupport",
    }
    response = requests.request(method.upper(), url, headers=headers, json=payload, timeout=timeout)
    response.raise_for_status()
    if not response.content:
        return {}
    value = response.json()
    return value


def relay_api(method: str, path: str, payload: dict | None = None, timeout: int = 25) -> Any:
    try:
        return relay_http(method, path, payload=payload, timeout=timeout)
    except Exception:
        # Fallback keeps compatibility with machines where direct HTTPS is filtered.
        if method.upper() == "GET":
            return gh_api([path], timeout=timeout)
        return gh_api(["-X", method.upper(), path], timeout=timeout, input_json=payload or {})


'''
remote = remote[:pos] + helper + remote[pos:]

# Replace tail polling with the same bounded last-page strategy over direct HTTPS.
start = remote.find('def fetch_comments() -> list[dict]:\n')
end = remote.find('\n\ndef ', start + 5)
if start < 0 or end < 0:
    raise SystemExit('fetch_comments bounds missing')
new_fetch = '''def fetch_comments() -> list[dict]:
    issue = relay_api("GET", f"repos/{REPO}/issues/{ISSUE_NUMBER}", timeout=20)
    total = integer(issue.get("comments")) if isinstance(issue, dict) else 0
    last_page = max(1, (total + 99) // 100)
    pages = sorted({max(1, last_page - 1), last_page, last_page + 1})
    comments: list[dict] = []
    seen: set[int] = set()
    for page in pages:
        data = relay_api(
            "GET",
            f"repos/{REPO}/issues/{ISSUE_NUMBER}/comments?per_page=100&page={page}",
            timeout=20,
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
remote = remote[:start] + new_fetch.rstrip() + remote[end:]

# Send relay results/worklog over the same resilient transport.
start = remote.find('def post_comment(kind: str, payload: dict) -> None:\n')
end = remote.find('\n\ndef post_worklog', start)
if start < 0 or end < 0:
    raise SystemExit('post_comment block missing')
new_post = '''def post_comment(kind: str, payload: dict) -> None:
    envelope = {
        "kind": kind,
        "node_id": node_id(),
        "time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "payload": payload,
    }
    body = "VEXRESULT\\n```json\\n" + json.dumps(envelope, ensure_ascii=False, indent=2) + "\\n```"
    relay_api("POST", f"repos/{REPO}/issues/{ISSUE_NUMBER}/comments", {"body": body}, timeout=25)
'''
remote = remote[:start] + new_post.rstrip() + remote[end:]

start = remote.find('def post_worklog(event: str, payload: dict) -> None:\n')
end = remote.find('\n\ndef processed_command_ids', start)
if start < 0 or end < 0:
    raise SystemExit('post_worklog block missing')
new_worklog = '''def post_worklog(event: str, payload: dict) -> None:
    envelope = {
        "event": str(event or "")[:80],
        "node_id": node_id(),
        "agent_version": VERSION,
        "time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "payload": payload if isinstance(payload, dict) else {},
    }
    body = "VEXWORKLOG\\n```json\\n" + json.dumps(envelope, ensure_ascii=False, indent=2) + "\\n```"
    relay_api("POST", f"repos/{REPO}/issues/{WORKLOG_ISSUE_NUMBER}/comments", {"body": body}, timeout=25)
'''
remote = remote[:start] + new_worklog.rstrip() + remote[end:]

# Poll failures should not kill a persistent session. Retry next cycle and keep UI alive.
needle = '                comments = fetch_comments()\n                done = set(processed_command_ids())\n'
replacement = '''                try:
                    comments = fetch_comments()
                except Exception as exc:
                    self.on_status(f"Relay poll retrying: {exc.__class__.__name__}")
                    continue
                done = set(processed_command_ids())
'''
if needle not in remote:
    raise SystemExit('loop fetch marker missing')
remote = remote.replace(needle, replacement, 1)

REMOTE.write_text(remote, encoding="utf-8")
compile(remote, str(REMOTE), "exec")

checks = [
    'VERSION = "0.11.7.68"',
    'def relay_http(',
    'Authorization": f"Bearer {token}"',
    'Relay poll retrying:',
    'last_page + 1',
    'Start Persistent Session',
    'persistent_session_enabled_v67',
]
for marker in checks:
    if marker not in remote:
        raise SystemExit(f"v0.11.7.68 marker missing: {marker}")
print('Applied v0.11.7.68 resilient HTTP relay polling repair')
