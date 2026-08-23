#!/usr/bin/env python3
from pathlib import Path

path = Path("VexNative/ContentView.swift")
text = path.read_text(encoding="utf-8")

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
if old_direct in text:
    text = text.replace(old_direct, new_direct, 1)
elif "lets see the back view" not in text:
    raise SystemExit("v0.10.8 direct visual routing marker missing")

old_submit = '''            guard let submitted = await submit(prompt: original, orientation: orientation, endpoint: endpoint) else {
'''
new_submit = '''            let renderPrompt = contextualPrompt(original, app: app)
            guard let submitted = await submit(prompt: renderPrompt, orientation: orientation, endpoint: endpoint) else {
'''
if old_submit in text:
    text = text.replace(old_submit, new_submit, 1)
elif "contextualPrompt(original, app: app)" not in text:
    raise SystemExit("v0.10.8 contextual prompt call marker missing")

marker = '''    private static func requestedOrientation(_ lower: String) -> String {
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
            return isArtRequest(normalize(message.content))
        })?.content.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let priorArt, !priorArt.isEmpty, priorArt != original else {
            return String(original.prefix(7000))
        }
        return String((priorArt + ". Follow-up view instruction: " + original).prefix(7000))
    }

'''
if marker in text and "private static func contextualPrompt" not in text:
    text = text.replace(marker, helper + marker, 1)
elif "private static func contextualPrompt" not in text:
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
if old_body in text:
    text = text.replace(old_body, new_body, 1)
elif '"persona": String(app.profile.persona.prefix(6000))' not in text:
    raise SystemExit("v0.10.8 cognition context body marker missing")

old_exclusion = '''            "picture", " image", "camera", "open youtube", "open google", "open browser",
'''
new_exclusion = '''            "picture", " image", "camera", "back view", "rear view", "front view", "side view",
            "from behind", "turn around", "open youtube", "open google", "open browser",
'''
if old_exclusion in text:
    text = text.replace(old_exclusion, new_exclusion, 1)
elif '"back view", "rear view", "front view"' not in text:
    raise SystemExit("v0.10.8 cognition art exclusion marker missing")

path.write_text(text, encoding="utf-8")

for required in [
    "contextualPrompt(original, app: app)", "lets see the back view",
    '"persona": String(app.profile.persona.prefix(6000))', '"state": stateContext',
    '"back view", "rear view", "front view"',
]:
    if required not in text:
        raise SystemExit(f"missing v0.10.8 iOS marker: {required}")

print("Applied v0.10.8 iOS art follow-up routing and PC cognition context")
