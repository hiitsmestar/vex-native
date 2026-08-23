#!/usr/bin/env python3
from pathlib import Path
import json


def once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"{label}: source block not found")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# iPhone: route natural follow-up views directly to Art Worker, carry the prior
# visual request for continuity, and give PC cognition authoritative Vex state.
# ---------------------------------------------------------------------------
ios_path = Path("VexNative/ContentView.swift")
ios = ios_path.read_text(encoding="utf-8")

old_direct = '''        let directVisualRequests = [
            "show me a picture", "show me a pic", "show me a photo", "show me an image",
            "send me a picture", "send me a pic", "send me a photo", "send me an image"
        ]
        if directVisualRequests.contains(where: { lower.contains($0) }) { return true }
        return createWords.contains(where: { lower.contains($0) }) &&
            imageWords.contains(where: { lower.contains($0) })
'''
new_direct = '''        let directVisualRequests = [
            "show me a picture", "show me a pic", "show me a photo", "show me an image",
            "send me a picture", "send me a pic", "send me a photo", "send me an image",
            "show me the back view", "show me a back view", "show me the rear view", "show me a rear view",
            "show me the front view", "show me a front view", "lets see the back view", "let's see the back view",
            "lets see the rear view", "let's see the rear view", "lets see the front view", "let's see the front view"
        ]
        if directVisualRequests.contains(where: { lower.contains($0) }) { return true }
        let viewWords = ["back view", "rear view", "front view", "side view", "rear-view", "back-view"]
        if createWords.contains(where: { lower.contains($0) }) && viewWords.contains(where: { lower.contains($0) }) {
            return true
        }
        return createWords.contains(where: { lower.contains($0) }) &&
            imageWords.contains(where: { lower.contains($0) })
'''
if old_direct in ios:
    ios = ios.replace(old_direct, new_direct, 1)
elif "lets see the back view" not in ios:
    raise SystemExit("v0.10.8 direct visual routing marker missing")

old_submit_call = '''            guard let submitted = await submit(prompt: original, orientation: orientation, endpoint: endpoint) else {
'''
new_submit_call = '''            let renderPrompt = contextualPrompt(original, app: app)
            guard let submitted = await submit(prompt: renderPrompt, orientation: orientation, endpoint: endpoint) else {
'''
if old_submit_call in ios:
    ios = ios.replace(old_submit_call, new_submit_call, 1)
elif "contextualPrompt(original, app: app)" not in ios:
    raise SystemExit("v0.10.8 contextual art prompt call marker missing")

insert_before = '''    private static func requestedOrientation(_ lower: String) -> String {
'''
helper = r'''    private static func contextualPrompt(_ original: String, app: AppModel) -> String {
        let lower = normalize(original)
        let followupTokens = [
            "back view", "rear view", "front view", "side view", "same outfit", "that outfit",
            "same clothes", "that look", "same girl", "same woman", "from behind", "turn around"
        ]
        guard followupTokens.contains(where: { lower.contains($0) }) else {
            return String(original.prefix(7000))
        }

        let priorArt = app.profile.messages.reversed().first(where: { message in
            guard message.role == .user else { return false }
            let candidate = normalize(message.content)
            return isArtRequest(candidate)
        })?.content.trimmingCharacters(in: .whitespacesAndNewlines)

        guard let priorArt, !priorArt.isEmpty, priorArt != original else {
            return String(original.prefix(7000))
        }
        return String((priorArt + ". Follow-up view instruction: " + original).prefix(7000))
    }

'''
if insert_before in ios and "private static func contextualPrompt" not in ios:
    ios = ios.replace(insert_before, helper + insert_before, 1)
elif "private static func contextualPrompt" not in ios:
    raise SystemExit("v0.10.8 contextualPrompt insertion marker missing")

old_body = '''            let body: [String: Any] = [
                "message": String(original.prefix(5000)),
                "history": history
            ]
'''
new_body = '''            let stateContext: [String: String] = [
                "mood": app.profile.state.mood,
                "outfit": app.profile.state.outfit,
                "location": app.profile.state.location,
                "scene": app.profile.state.scene
            ]
            let body: [String: Any] = [
                "message": String(original.prefix(5000)),
                "history": history,
                "persona": String(app.profile.persona.prefix(6000)),
                "user_profile": String(app.profile.userProfile.prefix(3500)),
                "state": stateContext
            ]
'''
if old_body in ios:
    ios = ios.replace(old_body, new_body, 1)
elif '"persona": String(app.profile.persona.prefix(6000))' not in ios:
    raise SystemExit("v0.10.8 cognition context body marker missing")

old_exclusion = '''            "picture", " image", "camera", "open youtube", "open google", "open browser",
'''
new_exclusion = '''            "picture", " image", "camera", "back view", "rear view", "front view", "side view",
            "from behind", "turn around", "open youtube", "open google", "open browser",
'''
if old_exclusion in ios:
    ios = ios.replace(old_exclusion, new_exclusion, 1)
elif '"back view", "rear view", "front view"' not in ios:
    raise SystemExit("v0.10.8 cognition art exclusion marker missing")

ios_path.write_text(ios, encoding="utf-8")


# ---------------------------------------------------------------------------
# Bridge PC cognition: authoritative persona/state travels with the local request.
# Generated generic art never silently becomes Vex's body/outfit/state.
# ---------------------------------------------------------------------------
bridge_path = Path("Bridge/vex_bridge.py")
bridge = bridge_path.read_text(encoding="utf-8")

old_sig = 'def _ollama_chat(history: list[dict], message: str) -> tuple[str, str] | None:\n'
new_sig = 'def _ollama_chat(history: list[dict], message: str, context: dict | None = None) -> tuple[str, str] | None:\n'
if old_sig in bridge:
    bridge = bridge.replace(old_sig, new_sig, 1)
elif new_sig not in bridge:
    raise SystemExit("v0.10.8 cognition signature marker missing")

old_system = '    safe_messages = [{"role": "system", "content": VEX_COGNITION_SYSTEM}]\n'
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
    dynamic_system = VEX_COGNITION_SYSTEM + "\n\n" + grounding
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

# ---------------------------------------------------------------------------
# Keep the old dual-core/8GB PC responsive during CPU rendering. The renderer is
# deliberately lower priority; Bridge/Remote Support/UI keep breathing.
# ---------------------------------------------------------------------------
old_bridge_flags = '''        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        cmd = [
'''
new_bridge_flags = '''        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
        cmd = [
'''
if old_bridge_flags in bridge:
    bridge = bridge.replace(old_bridge_flags, new_bridge_flags, 1)
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
    # Preserve one logical core/thread for Bridge, Remote Support and the Windows UI.
    env.setdefault("OMP_NUM_THREADS", "2")
    env.setdefault("MKL_NUM_THREADS", "2")
    env.setdefault("OPENBLAS_NUM_THREADS", "2")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
    return subprocess.Popen(args, cwd=str(COMFY_DIR), stdout=log, stderr=subprocess.STDOUT, creationflags=flags, env=env)
'''
if old_start in art:
    art = art.replace(old_start, new_start, 1)
elif 'env.setdefault("OMP_NUM_THREADS", "2")' not in art:
    raise SystemExit("v0.10.8 Art Worker low-priority marker missing")

# Bundle version labels.
art = art.replace('VERSION = "0.10.7"', 'VERSION = "0.10.8"', 1)
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

# Deterministic guarantees.
checks = {
    ios_path: [
        "contextualPrompt(original, app: app)", "lets see the back view",
        '"persona": String(app.profile.persona.prefix(6000))', '"state": stateContext',
    ],
    bridge_path: [
        "PC COGNITION GROUNDING", "CURRENT VEX STATE", "_ollama_chat(history, message, context)",
        "BELOW_NORMAL_PRIORITY_CLASS",
    ],
    art_path: ["OMP_NUM_THREADS", "BELOW_NORMAL_PRIORITY_CLASS"],
    full_path: ['VERSION = "0.10.8"'],
}
for target, markers in checks.items():
    data = target.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in data:
            raise SystemExit(f"{target}: missing v0.10.8 marker: {marker}")

print("Applied v0.10.8 art follow-up routing, PC cognition grounding, and render responsiveness fixes")
