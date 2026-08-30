#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

REMOTE = Path("Tools/VexRemoteSupport.py")
remote = REMOTE.read_text(encoding="utf-8")

if 'VERSION = "0.11.7.62"' not in remote:
    raise SystemExit("v0.11.7.67 expected reconstructed v0.11.7.62 Remote Support source")

remote = re.sub(r'^VERSION = "0\.11\.7\.62"', 'VERSION = "0.11.7.67"', remote, count=1, flags=re.M)
remote = re.sub(r'^SESSION_SECONDS = .*$', 'SESSION_SECONDS = None  # persistent until locally stopped or app exits', remote, count=1, flags=re.M)
remote = remote.replace(
    '                if time.time() - self.started_at >= SESSION_SECONDS:\n                    self.on_status("Support session ended after 2 hours")\n                    break\n',
    '',
)
remote = remote.replace('text="Start 2-Hour Session"', 'text="Start Persistent Session"')

# Persist an explicit local preference so a user who installed this build does not
# have to press Start again after Windows/app restarts. Stop Session clears it.
remote = remote.replace(
    '    def start_session() -> None:\n        ready, detail = gh_ready()\n        if not ready:\n            messagebox.showwarning("Vex Remote Support", detail + ". Use Set Up GitHub first.")\n            return\n        worker.start()\n        status_var.set("Starting support session…")\n',
    '    def start_session() -> None:\n        ready, detail = gh_ready()\n        if not ready:\n            messagebox.showwarning("Vex Remote Support", detail + ". Use Set Up GitHub first.")\n            return\n        state = load_state()\n        state["persistent_session_enabled_v67"] = True\n        save_state(state)\n        worker.start()\n        status_var.set("Starting persistent support session…")\n',
)
remote = remote.replace(
    '    def stop_session() -> None:\n        worker.stop()\n        status_var.set("Stopping support session…")\n',
    '    def stop_session() -> None:\n        state = load_state()\n        state["persistent_session_enabled_v67"] = False\n        save_state(state)\n        worker.stop()\n        status_var.set("Stopping support session…")\n',
)

# Auto-resume only if this v67 preference has previously been enabled locally.
auto_anchor = '    worker.on_status = set_status\n\n'
if auto_anchor not in remote:
    raise SystemExit("v0.11.7.67 worker status anchor missing")
remote = remote.replace(
    auto_anchor,
    auto_anchor + '    if bool(load_state().get("persistent_session_enabled_v67")):\n        root.after(800, worker.start)\n\n',
    1,
)

REMOTE.write_text(remote, encoding="utf-8")
compile(remote, str(REMOTE), "exec")

checks = [
    'VERSION = "0.11.7.67"',
    'SESSION_SECONDS = None',
    'Start Persistent Session',
    'persistent_session_enabled_v67',
]
for marker in checks:
    if marker not in remote:
        raise SystemExit(f"v0.11.7.67 marker missing: {marker}")
if 'Support session ended after 2 hours' in remote:
    raise SystemExit('v0.11.7.67 still contains 2-hour timeout')
print('Applied v0.11.7.67 persistent Remote Support session behavior')
