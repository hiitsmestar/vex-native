#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
MARKER = 'V120_ART_IDLE_ON_DEMAND = "v0.12-art-idle-on-demand-v1"'

text = BRIDGE.read_text(encoding="utf-8")
if '"agent_runtime_bundle": "0.12.0"' not in text:
    raise SystemExit("v0.12 art-idle layer requires generated v0.12 Bridge")

if MARKER not in text:
    anchor = "class Handler(BaseHTTPRequestHandler):\n"
    if anchor not in text:
        raise SystemExit("v0.12 art-idle Handler anchor missing")

    layer = r'''
# ---------------------------------------------------------------------------
# v0.12 idle-art semantics
#
# Art is intentionally an on-demand worker. The background autonomy health loop
# must not classify "installed but currently asleep" as a failure and repeatedly
# wake/repair ComfyUI. Foreground art requests keep their existing bounded repair
# path; this wrapper changes only the idle capability probe.
# ---------------------------------------------------------------------------
V120_ART_IDLE_ON_DEMAND = "v0.12-art-idle-on-demand-v1"
_v120_art_idle_probe_base = _autonomy_probe_capability


def _v120_art_idle_resolve_gap() -> None:
    try:
        resolver = globals().get("_v11771_resolve_gap")
        if callable(resolver):
            resolver("local capability art_worker is unhealthy")
            return
        with _ADAPTIVE_DB_LOCK:
            conn = _adaptive_conn()
            conn.execute(
                "UPDATE gaps SET status='resolved',updated_at=? "
                "WHERE status='open' AND request_text=?",
                (time.time(), "local capability art_worker is unhealthy"),
            )
            conn.commit()
            conn.close()
    except Exception:
        pass


def _autonomy_probe_capability(name: str) -> tuple[bool, str]:
    if str(name or "") != "art_worker":
        return _v120_art_idle_probe_base(name)

    try:
        installed_fn = globals().get("_sr_art_installed")
        installed = bool(callable(installed_fn) and installed_fn())
        if not installed:
            _v120_art_idle_resolve_gap()
            return True, "art worker not installed on this node"

        health_fn = globals().get("_art_comfy_health")
        if callable(health_fn):
            try:
                if bool(health_fn(timeout=1.8)):
                    _v120_art_idle_resolve_gap()
                    return True, "healthy"
            except Exception:
                pass

        # A stopped on-demand renderer is normal during idle time. Do not invoke
        # include_art=True here. The foreground render path still owns startup,
        # repair, queue handling, and its resource/circuit-breaker checks.
        _v120_art_idle_resolve_gap()
        return True, "installed; idle/on-demand"
    except Exception as exc:
        # Probe failures should not create an endless repair loop for an optional
        # on-demand worker. Actual render requests still surface/repair real faults.
        _v120_art_idle_resolve_gap()
        return True, f"installed; idle/on-demand ({exc.__class__.__name__})"
'''

    text = text.replace(anchor, layer + "\n\n" + anchor, 1)

BRIDGE.write_text(text, encoding="utf-8")
compile(text, str(BRIDGE), "exec")

final = BRIDGE.read_text(encoding="utf-8")
for required in [
    MARKER,
    "_v120_art_idle_probe_base = _autonomy_probe_capability",
    'return True, "installed; idle/on-demand"',
    "Foreground art requests keep their existing bounded repair",
]:
    if required not in final:
        raise SystemExit(f"v0.12 art-idle invariant missing: {required}")

print("Applied v0.12 idle-art on-demand health semantics")
