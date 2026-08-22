#!/usr/bin/env python3
from pathlib import Path

path = Path("VexNative/ContentView.swift")
text = path.read_text(encoding="utf-8")

old_start = '''    static func tryHandle(_ original: String, app: AppModel) async -> Bool {\n        guard shouldUse(original) else { return false }\n        let endpoints = configuredEndpoints()\n        guard !endpoints.isEmpty else { return false }\n\n        let history = app.profile.messages.suffix(28).map { message -> [String: String] in\n'''
new_start = '''    static func tryHandle(_ original: String, app: AppModel) async -> Bool {\n        guard shouldUse(original) else { return false }\n        let endpoints = configuredEndpoints()\n        guard !endpoints.isEmpty else { return false }\n\n        // v0.9.4.2: acknowledge the send immediately. Previously the composer\n        // appeared dead while /llm/chat waited up to 45 seconds because the draft\n        // stayed on screen and isGenerating was not set until AFTER a reply arrived.\n        app.draft = ""\n        app.isGenerating = true\n        app.pcBrainStatus = "PC cognition • thinking…"\n        defer { app.isGenerating = false }\n\n        let history = app.profile.messages.suffix(28).map { message -> [String: String] in\n'''
if old_start not in text:
    raise SystemExit("cognition start block not found")
text = text.replace(old_start, new_start, 1)

old_loop = '''        for endpoint in endpoints {\n            guard let url = endpointURL(endpoint, path: "/llm/chat") else { continue }\n            var request = URLRequest(url: url)\n            request.httpMethod = "POST"\n            request.timeoutInterval = 45\n'''
new_loop = '''        for endpoint in endpoints {\n            // Dead/stale paired endpoints should fail over in a few seconds rather\n            // than making the send button look broken for a full model timeout.\n            guard await bridgeAlive(endpoint) else { continue }\n            guard let url = endpointURL(endpoint, path: "/llm/chat") else { continue }\n            var request = URLRequest(url: url)\n            request.httpMethod = "POST"\n            // CPU inference on the new 4B brain can legitimately take a while.\n            // The UI is already visibly busy, so give a live node enough time.\n            request.timeoutInterval = 90\n'''
if old_loop not in text:
    raise SystemExit("cognition request loop block not found")
text = text.replace(old_loop, new_loop, 1)

old_success = '''                app.draft = ""\n                app.isGenerating = true\n                defer { app.isGenerating = false }\n                app.profile.messages.append(ChatMessage(role: .user, content: original))\n'''
new_success = '''                app.profile.messages.append(ChatMessage(role: .user, content: original))\n'''
if old_success not in text:
    raise SystemExit("late cognition busy-state block not found")
text = text.replace(old_success, new_success, 1)

old_return = '''        }\n        return false\n    }\n\n    private static func shouldUse(_ text: String) -> Bool {\n'''
new_return = '''        }\n\n        // Let the remaining native/web fallback routes handle the turn. They expect\n        // the original text to still be in draft, so restore it only on total PC\n        // cognition failure.\n        app.draft = original\n        app.pcBrainConnected = false\n        app.pcBrainStatus = "PC cognition unavailable • falling back"\n        return false\n    }\n\n    private static func bridgeAlive(_ endpoint: String) async -> Bool {\n        guard let url = endpointURL(endpoint, path: "/status") else { return false }\n        var request = URLRequest(url: url)\n        request.timeoutInterval = 3.5\n        do {\n            let (_, response) = try await VexBridgeNetworking.data(for: request)\n            guard let http = response as? HTTPURLResponse else { return false }\n            return (200...299).contains(http.statusCode)\n        } catch {\n            return false\n        }\n    }\n\n    private static func shouldUse(_ text: String) -> Bool {\n'''
if old_return not in text:
    raise SystemExit("cognition fallback return block not found")
text = text.replace(old_return, new_return, 1)

# Make the composer visually explicit while a turn is routing/generating. This is
# deliberately cosmetic; the important state transition is in PCCognitionOverlay.
old_progress = '''                                    Text(web.isWorking ? "web brain is looking…" : "three neurons are thinking…")\n'''
new_progress = '''                                    Text(web.isWorking ? "web brain is looking…" : (app.pcBrainConnected ? "PC brain is thinking…" : "Vex is thinking…"))\n'''
if old_progress in text:
    text = text.replace(old_progress, new_progress, 1)

path.write_text(text, encoding="utf-8")

for marker in [
    "v0.9.4.2: acknowledge the send immediately",
    "bridgeAlive(endpoint)",
    'request.timeoutInterval = 90',
    'app.draft = original',
    'PC cognition • thinking…',
]:
    if marker not in text:
        raise SystemExit(f"missing v0.9.4.2 marker: {marker}")

print("Applied v0.9.4.2 immediate-send feedback + cognition failover hotfix")
