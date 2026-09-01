#!/usr/bin/env python3
from pathlib import Path

path = Path("VexNative/ContentView.swift")
text = path.read_text(encoding="utf-8")

for marker in [
    "let cognitionEndpoints = isVerifiedPersonalRecallTurn(original)",
    "await syncPersonalMetadata(endpoint: endpoint.value, app: app)",
    "await withTaskGroup(of: CognitionResult.self)",
]:
    if marker not in text:
        raise SystemExit(f"v0.11.7.53 expected .52 marker missing: {marker}")

# Add a compact agent response contract inside the PC cognition overlay.
struct_anchor = '''    private struct BridgeErrorReply: Decodable {
        let ok: Bool?
        let error: String?
        let setup: String?
    }
'''
agent_struct = struct_anchor + '''
    private struct AgentReply: Decodable {
        let ok: Bool
        let reply: String?
        let delegated: String?
        let tool: String?
        let error: String?
    }
'''
if "private struct AgentReply: Decodable" not in text:
    if struct_anchor not in text:
        raise SystemExit("v0.11.7.53 BridgeErrorReply anchor missing")
    text = text.replace(struct_anchor, agent_struct, 1)

# Before the ordinary cognition race, ask the primary PC's capability-aware agent
# once. It may execute a verified local tool or return delegated=chat. Only the
# primary receives this call so mutating intents cannot execute twice.
race_anchor = '''        var winner: CognitionAttempt?
        await withTaskGroup(of: CognitionResult.self) { group in
'''
agent_call = '''        // v0.11.7.53: Full AI router. Give the primary PC agent first refusal
        // for memory/research/device/tool intents. Ordinary conversation falls
        // through to the proven multi-PC /llm/chat race.
        if let primary = cognitionEndpoints.first,
           isBridgeEndpoint(primary.value),
           let agentWinner = await requestAgentReply(endpoint: primary, original: original) {
            app.profile.messages.append(ChatMessage(role: .user, content: original))
            app.profile.messages.append(ChatMessage(role: .assistant, content: agentWinner.reply))
            app.persist()
            app.pcBrainConnected = true
            UserDefaults.standard.set(primary.value, forKey: "vex.pc.cognition.lastGoodEndpoint.v1")
            app.pcBrainStatus = "PC agent • \(agentWinner.model ?? "tool")"
            return true
        }

        var winner: CognitionAttempt?
        await withTaskGroup(of: CognitionResult.self) { group in
'''
if "let agentWinner = await requestAgentReply" not in text:
    if race_anchor not in text:
        raise SystemExit("v0.11.7.53 cognition race anchor missing")
    text = text.replace(race_anchor, agent_call, 1)

# Insert the agent transport immediately before the normal /llm/chat transport.
request_anchor = '''    nonisolated private static func requestReply(
'''
agent_request = r'''    nonisolated private static func requestAgentReply(
        endpoint: ConfiguredEndpoint,
        original: String
    ) async -> CognitionAttempt? {
        guard let root = URL(string: endpoint.value), VexBridgeNetworking.isBridgeURL(root) else { return nil }
        guard var parts = URLComponents(url: root, resolvingAgainstBaseURL: false) else { return nil }
        parts.path = "/agent/run"
        guard let url = parts.url else { return nil }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 18
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        guard let body = try? JSONSerialization.data(withJSONObject: ["message": String(original.prefix(3500))]) else { return nil }
        request.httpBody = body

        do {
            let (data, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else { return nil }
            guard let decoded = try? JSONDecoder().decode(AgentReply.self, from: data), decoded.ok else { return nil }
            if decoded.delegated?.lowercased() == "chat" { return nil }
            guard let reply = decoded.reply?.trimmingCharacters(in: .whitespacesAndNewlines), !reply.isEmpty else { return nil }
            return CognitionAttempt(endpoint: endpoint.value, reply: reply, model: decoded.tool ?? "vex-agent-v1200")
        } catch {
            // Agent discovery/execution is opportunistic. Existing /llm/chat
            // remains the reliable fallback when the PC runtime predates v0.12.0.
            return nil
        }
    }

'''
if "private static func requestAgentReply(" not in text:
    if request_anchor not in text:
        raise SystemExit("v0.11.7.53 requestReply anchor missing")
    text = text.replace(request_anchor, agent_request + request_anchor, 1)

path.write_text(text, encoding="utf-8")

required = [
    "private struct AgentReply: Decodable",
    'parts.path = "/agent/run"',
    "let agentWinner = await requestAgentReply(endpoint: primary, original: original)",
    "decoded.delegated?.lowercased() == \"chat\"",
    "await withTaskGroup(of: CognitionResult.self)",
    "let cognitionEndpoints = isVerifiedPersonalRecallTurn(original)",
]
missing = [x for x in required if x not in text]
if missing:
    raise SystemExit("Missing v0.11.7.53 marker(s): " + " | ".join(missing))
print("Applied VexNative v0.11.7.53 Full AI primary agent router")
