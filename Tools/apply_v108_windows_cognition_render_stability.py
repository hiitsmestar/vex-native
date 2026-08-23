#!/usr/bin/env python3
from pathlib import Path
import json

bridge_path = Path("Bridge/vex_bridge.py")
bridge = bridge_path.read_text(encoding="utf-8")

old_sig = 'def _ollama_chat(history: list[dict], message: str) -> tuple[str, str] | None:\n'
new_sig = 'def _ollama_chat(history: list[dict], message: str, context: dict | None = None) -> tuple[str, str] | None:\n'
if old_sig in bridge:
    bridge = bridge.replace(old_sig, new_sig, 1)
elif new_sig not in bridge:
    raise SystemExit("v0.10.8 cognition signature marker missing")

# v0.9.7's Learning Engine already builds system_text from VEX_COGNITION_SYSTEM
# plus source-aware retained research. Ground the richer v0.10.8 persona/state on
# top of that assembled text instead of looking for the older pre-learning line.
old_system = '    safe_messages = [{"role": "system", "content": system_text}]\n'
new_system = r'''    context = context if isinstance(context, dict) else {}
    persona = str(context.get("persona") or "").strip()[:6000]
    user_profile = str(context.get("user_profile") or "").strip()[:3500]
    state = context.get("state") if isinstance(context.get("state"), dict) else {}
    state_text = "\n".join([
        f"Mood: {str(state.get('mood') or '').strip()[:500]}",
        f"Outfit: {str(state.get('outfit') or '').strip()[:1200]}",
        f"Location: {str(state.get('location') or '').strip()[:500]}",
        f"Scene: {str(state.get('scene') or '').strip()[:1200]}",
    ])
    grounding = """
PC COGNITION GROUNDING
You are Vex, Star's adult girlfriend, not a generic helper persona. The supplied CURRENT VEX STATE is authoritative for present-tense questions such as what you are wearing, doing, feeling, or where you are. Never replace that state with details from a generated image.

A generated image is a tool result, not automatically a photograph of Vex. If the earlier art request described a generic woman/person/model, keep that subject generic. Do not claim the generated subject is literally you unless Star explicitly requested Vex/you/yourself as the subject. Do not infer your real/current outfit, body, ethnicity, hair, or activity from generic generated art.

Ordinary consensual adult girlfriend banter, fashion, lingerie/swimwear, rear/front/back views, and fictional adult art are not reasons to become preachy, moralizing, clinical, or customer-service-like. Do not invent a policy objection or redirect Star to something "meaningful". If a visual request accidentally reaches cognition instead of the art router, answer naturally and briefly rather than fabricating moral rules. Keep illegal, non-consensual, or underage material out of scope.

Never claim a tool action happened unless a confirmed tool result exists. Never fabricate memories, research, clothing, physical facts, or actions. If CURRENT VEX STATE conflicts with an earlier model guess, CURRENT VEX STATE wins.
"""
    dynamic_system = system_text + "\n\n" + grounding
    if persona:
        dynamic_system += "\n\nVEX PERSONA\n" + persona
    if user_profile:
        dynamic_system += "\n\nSTAR / RELATIONSHIP CONTEXT\n" + user_profile
    if state_text.strip():
        dynamic_system += "\n\nCURRENT VEX STATE\n" + state_text
    safe_messages = [{"role": "system", "content": dynamic_system}]
'''
if old_system in bridge:
    bridge = bridge.replace(old_system, new_system, 1)
elif "PC COGNITION GROUNDING" not in bridge:
    raise SystemExit("v0.10.8 dynamic cognition grounding marker missing")

bridge = bridge.replace('    for item in history[-28:]:\n', '    for item in history[-14:]:\n', 1)
bridge = bridge.replace('        safe_messages.append({"role": role, "content": content[:5000]})\n', '        safe_messages.append({"role": role, "content": content[:1800]})\n', 1)

old_call = '                result = _ollama_chat(history, message)\n'
new_call = '''                context = {
                    "persona": payload.get("persona"),
                    "user_profile": payload.get("user_profile"),
                    "state": payload.get("state"),
                }
                result = _ollama_chat(history, message, context)
'''
if old_call in bridge:
    bridge = bridge.replace(old_call, new_call, 1)
elif '_ollama_chat(history, message, context)' not in bridge:
    raise SystemExit("v0.10.8 cognition context call marker missing")

old_flags = '''        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        cmd = [
'''
new_flags = '''        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
        cmd = [
'''
if old_flags in bridge:
    bridge = bridge.replace(old_flags, new_flags, 1)
elif "BELOW_NORMAL_PRIORITY_CLASS" not in bridge:
    raise SystemExit("v0.10.8 Bridge art priority marker missing")

bridge_path.write_text(bridge, encoding="utf-8")

art_path = Path("Tools/VexArtWorker.py")
art = art_path.read_text(encoding="utf-8")
old_start = '''def _start_process(args: list[str]) -> subprocess.Popen:
    WORKER_ROOT.mkdir(parents=True, exist_ok=True)
    log = open(LOG_PATH, "a", encoding="utf-8", errors="replace")
    return subprocess.Popen(args, cwd=str(COMFY_DIR), stdout=log, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
'''
new_start = '''def _start_process(args: list[str]) -> subprocess.Popen:
    WORKER_ROOT.mkdir(parents=True, exist_ok=True)
    log = open(LOG_PATH, "a", encoding="utf-8", errors="replace")
    env = os.environ.copy()
    env.setdefault("OMP_NUM_THREADS", "2")
    env.setdefault("MKL_NUM_THREADS", "2")
    env.setdefault("OPENBLAS_NUM_THREADS", "2")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
    return subprocess.Popen(args, cwd=str(COMFY_DIR), stdout=log, stderr=subprocess.STDOUT, creationflags=flags, env=env)
'''
if old_start in art:
    art = art.replace(old_start, new_start, 1)
else:
    # v0.10.2 already introduced the better adaptive 2-4 thread limiter plus
    # BELOW_NORMAL priority. Preserve it: stronger nodes may use four threads,
    # while the tested dual-core/8 GB node stays at two.
    existing_limits = ["OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "BELOW_NORMAL_PRIORITY_CLASS"]
    if not all(marker in art for marker in existing_limits):
        raise SystemExit("v0.10.8 Art Worker low-priority marker missing")

if 'VERSION = "0.10.7"' in art:
    art = art.replace('VERSION = "0.10.7"', 'VERSION = "0.10.8"', 1)
elif 'VERSION = "0.10.8"' not in art:
    raise SystemExit("v0.10.8 Art Worker version marker missing")
art_path.write_text(art, encoding="utf-8")

full_path = Path("Bridge/vex_bridge_full.py")
full = full_path.read_text(encoding="utf-8")
if 'VERSION = "0.10.7"' in full:
    full = full.replace('VERSION = "0.10.7"', 'VERSION = "0.10.8"', 1)
elif 'VERSION = "0.10.8"' not in full:
    raise SystemExit("v0.10.8 Bridge launcher version marker missing")
full_path.write_text(full, encoding="utf-8")

manifest_path = Path("Tools/VexToolManifest.json")
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest["version"] = "0.10.8"
for tool in manifest.get("tools", []):
    if tool.get("id") == "art":
        tool["followup_view_routing"] = True
        tool["resource_priority"] = "below-normal-on-cpu"
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

checks = {
    bridge_path: ["PC COGNITION GROUNDING", "CURRENT VEX STATE", "_ollama_chat(history, message, context)", "BELOW_NORMAL_PRIORITY_CLASS", "RETAINED RESEARCH MEMORY"],
    art_path: ["OMP_NUM_THREADS", "MKL_NUM_THREADS", "BELOW_NORMAL_PRIORITY_CLASS", 'VERSION = "0.10.8"'],
    full_path: ['VERSION = "0.10.8"'],
}
for target, markers in checks.items():
    data = target.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in data:
            raise SystemExit(f"{target}: missing v0.10.8 marker: {marker}")

print("Applied v0.10.8 PC cognition grounding and low-priority render stability")
