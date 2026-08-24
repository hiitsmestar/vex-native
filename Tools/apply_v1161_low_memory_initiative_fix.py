#!/usr/bin/env python3
from pathlib import Path

path = Path("Bridge/vex_bridge.py")
text = path.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global text
    if old not in text:
        raise SystemExit(f"v0.11.6.1 {label}: expected source block not found")
    text = text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# v0.11.6.1 Low-memory autonomy coordination
#
# The tested primary PC is intentionally small. v0.11.4-v0.11.6 originally used
# conservative 1.4-1.6 GB free-RAM cutoffs that could defer every background
# learning/autonomy/initiative cycle forever on an otherwise healthy 8 GB node.
#
# New behavior:
# - only severe memory pressure stops background work entirely;
# - capability probes and skill validation continue in low-memory mode;
# - initiative falls back to deterministic, non-LLM internal choices when there
#   is not enough headroom for another planner inference;
# - model-backed upgrade synthesis waits for better headroom;
# - normal foreground work and Art Worker still win immediately.
# ---------------------------------------------------------------------------

marker = '_INITIATIVE_LAST_DECISION = 0.0\n'
if marker not in text:
    raise SystemExit("v0.11.6.1 initiative constants marker missing")
text = text.replace(
    marker,
    marker + '''\nIDLE_AUTONOMY_HARD_FLOOR_BYTES = 640 * 1024 * 1024\nIDLE_AUTONOMY_PLANNER_FLOOR_BYTES = 1150 * 1024 * 1024\n''',
    1,
)

# Adaptive review still needs local model inference, but 1.4 GB was too strict for
# the field PC. Let it try unless the machine is genuinely starved; failures still
# defer safely and retry later through the existing loop.
replace_once(
    '''        available = int(snap.get("memory_available") or 0)\n        if available and available < 1400 * 1024 * 1024 and not force:\n            return {"ok": True, "idle": True, "detail": "memory pressure; adaptive review deferred"}\n''',
    '''        available = int(snap.get("memory_available") or 0)\n        if available and available < IDLE_AUTONOMY_HARD_FLOOR_BYTES and not force:\n            return {"ok": True, "idle": True, "detail": "severe memory pressure; adaptive review deferred"}\n''',
    "adaptive memory floor",
)

# Capability probes and learned-skill rehearsal are useful even when RAM is tight.
# Keep those running. Only the model-backed upgrade-candidate synthesis is deferred
# below the planner floor.
replace_once(
    '''        available = int(snap.get("memory_available") or 0)\n        if available and available < 1500 * 1024 * 1024 and not force:\n            return {"ok": True, "idle": True, "detail": "memory pressure; autonomy deferred"}\n    except Exception:\n        pass\n\n    result = {"ok": True, "feature": None, "skills": None, "upgrade": None}\n''',
    '''        available = int(snap.get("memory_available") or 0)\n        if available and available < IDLE_AUTONOMY_HARD_FLOOR_BYTES and not force:\n            return {"ok": True, "idle": True, "detail": "severe memory pressure; autonomy deferred"}\n    except Exception:\n        available = 0\n\n    low_memory = bool(available and available < IDLE_AUTONOMY_PLANNER_FLOOR_BYTES)\n    result = {"ok": True, "feature": None, "skills": None, "upgrade": None, "low_memory": low_memory}\n''',
    "autonomy low-memory mode",
)

replace_once(
    '''    if force or now - _AUTONOMY_LAST_UPGRADE >= AUTONOMY_UPGRADE_INTERVAL:\n        _AUTONOMY_LAST_UPGRADE = now\n        result["upgrade"] = _autonomy_stage_upgrade_candidate()\n''',
    '''    if force or now - _AUTONOMY_LAST_UPGRADE >= AUTONOMY_UPGRADE_INTERVAL:\n        _AUTONOMY_LAST_UPGRADE = now\n        if low_memory and not force:\n            result["upgrade"] = {"ok": True, "detail": "low-memory mode; model-backed upgrade synthesis deferred"}\n        else:\n            result["upgrade"] = _autonomy_stage_upgrade_candidate()\n''',
    "autonomy upgrade gating",
)

# Initiative must not become "do nothing forever" just because the PC lives near
# the RAM ceiling. Under moderate pressure choose a useful deterministic internal
# action that does not require another local-model planning pass.
replace_once(
    '''        available = int(rs.get("memory_available") or 0)\n        if available and available < 1600 * 1024 * 1024 and not force:\n            return {"ok": True, "idle": True, "detail": "memory pressure; initiative deferred"}\n    except Exception:\n        pass\n\n    _INITIATIVE_LAST_DECISION = now\n    snapshot = _initiative_self_snapshot()\n    _initiative_store_self_state(snapshot)\n    decision = _initiative_choose_action(snapshot)\n''',
    '''        available = int(rs.get("memory_available") or 0)\n        if available and available < IDLE_AUTONOMY_HARD_FLOOR_BYTES and not force:\n            return {"ok": True, "idle": True, "detail": "severe memory pressure; initiative deferred"}\n    except Exception:\n        available = 0\n\n    _INITIATIVE_LAST_DECISION = now\n    snapshot = _initiative_self_snapshot()\n    _initiative_store_self_state(snapshot)\n    low_memory = bool(available and available < IDLE_AUTONOMY_PLANNER_FLOOR_BYTES)\n    if low_memory and not force:\n        gaps = snapshot.get("open_gaps") if isinstance(snapshot, dict) else []\n        if gaps:\n            decision = {\n                "action": "research_open_gap",\n                "goal_key": "self_improvement",\n                "reason": "low-memory deterministic initiative: research an existing sanitized technical gap without another planner inference",\n                "confidence": 0.92,\n            }\n        else:\n            decision = {\n                "action": "probe_capability",\n                "goal_key": "capability_mastery",\n                "reason": "low-memory deterministic initiative: inspect one installed capability and advance the feature curriculum",\n                "confidence": 0.94,\n            }\n    else:\n        decision = _initiative_choose_action(snapshot)\n''',
    "initiative low-memory deterministic fallback",
)

# Expose the scheduling mode in status/self-model so future diagnostics can tell
# whether the planner is operating normally or in the lightweight path.
replace_once(
    '''    snapshot["recent_events"] = _initiative_recent_events(10)\n    snapshot["idle_seconds"] = INITIATIVE_IDLE_SECONDS\n    snapshot["decision_interval"] = INITIATIVE_DECISION_INTERVAL\n''',
    '''    snapshot["recent_events"] = _initiative_recent_events(10)\n    snapshot["idle_seconds"] = INITIATIVE_IDLE_SECONDS\n    snapshot["decision_interval"] = INITIATIVE_DECISION_INTERVAL\n    available = int((snapshot.get("resources") or {}).get("memory_available") or 0)\n    snapshot["scheduler_mode"] = "low-memory" if available and available < IDLE_AUTONOMY_PLANNER_FLOOR_BYTES else "normal"\n    snapshot["hard_floor_bytes"] = IDLE_AUTONOMY_HARD_FLOOR_BYTES\n    snapshot["planner_floor_bytes"] = IDLE_AUTONOMY_PLANNER_FLOOR_BYTES\n''',
    "initiative status scheduler mode",
)

for stale in ['"version": "0.11.6.0"']:
    text = text.replace(stale, '"version": "0.11.6.1"')

path.write_text(text, encoding="utf-8")
compile(text, str(path), "exec")

final = path.read_text(encoding="utf-8")
checks = [
    '"version": "0.11.6.1"',
    "IDLE_AUTONOMY_HARD_FLOOR_BYTES",
    "IDLE_AUTONOMY_PLANNER_FLOOR_BYTES",
    "low-memory deterministic initiative",
    'snapshot["scheduler_mode"]',
    '"low_memory": low_memory',
    "model-backed upgrade synthesis deferred",
]
for item in checks:
    if item not in final:
        raise SystemExit(f"v0.11.6.1 verifier missing: {item}")

print("Applied v0.11.6.1 low-memory autonomous initiative scheduling")
