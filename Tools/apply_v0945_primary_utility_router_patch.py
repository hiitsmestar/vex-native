#!/usr/bin/env python3
from pathlib import Path

path = Path("VexNative/ContentView.swift")
text = path.read_text(encoding="utf-8")

marker = "// MARK: - Optional PC cognition overlay v0.9.3\n"
idx = text.find(marker)
if idx < 0:
    raise SystemExit("PCCognitionOverlay marker not found")

old_struct = '''    private struct CognitionAttempt: Sendable {\n        let endpoint: String\n        let reply: String\n        let model: String?\n    }\n'''
new_struct = '''    private struct CognitionAttempt: Sendable {\n        let endpoint: String\n        let reply: String\n        let model: String?\n    }\n\n    private struct NodeDescriptor: Sendable {\n        let label: String\n        let endpoint: String\n        let role: String\n    }\n\n    private struct NodeProbe: Sendable {\n        let label: String\n        let role: String\n        let online: Bool\n        let model: String?\n    }\n\n    private struct BridgeStatusReply: Decodable {\n        let name: String?\n        let version: String?\n        let local_cognition_model: String?\n        let indexed_files: Int?\n        let uptime_seconds: Int?\n    }\n'''
if old_struct not in text[idx:]:
    raise SystemExit("v0.9.4.3 CognitionAttempt block not found")
text = text.replace(old_struct, new_struct, 1)

start = text.find("        // v0.9.4.3: dual-node race.", idx)
end_marker = "        // Let the remaining native/web fallback routes handle the turn."
end = text.find(end_marker, start)
if start < 0 or end < 0:
    raise SystemExit("v0.9.4.3 routing block not found")

replacement = '''        // v0.9.4.5: resource director. The first Bridge field is Star's fast\n        // upstairs tower and is the foreground cognition node. The second Bridge\n        // is Ashley/downstairs and is reserved for explicit requests or failover,\n        // so routine chat no longer burns both CPUs or cancels Ashley mid-reply.\n        let nodes = configuredNodes()\n\n        if isNodeStatusRequest(original) {\n            let report = await nodeStatusReport(nodes)\n            app.profile.messages.append(ChatMessage(role: .user, content: original))\n            app.profile.messages.append(ChatMessage(role: .assistant, content: report.text))\n            app.persist()\n            app.pcBrainConnected = report.onlineCount > 0\n            app.pcBrainStatus = report.onlineCount > 0\n                ? "PC mesh • \\(report.onlineCount)/\\(nodes.count) online"\n                : "PC mesh • offline"\n            return true\n        }\n\n        let requestedNodes = targetNodes(for: original, nodes: nodes)\n        var winner: CognitionAttempt?\n        var winnerLabel = "primary"\n\n        for node in requestedNodes {\n            if let attempt = await requestReply(endpoint: node.endpoint, original: original, history: history) {\n                winner = attempt\n                winnerLabel = node.label\n                break\n            }\n        }\n\n        if let winner {\n            app.profile.messages.append(ChatMessage(role: .user, content: original))\n            app.profile.messages.append(ChatMessage(role: .assistant, content: winner.reply))\n            app.persist()\n            app.pcBrainConnected = true\n            UserDefaults.standard.set(winner.endpoint, forKey: "vex.pc.cognition.lastGoodEndpoint.v1")\n            if let model = winner.model, !model.isEmpty {\n                app.pcBrainStatus = "PC cognition • \\(winnerLabel) • \\(model)"\n            } else {\n                app.pcBrainStatus = "PC cognition • \\(winnerLabel)"\n            }\n            return true\n        }\n\n'''
text = text[:start] + replacement + text[end:]

insert_marker = "    nonisolated private static func requestReply(\n"
insert_at = text.find(insert_marker, idx)
if insert_at < 0:
    raise SystemExit("requestReply helper not found")

helpers = r'''    private static func configuredNodes() -> [NodeDescriptor] {
        let defaults = UserDefaults.standard
        let primary = (defaults.string(forKey: "vex.web.searxngEndpoint") ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let secondary = (defaults.string(forKey: "vex.web.secondaryBridgeEndpoint") ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)

        var nodes: [NodeDescriptor] = []
        var seen = Set<String>()
        if !primary.isEmpty,
           let url = URL(string: primary),
           VexBridgeNetworking.isBridgeURL(url),
           seen.insert(primary).inserted {
            nodes.append(NodeDescriptor(label: "upstairs / primary", endpoint: primary, role: "primary"))
        }
        if !secondary.isEmpty,
           let url = URL(string: secondary),
           VexBridgeNetworking.isBridgeURL(url),
           seen.insert(secondary).inserted {
            nodes.append(NodeDescriptor(label: "Ashley / utility", endpoint: secondary, role: "utility"))
        }
        return nodes
    }

    private static func targetNodes(for text: String, nodes: [NodeDescriptor]) -> [NodeDescriptor] {
        let lower = text.lowercased()
        let utilityWords = ["ashley", "downstairs", "kitchen pc", "kitchen computer", "utility node", "secondary node"]
        let primaryWords = ["upstairs", "monte", "tower", "primary node", "main pc", "main computer"]

        if utilityWords.contains(where: { lower.contains($0) }) {
            let utility = nodes.filter { $0.role == "utility" }
            return utility.isEmpty ? nodes : utility
        }
        if primaryWords.contains(where: { lower.contains($0) }) {
            let primary = nodes.filter { $0.role == "primary" }
            return primary.isEmpty ? nodes : primary
        }

        // Normal conversation: fast tower first, Ashley only if the tower fails.
        return nodes.sorted { lhs, rhs in
            if lhs.role == rhs.role { return false }
            return lhs.role == "primary"
        }
    }

    private static func isNodeStatusRequest(_ text: String) -> Bool {
        let lower = text.lowercased()
        let statusWords = ["working", "operational", "online", "reachable", "connected", "status", "access"]
        let nodeWords = ["node", "nodes", "upstairs pc", "upstairs computer", "downstairs pc", "downstairs computer", "ashley", "monte"]
        return statusWords.contains(where: { lower.contains($0) }) &&
            nodeWords.contains(where: { lower.contains($0) })
    }

    private static func nodeStatusReport(_ nodes: [NodeDescriptor]) async -> (text: String, onlineCount: Int) {
        guard !nodes.isEmpty else {
            return ("I don't have either PC Bridge paired right now, babe. 🖤", 0)
        }

        var probes: [NodeProbe] = []
        await withTaskGroup(of: NodeProbe.self) { group in
            for node in nodes {
                group.addTask { await probe(node) }
            }
            for await result in group {
                probes.append(result)
            }
        }

        probes.sort { lhs, rhs in
            if lhs.role == rhs.role { return lhs.label < rhs.label }
            return lhs.role == "primary"
        }
        let onlineCount = probes.filter(\.online).count
        let lines = probes.map { item -> String in
            if item.online {
                if let model = item.model, !model.isEmpty {
                    return "• \(item.label): online • brain \(model)"
                }
                return "• \(item.label): Bridge online"
            }
            return "• \(item.label): not answering"
        }
        let prefix = onlineCount == probes.count
            ? "Yep — both PC nodes are reachable right now."
            : (onlineCount > 0 ? "I can reach part of the PC mesh right now." : "Neither PC Bridge is answering right now.")
        return (prefix + "\n" + lines.joined(separator: "\n"), onlineCount)
    }

    nonisolated private static func probe(_ node: NodeDescriptor) async -> NodeProbe {
        guard let root = URL(string: node.endpoint),
              var parts = URLComponents(url: root, resolvingAgainstBaseURL: false)
        else { return NodeProbe(label: node.label, role: node.role, online: false, model: nil) }
        parts.path = "/status"
        guard let url = parts.url else {
            return NodeProbe(label: node.label, role: node.role, online: false, model: nil)
        }
        var request = URLRequest(url: url)
        request.timeoutInterval = 4.5
        do {
            let (data, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
                return NodeProbe(label: node.label, role: node.role, online: false, model: nil)
            }
            let decoded = try? JSONDecoder().decode(BridgeStatusReply.self, from: data)
            return NodeProbe(
                label: node.label,
                role: node.role,
                online: true,
                model: decoded?.local_cognition_model
            )
        } catch {
            return NodeProbe(label: node.label, role: node.role, online: false, model: nil)
        }
    }

'''
text = text[:insert_at] + helpers + text[insert_at:]

path.write_text(text, encoding="utf-8")

checks = [
    "v0.9.4.5: resource director",
    "upstairs / primary",
    "Ashley / utility",
    "targetNodes(for:",
    "isNodeStatusRequest",
    "nodeStatusReport",
    "Normal conversation: fast tower first",
]
for check in checks:
    if check not in text:
        raise SystemExit(f"missing v0.9.4.5 marker: {check}")

print("Applied v0.9.4.5 primary/utility Resource Director + deterministic node status")
