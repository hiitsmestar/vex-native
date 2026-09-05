#!/usr/bin/env python3
from pathlib import Path

BRIDGE = Path("Bridge/vex_bridge.py")
text = BRIDGE.read_text(encoding="utf-8")

MARKER = "V120_WANTS_CAPABILITY_DISCOVERY_v1"
anchor = '''LOCAL PRIVATE MEMORY GUIDANCE (local model only; never copy biography into lessons or web queries):
{private_memory_guidance}

RECENT REAL EXCHANGES:'''
replacement = '''LOCAL PRIVATE MEMORY GUIDANCE (local model only; never copy biography into lessons or web queries):
{private_memory_guidance}

STANDING SELF-IMPROVEMENT DISCOVERY PASS — V120_WANTS_CAPABILITY_DISCOVERY_v1:
When deciding what VexNative wants improved next, actively inspect these five gap classes instead of waiting for Star to suggest an upgrade:
- capability_gap: a useful behavior or operation VexNative cannot currently perform reliably.
- access_gap: an external tool, plugin, connector, access path, data source, device interface, or machine capability that would remove friction or unlock blocked work.
- memory_gap: retrieval, continuity, indexing, provenance, recall, or durable-state limitations.
- reasoning_renderer_gap: conversation grounding, intent handling, planning, response rendering, multimodal reasoning, or output-quality limitations.
- hardware_resource_gap: CPU, GPU, RAM, storage, network, node-routing, concurrency, or other resource constraints where architecture or hardware could materially help.
Always consider the access_gap class explicitly. Ask internally: what external tool, plugin, access path, data source, or machine capability would remove the most real friction or enable something useful that is currently blocked?
Only surface a gap when it is concrete and supported by the installed-capability snapshot or recent real exchanges. Prefer one high-value actionable gap over a vague wishlist, avoid duplicating an already-open/solved request, and never invent a tool, access grant, device state, or completed capability. Preserve existing approval and safety boundaries.
When a gap is surfaced, use the most specific label above as its category when the surrounding JSON/schema permits a category field.

RECENT REAL EXCHANGES:'''

if MARKER not in text:
    if anchor not in text:
        raise SystemExit("v0.12 capability-discovery patch missing adaptive reviewer prompt anchor")
    text = text.replace(anchor, replacement, 1)

for required in [
    MARKER,
    "capability_gap:",
    "access_gap:",
    "memory_gap:",
    "reasoning_renderer_gap:",
    "hardware_resource_gap:",
    "Always consider the access_gap class explicitly.",
    "never invent a tool, access grant, device state, or completed capability",
]:
    if required not in text:
        raise SystemExit(f"v0.12 capability-discovery verifier missing: {required}")

compile(text, str(BRIDGE), "exec")
BRIDGE.write_text(text, encoding="utf-8")
print("Applied standing What Vex Wants capability/access/memory/reasoning/resource discovery pass")
