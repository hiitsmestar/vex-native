#!/usr/bin/env python3
from pathlib import Path

path = Path("VexNative/ContentView.swift")
text = path.read_text(encoding="utf-8")

marker = "// MARK: - Optional PC cognition overlay v0.9.3\n"
idx = text.find(marker)
if idx < 0:
    raise SystemExit("PCCognitionOverlay marker not found")

# Add a Sendable winner type beside the existing decoded reply.
old_reply = '''    private struct OverlayReply: Decodable {\n        let ok: Bool\n        let reply: String?\n        let model: String?\n    }\n'''
new_reply = '''    private struct OverlayReply: Decodable {\n        let ok: Bool\n        let reply: String?\n        let model: String?\n    }\n\n    private struct CognitionAttempt: Sendable {\n        let endpoint: String\n        let reply: String\n        let model: String?\n    }\n'''
if old_reply not in text[idx:]:
    raise SystemExit("OverlayReply block not found")
text = text.replace(old_reply, new_reply, 1)

# v0.9.4.2 made the routing visible but still tried nodes serially. On a two-PC
# setup, one CPU-slow node can consume almost the entire request window before the
# healthy node is attempted. Race all configured nodes and accept the first valid
# cognition answer instead.
loop_start = text.find("        for endpoint in endpoints {\n", idx)
if loop_start < 0:
    raise SystemExit("sequential cognition loop not found")
loop_end_marker = "        // Let the remaining native/web fallback routes handle the turn."
loop_end = text.find(loop_end_marker, loop_start)
if loop_end < 0:
    raise SystemExit("cognition fallback marker not found")

replacement = '''        // v0.9.4.3: dual-node race. Both paired PC brains are independent, so a\n        // slow/down node must never block a healthy node behind it. The first valid\n        // reply wins; the remaining request is cancelled.\n        let winner: CognitionAttempt? = await withTaskGroup(of: CognitionAttempt?.self) { group in\n            for endpoint in endpoints {\n                group.addTask {\n                    await requestReply(endpoint: endpoint, original: original, history: history)\n                }\n            }\n\n            while let candidate = await group.next() {\n                if let candidate {\n                    group.cancelAll()\n                    return candidate\n                }\n            }\n            return nil\n        }\n\n        if let winner {\n            app.profile.messages.append(ChatMessage(role: .user, content: original))\n            app.profile.messages.append(ChatMessage(role: .assistant, content: winner.reply))\n            app.persist()\n            app.pcBrainConnected = true\n            UserDefaults.standard.set(winner.endpoint, forKey: "vex.pc.cognition.lastGoodEndpoint.v1")\n            if let model = winner.model, !model.isEmpty {\n                app.pcBrainStatus = "PC cognition • \\(model)"\n            } else {\n                app.pcBrainStatus = "PC cognition • connected"\n            }\n            return true\n        }\n\n'''
text = text[:loop_start] + replacement + text[loop_end:]

# Insert the actual network worker before bridgeAlive. It is nonisolated so child
# tasks can execute concurrently instead of inheriting the MainActor.
insert_marker = "    private static func bridgeAlive(_ endpoint: String) async -> Bool {\n"
insert_at = text.find(insert_marker, idx)
if insert_at < 0:
    raise SystemExit("bridgeAlive helper not found")
worker = '''    nonisolated private static func requestReply(\n        endpoint: String,\n        original: String,\n        history: [[String: String]]\n    ) async -> CognitionAttempt? {\n        guard let root = URL(string: endpoint),\n              var parts = URLComponents(url: root, resolvingAgainstBaseURL: false)\n        else { return nil }\n        parts.path = "/llm/chat"\n        guard let url = parts.url else { return nil }\n\n        var request = URLRequest(url: url)\n        request.httpMethod = "POST"\n        request.timeoutInterval = 90\n        request.setValue("application/json", forHTTPHeaderField: "Content-Type")\n        let body: [String: Any] = [\n            "message": String(original.prefix(5000)),\n            "history": history\n        ]\n        request.httpBody = try? JSONSerialization.data(withJSONObject: body)\n\n        do {\n            let (data, response) = try await VexBridgeNetworking.data(for: request)\n            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode),\n                  let decoded = try? JSONDecoder().decode(OverlayReply.self, from: data),\n                  decoded.ok,\n                  let reply = decoded.reply?.trimmingCharacters(in: .whitespacesAndNewlines),\n                  !reply.isEmpty\n            else { return nil }\n            return CognitionAttempt(endpoint: endpoint, reply: reply, model: decoded.model)\n        } catch {\n            return nil\n        }\n    }\n\n'''
text = text[:insert_at] + worker + text[insert_at:]

# Prefer the last cognition winner when constructing the list. The race makes this
# optional for correctness, but it improves single-node warm-cache behavior.
old_values = '''        let last = defaults.string(forKey: "vex.pc.smartBrowser.lastEndpoint.v1") ?? ""\n        var values: [String] = []\n        for endpoint in [last, primary, secondary] where !endpoint.isEmpty {\n'''
new_values = '''        let lastCognition = defaults.string(forKey: "vex.pc.cognition.lastGoodEndpoint.v1") ?? ""\n        let last = defaults.string(forKey: "vex.pc.smartBrowser.lastEndpoint.v1") ?? ""\n        var values: [String] = []\n        for endpoint in [lastCognition, last, primary, secondary] where !endpoint.isEmpty {\n'''
if old_values not in text[idx:]:
    raise SystemExit("configuredEndpoints ordering block not found")
text = text.replace(old_values, new_values, 1)

path.write_text(text, encoding="utf-8")

checks = [
    "v0.9.4.3: dual-node race",
    "withTaskGroup(of: CognitionAttempt?.self)",
    "requestReply(endpoint: endpoint",
    "vex.pc.cognition.lastGoodEndpoint.v1",
    "nonisolated private static func requestReply",
]
for check in checks:
    if check not in text:
        raise SystemExit(f"missing v0.9.4.3 marker: {check}")

print("Applied v0.9.4.3 concurrent dual-PC cognition race/failover hotfix")
