#!/usr/bin/env python3
from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
bridge = BRIDGE.read_text(encoding="utf-8")

# The .52 recall classifier replacement can remove the module-level state that
# sits immediately before _next_memory_reply_variant(). Restore it as the final
# recall patch so the formatter has a real lock and counter at runtime.
anchor = "def _next_memory_reply_variant() -> int:\n"
if anchor not in bridge:
    raise SystemExit("v0.11.7.52 variant-state hotfix anchor missing")

if "_MEMORY_REPLY_VARIANT_LOCK = threading.Lock()" not in bridge:
    bridge = bridge.replace(
        anchor,
        "_MEMORY_REPLY_VARIANT_LOCK = threading.Lock()\n_MEMORY_REPLY_VARIANT = 0\n\n\n" + anchor,
        1,
    )
elif "_MEMORY_REPLY_VARIANT = 0" not in bridge:
    lock = "_MEMORY_REPLY_VARIANT_LOCK = threading.Lock()\n"
    bridge = bridge.replace(lock, lock + "_MEMORY_REPLY_VARIANT = 0\n", 1)

for marker in [
    "_MEMORY_REPLY_VARIANT_LOCK = threading.Lock()",
    "_MEMORY_REPLY_VARIANT = 0",
    "def _next_memory_reply_variant() -> int:",
    '"agent_runtime_bundle": "0.11.7.52"',
]:
    if marker not in bridge:
        raise SystemExit(f"v0.11.7.52 variant-state marker missing: {marker}")

BRIDGE.write_text(bridge, encoding="utf-8")
compile(bridge, str(BRIDGE), "exec")
print("Applied v0.11.7.52 verified-memory reply variant state hotfix")
