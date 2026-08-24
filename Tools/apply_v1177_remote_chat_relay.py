#!/usr/bin/env python3
from pathlib import Path

# Keep the historical workflow entry point stable while the v2 patch applies
# the same remote-chat feature using structural matching against the current
# Remote Support command loop.
patch = Path("Tools/apply_v1177_remote_chat_relay_v2.py")
source = patch.read_text(encoding="utf-8")
compile(source, str(patch), "exec")
exec(compile(source, str(patch), "exec"), {"__name__": "__main__", "__file__": str(patch)})
