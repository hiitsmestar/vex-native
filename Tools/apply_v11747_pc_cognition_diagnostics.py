#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


CONTENT = Path("VexNative/ContentView.swift")
APP = Path("VexNative/AppModel.swift")


content = CONTENT.read_text(encoding="utf-8")
overlay_start_marker = "@MainActor\nprivate enum PCCognitionOverlay {"
overlay_end_marker = "\n// MARK: - Vex Housekeeper v0.9.6 active maintenance"
start = content.find(overlay_start_marker)
end = content.find(overlay_end_marker, start)
if start < 0 or end < 0:
    raise SystemExit("v0.11.7.47 PC cognition overlay anchor missing")

new_overlay = r'''@MainActor
private enum PCCognitionOverlay {
    private struct OverlayReply: Decodable {
        let ok: Bool
        let reply: String?
        let model: String?
        let error: String?
        let setup: String?
    }

    private struct BridgeErrorReply: Decodable {
        let ok: Bool?
        let error: String?
        let setup: String?
    }

    private struct ConfiguredEndpoint: Sendable {
        let label: String
        let value: String
    }

    private struct CognitionAttempt: Sendable {
        let endpoint: String
        let reply: String
        let model: String?
    }

    private struct CognitionFailure: Sendable {
        let label: String
        let reason: String
    }

    private enum CognitionResult: Sendable {
        case success(CognitionAttempt)
        case failure(CognitionFailure)
    }

    static func tryHandle(_ original: String, app: AppModel) async -> Bool {
        guard shouldUse(original) else { return false }
        let endpoints = configuredEndpoints()
        guard !endpoints.isEmpty else {
            app.pcBrainConnected = false
            app.pcBrainStatus = "PC cognition unavailable • no paired Bridge endpoint"
            return false
        }

        // v0.9.4.2: acknowledge the send immediately. Previously the composer
        // appeared dead while /llm/chat waited up to 45 seconds because the draft
        // stayed on screen and isGenerating was not set until AFTER a reply arrived.
        app.draft = ""
        app.isGenerating = true
        app.pcBrainStatus = "PC cognition • thinking…"
        defer { app.isGenerating = false }

        let history = app.profile.messages.suffix(28).map { message -> [String: String] in
            ["role": message.role.rawValue, "content": String(message.content.prefix(5000))]
        }

        let personaContext = String(app.profile.persona.prefix(6000))
        let userProfileContext = String(app.profile.userProfile.prefix(3500))
        let stateContext: [String: String] = [
            "mood": app.profile.state.mood,
            "outfit": app.profile.state.outfit,
            "location": app.profile.state.location,
            "scene": app.profile.state.scene
        ]

        var failures: [CognitionFailure] = []
        func record(_ result: CognitionResult) -> CognitionAttempt? {
            switch result {
            case .success(let attempt):
                return attempt
            case .failure(let failure):
                failures.append(failure)
                return nil
            }
        }

        // v0.9.5 Resource Director: the first configured Bridge is the foreground
        // primary node. Utility nodes retain every tool permission, but they only
        // receive interactive cognition when primary fails.
        var winner: CognitionAttempt?
        if let primary = endpoints.first {
            if isBridgeEndpoint(primary.value) {
                Task { await syncPersonalMemory(endpoint: primary.value, app: app) }
            }
            let result = await requestReply(
                endpoint: primary,
                original: original,
                history: history,
                persona: personaContext,
                userProfile: userProfileContext,
                state: stateContext
            )
            winner = record(result)
        } else {
            winner = nil
        }

        if winner == nil {
            for fallback in endpoints.dropFirst() {
                if isBridgeEndpoint(fallback.value) {
                    Task { await syncPersonalMemory(endpoint: fallback.value, app: app) }
                }
                let result = await requestReply(
                    endpoint: fallback,
                    original: original,
                    history: history,
                    persona: personaContext,
                    userProfile: userProfileContext,
                    state: stateContext
                )
                if let candidate = record(result) {
                    winner = candidate
                    break
                }
            }
        }

        if let winner {
            app.profile.messages.append(ChatMessage(role: .user, content: original))
            app.profile.messages.append(ChatMessage(role: .assistant, content: winner.reply))
            app.persist()
            app.pcBrainConnected = true
            UserDefaults.standard.set(winner.endpoint, forKey: "vex.pc.cognition.lastGoodEndpoint.v1")
            if let model = winner.model, !model.isEmpty {
                app.pcBrainStatus = "PC cognition • \(model)"
            } else {
                app.pcBrainStatus = "PC cognition • connected"
            }
            return true
        }

        // Let the remaining native/web fallback routes handle the turn. They expect
        // the original text to still be in draft, so restore it only on total PC
        // cognition failure.
        app.draft = original
        app.pcBrainConnected = false
        app.pcBrainStatus = "PC cognition unavailable • \(failureSummary(failures, endpointCount: endpoints.count))"
        return false
    }

    nonisolated private static func requestReply(
        endpoint: ConfiguredEndpoint,
        original: String,
        history: [[String: String]],
        persona: String,
        userProfile: String,
        state: [String: String]
    ) async -> CognitionResult {
        guard let root = URL(string: endpoint.value) else {
            return failure(endpoint, "invalid endpoint URL")
        }
        guard VexBridgeNetworking.isBridgeURL(root) else {
            return failure(endpoint, "not a private HTTPS Bridge URL on port 8765")
        }
        guard var parts = URLComponents(url: root, resolvingAgainstBaseURL: false) else {
            return failure(endpoint, "invalid endpoint URL")
        }
        parts.path = "/llm/chat"
        guard let url = parts.url else {
            return failure(endpoint, "invalid /llm/chat URL")
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 90
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body: [String: Any] = [
            "message": String(original.prefix(5000)),
            "history": history,
            "persona": persona,
            "user_profile": userProfile,
            "state": state
        ]
        guard let requestBody = try? JSONSerialization.data(withJSONObject: body) else {
            return failure(endpoint, "could not encode cognition request")
        }
        request.httpBody = requestBody

        do {
            let (data, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse else {
                return failure(endpoint, "non-HTTP Bridge response")
            }
            guard (200...299).contains(http.statusCode) else {
                return failure(endpoint, httpFailure(status: http.statusCode, data: data))
            }
            let decoded: OverlayReply
            do {
                decoded = try JSONDecoder().decode(OverlayReply.self, from: data)
            } catch {
                return failure(endpoint, "bad /llm/chat JSON")
            }
            guard decoded.ok else {
                let reason = sanitizedBridgeMessage(decoded.error) ?? sanitizedBridgeMessage(decoded.setup) ?? "Bridge rejected /llm/chat"
                return failure(endpoint, reason)
            }
            guard let reply = decoded.reply?.trimmingCharacters(in: .whitespacesAndNewlines), !reply.isEmpty else {
                return failure(endpoint, "empty PC cognition reply")
            }
            return .success(CognitionAttempt(endpoint: endpoint.value, reply: reply, model: decoded.model))
        } catch {
            return failure(endpoint, networkFailure(error))
        }
    }

    private static func failure(_ endpoint: ConfiguredEndpoint, _ reason: String) -> CognitionResult {
        .failure(CognitionFailure(label: endpoint.label, reason: reason))
    }

    private static func httpFailure(status: Int, data: Data) -> String {
        let bridgeMessage = decodeBridgeMessage(data)
        switch status {
        case 401:
            return "bridge token rejected"
        case 404:
            return "/llm/chat route missing"
        case 413:
            return "cognition payload too large"
        case 503:
            if bridgeMessage?.lowercased().contains("no local cognition") == true {
                return "no local cognition model"
            }
            if let bridgeMessage {
                return "Bridge unavailable: \(bridgeMessage)"
            }
            return "Bridge unavailable"
        default:
            if let bridgeMessage {
                return "Bridge HTTP \(status): \(bridgeMessage)"
            }
            return "Bridge HTTP \(status)"
        }
    }

    private static func decodeBridgeMessage(_ data: Data) -> String? {
        guard !data.isEmpty,
              let decoded = try? JSONDecoder().decode(BridgeErrorReply.self, from: data)
        else { return nil }
        return sanitizedBridgeMessage(decoded.error) ?? sanitizedBridgeMessage(decoded.setup)
    }

    private static func sanitizedBridgeMessage(_ raw: String?) -> String? {
        guard var value = raw else { return nil }
        value = value
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
            .replacingOccurrences(of: #"(?i)(token|pin)=([^&\s]+)"#, with: "$1=[redacted]", options: .regularExpression)
            .replacingOccurrences(of: #"[A-Za-z]:\\[^\s]+"#, with: "[local path]", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty else { return nil }
        return String(value.prefix(120))
    }

    private static func networkFailure(_ error: Error) -> String {
        if let bridgeError = error as? VexBridgeNetworkingError {
            switch bridgeError {
            case .missingCertificatePin:
                return "certificate pin missing"
            case .invalidCertificatePin:
                return "certificate pin malformed"
            case .certificateMismatch:
                return "certificate mismatch"
            }
        }

        if let urlError = error as? URLError {
            switch urlError.code {
            case .timedOut:
                return "timeout waiting for Bridge"
            case .cannotFindHost, .dnsLookupFailed, .cannotConnectToHost, .networkConnectionLost, .notConnectedToInternet:
                return "LAN connection failed"
            case .secureConnectionFailed, .serverCertificateUntrusted, .serverCertificateHasBadDate, .serverCertificateNotYetValid, .clientCertificateRejected, .clientCertificateRequired:
                return "TLS handshake failed"
            case .appTransportSecurityRequiresSecureConnection:
                return "iOS blocked Bridge transport"
            default:
                return "network error \(urlError.code.rawValue)"
            }
        }

        return "network error"
    }

    private static func failureSummary(_ failures: [CognitionFailure], endpointCount: Int) -> String {
        guard !failures.isEmpty else {
            return endpointCount <= 0 ? "no paired Bridge endpoint" : "no endpoint returned a result"
        }

        let priority = [
            "certificate mismatch",
            "certificate pin missing",
            "certificate pin malformed",
            "bridge token rejected",
            "/llm/chat route missing",
            "no local cognition model",
            "timeout waiting for Bridge",
            "LAN connection failed",
            "TLS handshake failed",
            "not a private HTTPS Bridge URL on port 8765"
        ]
        for reason in priority {
            if let failure = failures.first(where: { $0.reason == reason }) {
                return "\(failure.label): \(failure.reason)"
            }
        }

        let first = failures[0]
        let suffix = failures.count > 1 ? "; \(failures.count - 1) more" : ""
        return "\(first.label): \(first.reason)\(suffix)"
    }

    private static func postMemorySync(endpoint: String, payload: [String: Any], timeout: TimeInterval) async -> Bool {
        guard isBridgeEndpoint(endpoint), let url = endpointURL(endpoint, path: "/memory/sync") else { return false }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = timeout
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        guard let body = try? JSONSerialization.data(withJSONObject: payload) else { return false }
        request.httpBody = body
        do {
            let (_, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse else { return false }
            return (200...299).contains(http.statusCode)
        } catch {
            return false
        }
    }

    private static let memorySyncCountPrefix = "vex.pc.memory.syncCount.v1."
    private static let memoryMetadataAtPrefix = "vex.pc.memory.metadataAt.v1."

    private static func memoryEndpointKey(_ endpoint: String) -> String {
        Data(endpoint.utf8).base64EncodedString()
    }

    private static func syncPersonalMemory(endpoint: String, app: AppModel) async {
        try? await Task.sleep(nanoseconds: 750_000_000)
        let key = memoryEndpointKey(endpoint)
        let defaults = UserDefaults.standard

        // Refresh persona/profile/rules/current state periodically. Use Codable so
        // new BrainProfile fields automatically join the memory snapshot later.
        let metadataKey = memoryMetadataAtPrefix + key
        let lastMetadataAt = defaults.double(forKey: metadataKey)
        if lastMetadataAt <= 0 || Date().timeIntervalSince1970 - lastMetadataAt > 600 {
            let encoder = JSONEncoder()
            encoder.dateEncodingStrategy = .secondsSince1970
            if let encoded = try? encoder.encode(app.profile),
               var profileObject = (try? JSONSerialization.jsonObject(with: encoded)) as? [String: Any] {
                // Raw chat history is sent separately in bounded incremental batches.
                profileObject.removeValue(forKey: "messages")
                let payload: [String: Any] = [
                    "source": "vexnative-iphone-v0.11",
                    "thread_id": "vexnative-iphone",
                    "profile": profileObject
                ]
                if await postMemorySync(endpoint: endpoint, payload: payload, timeout: 8) {
                    defaults.set(Date().timeIntervalSince1970, forKey: metadataKey)
                }
            }
        }

        // Copy the complete native chat archive once, then only the new suffix.
        // Count is kept per paired Bridge because each PC owns its own local DB.
        let countKey = memorySyncCountPrefix + key
        let messages = app.profile.messages
        var synced = defaults.integer(forKey: countKey)
        if synced < 0 || synced > messages.count { synced = 0 }
        guard synced < messages.count else { return }

        let batchSize = 100
        while synced < messages.count {
            let end = min(messages.count, synced + batchSize)
            let batch = (synced..<end).map { index -> [String: Any] in
                let message = messages[index]
                return [
                    "id": message.id.uuidString,
                    "ordinal": index,
                    "role": message.role.rawValue,
                    "content": String(message.content.prefix(50000)),
                    "created_at": message.createdAt.timeIntervalSince1970
                ]
            }
            let payload: [String: Any] = [
                "source": "vexnative-iphone-v0.11",
                "thread_id": "vexnative-iphone",
                "start_ordinal": synced,
                "messages": batch
            ]
            guard await postMemorySync(endpoint: endpoint, payload: payload, timeout: 12) else {
                // Older Bridge or temporarily unavailable memory worker: cognition
                // continues normally and the same batch is retried next PC turn.
                return
            }
            synced = end
            defaults.set(synced, forKey: countKey)
        }
    }

    private static func shouldUse(_ text: String) -> Bool {
        let lower = text.lowercased()
        // Existing native routes stay authoritative for tools, live research and visuals.
        let exclusions = [
            "search the web", "search online", "look up ", "latest", "current ", "today",
            "weather", "news", "http://", "https://", "take a photo", "take photo",
            "picture", " image", "camera", "back view", "rear view", "front view", "side view",
            "from behind", "turn around", "open youtube", "open google", "open browser",
            "volume", "pause", "next track", "playlist"
        ]
        return !exclusions.contains(where: { lower.contains($0) })
    }

    private static func configuredEndpoints() -> [ConfiguredEndpoint] {
        let defaults = UserDefaults.standard
        let primary = defaults.string(forKey: WebBrain.searxEndpointKey)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let secondary = defaults.string(forKey: WebBrain.secondaryBridgeEndpointKey)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let lastCognition = defaults.string(forKey: "vex.pc.cognition.lastGoodEndpoint.v1")?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let lastBrowser = defaults.string(forKey: "vex.pc.smartBrowser.lastEndpoint.v1")?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        var values: [ConfiguredEndpoint] = []

        func append(label: String, endpoint: String) {
            guard !endpoint.isEmpty, !values.contains(where: { $0.value == endpoint }) else { return }
            values.append(ConfiguredEndpoint(label: label, value: endpoint))
        }

        append(label: "primary", endpoint: primary)
        append(label: "last good", endpoint: lastCognition)
        append(label: "browser bridge", endpoint: lastBrowser)
        append(label: "second", endpoint: secondary)
        return values
    }

    private static func isBridgeEndpoint(_ endpoint: String) -> Bool {
        guard let url = URL(string: endpoint) else { return false }
        return VexBridgeNetworking.isBridgeURL(url)
    }

    private static func endpointURL(_ endpoint: String, path: String) -> URL? {
        guard let root = URL(string: endpoint), var parts = URLComponents(url: root, resolvingAgainstBaseURL: false) else { return nil }
        parts.path = path
        return parts.url
    }
}
'''

content = content[:start] + new_overlay + content[end:]
CONTENT.write_text(content, encoding="utf-8")

app = APP.read_text(encoding="utf-8")
old_message = '''        guard let engine else {
            profile.messages.append(ChatMessage(
                role: .assistant,
                content: "My PC cognition node didn't answer that turn and my onboard fallback brain is parked in startup-safe mode. Open Brain only if you want to load the saved iPhone model manually. 🖤"
            ))
            persist()
            isGenerating = false
            return
        }
'''
new_message = '''        guard let engine else {
            let detail = pcBrainStatus.trimmingCharacters(in: .whitespacesAndNewlines)
            let reason = detail.isEmpty ? "PC cognition unavailable" : detail
            profile.messages.append(ChatMessage(
                role: .assistant,
                content: "I couldn't use the PC cognition path for that turn (\\(reason)), and my onboard fallback brain is parked in startup-safe mode. Open Brain only if you want to load the saved iPhone model manually. 🖤"
            ))
            persist()
            isGenerating = false
            return
        }
'''
if old_message not in app:
    raise SystemExit("v0.11.7.47 startup-safe fallback message anchor missing")
app = app.replace(old_message, new_message, 1)
APP.write_text(app, encoding="utf-8")

overlay = content[start:content.find(overlay_end_marker, start)]
checks = [
    ("diagnostic result type", "private enum CognitionResult: Sendable" in overlay),
    ("token rejection diagnostic", "bridge token rejected" in overlay),
    ("route missing diagnostic", '"/llm/chat route missing"' in overlay),
    ("last good endpoint retry", "lastCognition" in overlay and "vex.pc.cognition.lastGoodEndpoint.v1" in overlay),
    ("device terms reach cognition", '"computer"' not in overlay and '" pc"' not in overlay and '"iphone"' not in overlay and '"phone"' not in overlay),
    ("memory sync bridge guard", "guard isBridgeEndpoint(endpoint), let url = endpointURL(endpoint, path: \"/memory/sync\")" in overlay),
    ("fallback detail", "I couldn't use the PC cognition path for that turn" in app),
]
missing = [name for name, ok in checks if not ok]
if missing:
    raise SystemExit("v0.11.7.47 diagnostics verifier failed: " + ", ".join(missing))

print("Applied VexNative v0.11.7.47 PC cognition route diagnostics")
