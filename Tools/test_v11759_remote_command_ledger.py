#!/usr/bin/env python3
from pathlib import Path

path = Path("Tools/VexRemoteSupport.py")
text = path.read_text(encoding="utf-8")
compile(text, str(path), "exec")

required = [
    'VERSION = "0.11.7.59"',
    'WORKLOG_ISSUE_NUMBER = 79',
    'processed_command_ids_v59',
    'remember_processed_command(command_id)',
    'comments = fetch_comments()',
    'if command_id in done:',
    'post_worklog("remote_command_completed"',
]
for marker in required:
    if marker not in text:
        raise SystemExit(f"missing v0.11.7.59 marker: {marker}")

loop_start = text.find('    def loop(self) -> None:\n')
loop_end = text.find('\n\ndef main() -> int:', loop_start)
if loop_start < 0 or loop_end < 0:
    raise SystemExit("SupportWorker.loop bounds missing")
loop = text[loop_start:loop_end]
if 'last_comment_id' in loop:
    raise SystemExit("command polling still depends on shared last_comment_id cursor")
if 'cid <= last_id' in loop:
    raise SystemExit("legacy skip-by-comment-id logic survived")
print("v0.11.7.59 remote command ledger regression passed")
