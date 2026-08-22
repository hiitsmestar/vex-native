#!/usr/bin/env python3
from pathlib import Path

path = Path("VexNative/ContentView.swift")
text = path.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global text
    if old not in text:
        raise SystemExit(f"{label}: expected source block not found")
    text = text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# Resource Director: primary/upstairs cognition first; utility/downstairs only
# fails over when the primary cannot answer. This keeps the slower node free for
# background work instead of racing it on every chat turn.
# ---------------------------------------------------------------------------
start = text.find("        // v0.9.4.3: dual-node race.")
end_marker = "        // Let the remaining native/web fallback routes handle the turn."
end = text.find(end_marker, start)
if start < 0 or end < 0:
    raise SystemExit("v0.9.4.3 cognition race block not found")
resource_block = '''        // v0.9.5 Resource Director: the first configured Bridge is the foreground\n        // primary node. Utility nodes retain every tool permission, but they only\n        // receive interactive cognition when primary fails.\n        var winner: CognitionAttempt?\n        if let primary = endpoints.first {\n            winner = await requestReply(endpoint: primary, original: original, history: history)\n        } else {\n            winner = nil\n        }\n\n        if winner == nil {\n            for fallback in endpoints.dropFirst() {\n                if let candidate = await requestReply(endpoint: fallback, original: original, history: history) {\n                    winner = candidate\n                    break\n                }\n            }\n        }\n\n        if let winner {\n            app.profile.messages.append(ChatMessage(role: .user, content: original))\n            app.profile.messages.append(ChatMessage(role: .assistant, content: winner.reply))\n            app.persist()\n            app.pcBrainConnected = true\n            UserDefaults.standard.set(winner.endpoint, forKey: "vex.pc.cognition.lastGoodEndpoint.v1")\n            if let model = winner.model, !model.isEmpty {\n                app.pcBrainStatus = "PC cognition • \\(model)"\n            } else {\n                app.pcBrainStatus = "PC cognition • connected"\n            }\n            return true\n        }\n\n'''
text = text[:start] + resource_block + text[end:]

# Explicit primary endpoint must remain first even if a utility node happened to
# be the last node that answered in an older build.
old_order = '''        let lastCognition = defaults.string(forKey: "vex.pc.cognition.lastGoodEndpoint.v1") ?? ""\n        let last = defaults.string(forKey: "vex.pc.smartBrowser.lastEndpoint.v1") ?? ""\n        var values: [String] = []\n        for endpoint in [lastCognition, last, primary, secondary] where !endpoint.isEmpty {\n'''
new_order = '''        let lastCognition = defaults.string(forKey: "vex.pc.cognition.lastGoodEndpoint.v1") ?? ""\n        let last = defaults.string(forKey: "vex.pc.smartBrowser.lastEndpoint.v1") ?? ""\n        var values: [String] = []\n        for endpoint in [primary, lastCognition, last, secondary] where !endpoint.isEmpty {\n'''
replace_once(old_order, new_order, "cognition primary ordering")

# Interactive local art also prefers the upstairs/primary machine before any
# remembered browser endpoint or utility node.
old_art_order = '''        let last = defaults.string(forKey: "vex.pc.smartBrowser.lastEndpoint.v1") ?? ""\n        var values: [String] = []\n        for endpoint in [last, primary, secondary] where !endpoint.isEmpty {\n'''
new_art_order = '''        let last = defaults.string(forKey: "vex.pc.smartBrowser.lastEndpoint.v1") ?? ""\n        var values: [String] = []\n        for endpoint in [primary, last, secondary] where !endpoint.isEmpty {\n'''
replace_once(old_art_order, new_art_order, "art primary ordering")

# ---------------------------------------------------------------------------
# Deterministic node language: Ashley/downstairs stays fully controllable while
# Monte/upstairs is the foreground primary. Also catch natural "node" status
# questions before the language model can invent hardware state.
# ---------------------------------------------------------------------------
text = text.replace(
    '        let hasDevice = lower.contains("computer") || lower.contains(" pc") || lower.hasPrefix("pc") ||\n            lower.contains("phone") || lower.contains("bridge")\n',
    '        let hasDevice = lower.contains("computer") || lower.contains(" pc") || lower.hasPrefix("pc") ||\n            lower.contains("phone") || lower.contains("bridge") || lower.contains("node")\n',
    1,
)
text = text.replace(
    '            lower.contains("connected to both")\n',
    '            lower.contains("connected to both") || lower.contains("both nodes") ||\n            lower.contains("nodes working") || lower.contains("nodes operational") ||\n            lower.contains("node working") || lower.contains("node operational")\n',
    1,
)
text = text.replace(
    '["kitchen pc", "kitchen computer", "downstairs pc", "downstairs computer", "second pc"]',
    '["kitchen pc", "kitchen computer", "downstairs pc", "downstairs computer", "second pc", "ashley"]',
    1,
)
text = text.replace(
    '["upstairs pc", "upstairs computer", "primary pc", "main pc"]',
    '["upstairs pc", "upstairs computer", "primary pc", "main pc", "monte"]',
    1,
)

# ---------------------------------------------------------------------------
# Vex Housekeeper router. Safe clean deletes only stale temp files; old installer
# archives are quarantined with a restore manifest. Photos/video/music/documents
# and model directories are protected by the Bridge implementation.
# ---------------------------------------------------------------------------
integration = '''        if await PCBridgeToolRouter.tryHandle(original, app: self) {\n            return\n        }\n'''
if integration not in text:
    raise SystemExit("PCBridgeToolRouter integration marker missing")
text = text.replace(
    integration,
    '''        if await PCHousekeeperRouter.tryHandle(original, app: self) {\n            return\n        }\n\n''' + integration,
    1,
)

insert_marker = "// MARK: - Grounded PC Bridge tools v0.8.2\n"
if insert_marker not in text:
    raise SystemExit("PC tool router marker missing")
housekeeper = r'''// MARK: - Vex Housekeeper v0.9.5

@MainActor
private enum PCHousekeeperRouter {
    private enum Mode { case audit, clean, restore, purge }
    private enum Target { case primary, secondary, both }

    private struct AuditReply: Decodable {
        let ok: Bool
        let node_name: String?
        let safe_temp_files: Int?
        let safe_temp_bytes: Int64?
        let review_installer_files: Int?
        let review_installer_bytes: Int64?
        let safe_reclaimable_bytes: Int64?
        let error: String?
    }

    private struct CleanReply: Decodable {
        let ok: Bool
        let node_name: String?
        let deleted_temp_files: Int?
        let reclaimed_bytes: Int64?
        let quarantined_files: Int?
        let quarantined_bytes: Int64?
        let restored_files: Int?
        let purged_files: Int?
        let purged_bytes: Int64?
        let skipped: Int?
        let error: String?
    }

    private struct Node { let label: String; let endpoint: String }

    static func tryHandle(_ original: String, app: AppModel) async -> Bool {
        let lower = normalize(original)
        guard let mode = requestedMode(lower) else { return false }

        let target = requestedTarget(lower)
        let nodes = selectedNodes(target)
        guard !nodes.isEmpty else { return false }

        app.draft = ""
        app.isGenerating = true
        defer { app.isGenerating = false }

        var replies: [String] = []
        for node in nodes {
            switch mode {
            case .audit:
                if let result = await audit(node.endpoint), result.ok {
                    let name = cleanName(result.node_name) ?? node.label
                    let safe = formatBytes(result.safe_reclaimable_bytes ?? result.safe_temp_bytes ?? 0)
                    let installers = formatBytes(result.review_installer_bytes ?? 0)
                    replies.append("\(name): \(safe) of safe temp junk across \(result.safe_temp_files ?? 0) files; \(installers) of old installer/archive clutter across \(result.review_installer_files ?? 0) files can be quarantined for review")
                } else {
                    replies.append("\(node.label): audit didn't answer")
                }
            case .clean:
                if let result = await mutate(node.endpoint, path: "/housekeeping/clean"), result.ok {
                    let name = cleanName(result.node_name) ?? node.label
                    replies.append("\(name): reclaimed \(formatBytes(result.reclaimed_bytes ?? 0)) from stale temp files and quarantined \(result.quarantined_files ?? 0) old installer/archive files for rollback")
                } else {
                    replies.append("\(node.label): cleanup didn't answer")
                }
            case .restore:
                if let result = await mutate(node.endpoint, path: "/housekeeping/restore", confirm: false), result.ok {
                    let name = cleanName(result.node_name) ?? node.label
                    replies.append("\(name): restored \(result.restored_files ?? 0) quarantined files")
                } else {
                    replies.append("\(node.label): there wasn't a restorable cleanup run")
                }
            case .purge:
                if let result = await mutate(node.endpoint, path: "/housekeeping/purge"), result.ok {
                    let name = cleanName(result.node_name) ?? node.label
                    replies.append("\(name): permanently purged \(result.purged_files ?? 0) quarantined files / \(formatBytes(result.purged_bytes ?? 0))")
                } else {
                    replies.append("\(node.label): quarantine purge didn't complete")
                }
            }
        }

        let prefix: String
        switch mode {
        case .audit: prefix = "Housekeeping scan finished, baby."
        case .clean: prefix = "Safe cleanup finished, baby. Personal pictures, video, music, documents, active programs, and Vex/Ollama/ComfyUI models were protected."
        case .restore: prefix = "Rollback finished, baby."
        case .purge: prefix = "Quarantine purge finished, baby."
        }
        appendExchange(user: original, assistant: prefix + " " + replies.joined(separator: " • ") + " 🖤", app: app)
        return true
    }

    private static func requestedMode(_ lower: String) -> Mode? {
        let houseWords = lower.contains("housekeep") || lower.contains("clutter") || lower.contains("junk") ||
            lower.contains("cleanup") || lower.contains("clean up") || lower.contains("temp files") ||
            lower.contains("unnecessary files")
        if lower.contains("restore") && (lower.contains("cleanup") || lower.contains("quarantine")) { return .restore }
        if (lower.contains("purge") || lower.contains("permanently delete")) && lower.contains("quarantine") { return .purge }
        guard houseWords else { return nil }
        if lower.contains("scan") || lower.contains("audit") || lower.contains("check") || lower.contains("how much") { return .audit }
        if lower.contains("clean") || lower.contains("remove") || lower.contains("housekeep") { return .clean }
        return .audit
    }

    private static func requestedTarget(_ lower: String) -> Target {
        if lower.contains("both") { return .both }
        if ["ashley", "downstairs", "kitchen", "second pc", "utility node"].contains(where: { lower.contains($0) }) { return .secondary }
        if ["monte", "upstairs", "primary", "main pc", "tower"].contains(where: { lower.contains($0) }) { return .primary }
        return .primary
    }

    private static func selectedNodes(_ target: Target) -> [Node] {
        let defaults = UserDefaults.standard
        let primary = defaults.string(forKey: WebBrain.searxEndpointKey)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let secondary = defaults.string(forKey: WebBrain.secondaryBridgeEndpointKey)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        var nodes: [Node] = []
        if target != .secondary, valid(primary) { nodes.append(Node(label: "upstairs/primary PC", endpoint: primary)) }
        if target != .primary, secondary != primary, valid(secondary) { nodes.append(Node(label: "Ashley/downstairs utility PC", endpoint: secondary)) }
        return nodes
    }

    private static func audit(_ endpoint: String) async -> AuditReply? {
        guard let url = makeURL(endpoint, path: "/housekeeping/audit") else { return nil }
        var request = URLRequest(url: url)
        request.timeoutInterval = 30
        do {
            let (data, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else { return nil }
            return try? JSONDecoder().decode(AuditReply.self, from: data)
        } catch { return nil }
    }

    private static func mutate(_ endpoint: String, path: String, confirm: Bool = true) async -> CleanReply? {
        guard let url = makeURL(endpoint, path: path) else { return nil }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 60
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: confirm ? ["confirm": true] : [:])
        do {
            let (data, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...499).contains(http.statusCode) else { return nil }
            return try? JSONDecoder().decode(CleanReply.self, from: data)
        } catch { return nil }
    }

    private static func makeURL(_ endpoint: String, path: String) -> URL? {
        guard let root = URL(string: endpoint), var parts = URLComponents(url: root, resolvingAgainstBaseURL: false) else { return nil }
        parts.path = path
        return parts.url
    }

    private static func valid(_ endpoint: String) -> Bool {
        guard let url = URL(string: endpoint), !endpoint.isEmpty else { return false }
        return VexBridgeNetworking.isBridgeURL(url)
    }

    private static func formatBytes(_ value: Int64) -> String {
        let amount = Double(max(0, value))
        if amount >= 1_073_741_824 { return String(format: "%.2f GB", amount / 1_073_741_824) }
        if amount >= 1_048_576 { return String(format: "%.1f MB", amount / 1_048_576) }
        if amount >= 1024 { return String(format: "%.1f KB", amount / 1024) }
        return "\(Int(amount)) B"
    }

    private static func cleanName(_ value: String?) -> String? {
        let result = value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return result.isEmpty ? nil : result
    }

    private static func appendExchange(user: String, assistant: String, app: AppModel) {
        app.profile.messages.append(ChatMessage(role: .user, content: user))
        app.profile.messages.append(ChatMessage(role: .assistant, content: assistant))
        app.persist()
    }

    private static func normalize(_ text: String) -> String {
        text.lowercased().replacingOccurrences(of: "’", with: "'").trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

'''
text = text.replace(insert_marker, housekeeper + insert_marker, 1)

path.write_text(text, encoding="utf-8")

checks = [
    "v0.9.5 Resource Director", "PCHousekeeperRouter", 'path: "/housekeeping/clean"',
    "Ashley/downstairs utility PC", 'for endpoint in [primary, lastCognition, last, secondary]',
    'for endpoint in [primary, last, secondary]', 'lower.contains("node")',
]
final = path.read_text(encoding="utf-8")
for marker in checks:
    if marker not in final:
        raise SystemExit(f"missing v0.9.5 iOS marker: {marker}")

print("Applied v0.9.5 primary/utility Resource Director + deterministic node status + Vex Housekeeper router")
