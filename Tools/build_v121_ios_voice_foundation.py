#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCRIPTS = [
    "Tools/apply_v074_bridge_pairing_patch.py",
    "Tools/apply_v075_search_routing_patch.py",
    "Tools/apply_v076_direct_research_answers_patch.py",
    "Tools/apply_v077_grounded_research_patch.py",
    "Tools/apply_v078_photo_context_patch.py",
    "Tools/apply_v079_camera_visual_replies_patch.py",
    "Tools/apply_v079_compile_hotfix.py",
    "Tools/apply_v0710_visual_intent_fix.py",
    "Tools/apply_v0711_zoomable_chat_images.py",
    "Tools/prepare_v082_build_chain.py",
    "Tools/apply_v080_hybrid_brain_patch.py",
    "Tools/apply_v081_dual_pc_mesh_patch.py",
    "Tools/apply_v082_pc_tools_capability_patch.py",
    "Tools/apply_v083_browser_url_tools_patch.py",
    "Tools/apply_v084_self_learning_skills_patch.py",
    "Tools/apply_v084_skill_resolution_order_hotfix.py",
    "Tools/apply_v085_skill_compiler_patch.py",
    "Tools/apply_v086_voice_ui_patch.py",
    "Tools/apply_v087_voice_crash_hotfix.py",
    "Tools/apply_v088_voice_transcript_patch.py",
    "Tools/apply_v089_voice_conversation_patch.py",
    "Tools/apply_v090_neural_voice_ios_patch.py",
    "Tools/apply_v090_named_media_ios_patch.py",
    "Tools/apply_v091_youtube_context_ios_patch.py",
]

TAIL_BEFORE_MAINTENANCE = [
    "Tools/apply_v093_cognition_ios_patch.py",
    "Tools/apply_v094_art_ios_patch.py",
    "Tools/apply_v0941_startup_safe_mode_patch.py",
    "Tools/apply_v0942_send_reliability_patch.py",
    "Tools/apply_v0943_dual_node_race_patch.py",
    "Tools/apply_v0944_bridge_long_request_timeout_patch.py",
    "Tools/apply_v095_resource_housekeeper_ios_patch.py",
]

TAIL_AFTER_MAINTENANCE = [
    "Tools/apply_v098_ios_time_grounding_patch.py",
    "Tools/apply_v107_art_ios_adapter_patch.py",
    "Tools/apply_v108_ios_art_followup_grounding.py",
    "Tools/apply_v110_ios_memory_sync.py",
    "Tools/apply_v111_ios_memory_sync_hotfix.py",
]


def run(path: str, allow_failure: bool = False) -> None:
    print(f"==> {path}", flush=True)
    result = subprocess.run([sys.executable, path], cwd=ROOT)
    if result.returncode != 0 and not allow_failure:
        raise SystemExit(result.returncode)


for script in SCRIPTS:
    run(script)

run("Tools/apply_v092_device_control_patch.py", allow_failure=True)
content = (ROOT / "VexNative" / "ContentView.swift").read_text(encoding="utf-8")
if "PhoneToolRouter" not in content:
    raise SystemExit("device-control chain did not produce PhoneToolRouter")

for script in TAIL_BEFORE_MAINTENANCE:
    run(script)
run("Tools/apply_v096_active_maintenance_ios_patch.py", allow_failure=True)
for script in TAIL_AFTER_MAINTENANCE:
    run(script)

# Keep one bounded diagnostic around the historical natural-continuity fast path.
# This is intentionally source code only (no user data) and makes future cumulative
# chain drift diagnosable from CI rather than guessing at the generated shape.
app_debug = (ROOT / "VexNative" / "AppModel.swift").read_text(encoding="utf-8")
fast = app_debug.find("if isQwen3, let grounded = nativeGroundedQwen3Reply(for: text) {")
if fast >= 0:
    print("--- generated AppModel continuity anchor ---", flush=True)
    print(app_debug[max(0, fast - 240):fast + 1900], flush=True)
    print("--- end continuity anchor ---", flush=True)

run("Tools/apply_v11729_ios_natural_continuity.py")
run("Tools/apply_v121_voice_foundation_ios.py")

content = (ROOT / "VexNative" / "ContentView.swift").read_text(encoding="utf-8")
for marker in [
    'V121_VOICE_FOUNDATION_IOS = "v0.12.1-swap-ready-voice-v1"',
    "case automatic",
    'return "Bridge Voice"',
    '"provider": speechEngine == .automatic ? "auto" : "edge-neural"',
    "func interruptSpeechAndListen()",
    "VexVoiceSettingsView",
]:
    if marker not in content:
        raise SystemExit(f"final iOS voice marker missing: {marker}")

print("PASS v0.12.1 iOS voice foundation source chain")
