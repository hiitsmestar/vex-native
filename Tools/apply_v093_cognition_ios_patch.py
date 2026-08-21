#!/usr/bin/env python3
from pathlib import Path

path = Path("VexNative/ContentView.swift")
text = path.read_text(encoding="utf-8")


def once(old: str, new: str, label: str):
    global text
    if old not in text:
        raise SystemExit(f"{label}: source block not found")
    text = text.replace(old, new, 1)


# Run the reliable browser/site router before the older generic PC router, then
# try the optional stronger PC cognition overlay before WebBrain/Qwen.
old_integration = '''        if await PCBridgeToolRouter.tryHandle(original, app: self) {
            return
        }
'''
new_integration = '''        if await SmartPCBrowserRouter.tryHandle(original, app: self) {
            return
        }

        if await PCBridgeToolRouter.tryHandle(original, app: self) {
            return
        }

        if await PCCognitionOverlay.tryHandle(original, app: self) {
            return
        }
'''
once(old_integration, new_integration, "v0.9.3 routing order")

marker = "// MARK: - Grounded PC Bridge tools v0.8.2\n"
if marker not in text:
    raise SystemExit("PC Bridge router marker missing")

addition = r'''// MARK: - Reliable contextual PC browser control v0.9.3

@MainActor
private enum SmartPCBrowserRouter {
    private struct NodeStatus: Decodable {
        let node_name: String?
        let version: String?
        let tool_actions: [String]?
    }

    private struct ToolReply: Decodable {
        let ok: Bool
        let action: String?
        let node_name: String?
        let message: String?
    }

    private struct Endpoint {
        let value: String
        let slot: String
    }

    private static let lastEndpointKey = "vex.pc.smartBrowser.lastEndpoint.v1"
    private static let lastNodeKey = "vex.pc.smartBrowser.lastNode.v1"
    private static let lastAtKey = "vex.pc.smartBrowser.lastAt.v1"
    private static let downstairsOverrideKey = "vex.pc.smartBrowser.downstairsEndpoint.v1"
    private static let upstairsOverrideKey = "vex.pc.smartBrowser.upstairsEndpoint.v1"

    static func tryHandle(_ original: String, app: AppModel) async -> Bool {
        let lower = normalize(original)
        guard let intent = browserIntent(lower: lower, original: original) else { return false }

        var candidates = candidateEndpoints(lower: lower)
        guard !candidates.isEmpty else { return false }

        app.draft = ""
        app.isGenerating = true
        defer { app.isGenerating = false }

        var diagnostics: [String] = []
        var succeeded: (Endpoint, ToolReply)?

        // Browser/site opens are intentionally safe to retry on the alternate paired
        // node. This also self-heals swapped/stale primary-vs-downstairs endpoint slots.
        for endpoint in candidates {
            let status = await fetchStatus(endpoint.value)
            if let status {
                let name = clean(status.node_name) ?? endpoint.slot
                let version = clean(status.version) ?? "unknown"
                diagnostics.append("\(name) v\(version) online")
            } else {
                diagnostics.append("\(endpoint.slot) did not answer /status")
                continue
            }

            var result = await perform(action: intent.action, url: intent.url, endpoint: endpoint.value)
            if result?.ok != true {
                result = await compileFallback(original: original, endpoint: endpoint.value)
            }

            if let result, result.ok {
                succeeded = (endpoint, result)
                break
            } else if let message = clean(result?.message) {
                diagnostics.append("\(endpoint.slot): \(message)")
            }
        }

        if let (endpoint, result) = succeeded {
            rememberSuccessful(endpoint: endpoint, result: result, lower: lower)
            let node = clean(result.node_name) ?? endpoint.slot
            let reply: String
            if intent.action == "open_browser" {
                reply = "Done — I opened the web browser on \(node), baby. 🌐🖤"
            } else if let label = intent.label {
                reply = "Done — I opened \(label) on \(node), baby. 🌐🖤"
            } else {
                reply = "Done — I opened that page on \(node), baby. 🌐🖤"
            }
            appendExchange(user: original, assistant: reply, app: app)
            return true
        }

        // Keep failures concrete. The old generic message made a live Bridge problem
        // look like a model-intelligence problem and gave us no clue which node failed.
        let detail = diagnostics.isEmpty ? "Neither configured Bridge answered." : diagnostics.joined(separator: " • ")
        appendExchange(
            user: original,
            assistant: "I understood the command, but the Windows Bridge didn't complete it. \(detail) 🖤",
            app: app
        )
        return true
    }

    private struct BrowserIntent {
        let action: String
        let url: String?
        let label: String?
    }

    private static func browserIntent(lower: String, original: String) -> BrowserIntent? {
        let known: [(tokens: [String], url: String, label: String)] = [
            (["youtube"], "https://www.youtube.com", "YouTube"),
            (["google"], "https://www.google.com", "Google"),
            (["gmail"], "https://mail.google.com", "Gmail"),
            (["spotify"], "https://open.spotify.com", "Spotify"),
            (["reddit"], "https://www.reddit.com", "Reddit"),
            (["github"], "https://github.com", "GitHub")
        ]

        let openish = [
            "open ", "open up ", "launch ", "go to ", "bring up ", "load ",
            "take me to ", "navigate to ", "search for ", "search youtube", "search google"
        ].contains(where: { lower.contains($0) })

        let browserish = lower.contains("browser") || lower.contains("internet") || lower.contains("web tab") ||
            lower.contains("browser tab") || known.contains(where: { entry in entry.tokens.contains(where: { lower.contains($0) }) })

        let explicitPC = refersToPC(lower)
        let recentPC = hasRecentPCContext(lower)
        guard browserish && (explicitPC || recentPC) && (openish || known.contains(where: { entry in entry.tokens.contains(where: { lower.contains($0) }) })) else {
            return nil
        }

        if let hit = known.first(where: { entry in entry.tokens.contains(where: { lower.contains($0) }) }) {
            return BrowserIntent(action: "open_url", url: hit.url, label: hit.label)
        }

        if let direct = explicitURL(in: original) {
            return BrowserIntent(action: "open_url", url: direct, label: nil)
        }

        if lower.contains("browser") || lower.contains("internet") || lower.contains("web tab") {
            return BrowserIntent(action: "open_browser", url: nil, label: nil)
        }
        return nil
    }

    private static func refersToPC(_ lower: String) -> Bool {
        [
            " pc", "pc ", "computer", "machine", "downstairs", "upstairs", "kitchen",
            "ashley", "monte", "hp computer", "hp pc", "both computers", "both pcs"
        ].contains(where: { lower.contains($0) })
    }

    private static func hasRecentPCContext(_ lower: String) -> Bool {
        let lastAt = UserDefaults.standard.double(forKey: lastAtKey)
        guard lastAt > 0, Date().timeIntervalSince1970 - lastAt < 60 * 60 else { return false }
        let lastNode = (UserDefaults.standard.string(forKey: lastNodeKey) ?? "").lowercased()
        if !lastNode.isEmpty, lower.contains(lastNode) { return true }
        return lower.contains("that you just opened") || lower.contains("you just opened") ||
            lower.contains("that browser") || lower.contains("the browser") || lower.contains("there")
    }

    private static func candidateEndpoints(lower: String) -> [Endpoint] {
        let defaults = UserDefaults.standard
        let primary = defaults.string(forKey: WebBrain.searxEndpointKey)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let secondary = defaults.string(forKey: WebBrain.secondaryBridgeEndpointKey)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""

        var base: [Endpoint] = []
        if valid(primary) { base.append(Endpoint(value: primary, slot: "primary PC")) }
        if valid(secondary), secondary != primary { base.append(Endpoint(value: secondary, slot: "second PC")) }
        guard !base.isEmpty else { return [] }

        let downstairs = ["downstairs", "kitchen", "second pc", "second computer", "hp pc", "hp computer"]
            .contains(where: { lower.contains($0) })
        let upstairs = ["upstairs", "primary pc", "main pc", "monte pc", "monte computer"]
            .contains(where: { lower.contains($0) })

        let override: String?
        if downstairs {
            override = defaults.string(forKey: downstairsOverrideKey)
        } else if upstairs {
            override = defaults.string(forKey: upstairsOverrideKey)
        } else {
            let lastAt = defaults.double(forKey: lastAtKey)
            override = (lastAt > 0 && Date().timeIntervalSince1970 - lastAt < 60 * 60)
                ? defaults.string(forKey: lastEndpointKey)
                : nil
        }

        if let override, let index = base.firstIndex(where: { $0.value == override }) {
            let first = base.remove(at: index)
            base.insert(first, at: 0)
            return base
        }

        // Preserve the old convention as first guess, but always try the other
        // node for browser/site opens. If it succeeds, remember the real mapping.
        if downstairs, base.count > 1 {
            return [base[1], base[0]]
        }
        return base
    }

    private static func rememberSuccessful(endpoint: Endpoint, result: ToolReply, lower: String) {
        let defaults = UserDefaults.standard
        defaults.set(endpoint.value, forKey: lastEndpointKey)
        defaults.set(Date().timeIntervalSince1970, forKey: lastAtKey)
        if let node = clean(result.node_name) { defaults.set(node, forKey: lastNodeKey) }
        if lower.contains("downstairs") || lower.contains("kitchen") {
            defaults.set(endpoint.value, forKey: downstairsOverrideKey)
        }
        if lower.contains("upstairs") || lower.contains("main pc") || lower.contains("primary pc") {
            defaults.set(endpoint.value, forKey: upstairsOverrideKey)
        }
    }

    private static func fetchStatus(_ endpoint: String) async -> NodeStatus? {
        guard let url = endpointURL(endpoint, path: "/status") else { return nil }
        var request = URLRequest(url: url)
        request.timeoutInterval = 3.5
        do {
            let (data, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else { return nil }
            return try JSONDecoder().decode(NodeStatus.self, from: data)
        } catch {
            return nil
        }
    }

    private static func perform(action: String, url requestedURL: String?, endpoint: String) async -> ToolReply? {
        guard let url = endpointURL(endpoint, path: "/tools/action") else { return nil }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 8
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        var payload: [String: String] = ["action": action]
        if let requestedURL { payload["url"] = requestedURL }
        request.httpBody = try? JSONSerialization.data(withJSONObject: payload)
        do {
            let (data, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...499).contains(http.statusCode) else { return nil }
            return try JSONDecoder().decode(ToolReply.self, from: data)
        } catch {
            return nil
        }
    }

    private static func compileFallback(original: String, endpoint: String) async -> ToolReply? {
        guard let url = endpointURL(endpoint, path: "/skills/compile") else { return nil }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 14
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: ["request": original])
        do {
            let (data, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...499).contains(http.statusCode) else { return nil }
            return try JSONDecoder().decode(ToolReply.self, from: data)
        } catch {
            return nil
        }
    }

    private static func endpointURL(_ endpoint: String, path: String) -> URL? {
        guard let root = URL(string: endpoint), var parts = URLComponents(url: root, resolvingAgainstBaseURL: false) else { return nil }
        parts.path = path
        return parts.url
    }

    private static func explicitURL(in text: String) -> String? {
        for word in text.split(whereSeparator: { $0.isWhitespace }).map(String.init) {
            let clean = word.trimmingCharacters(in: CharacterSet(charactersIn: ",.;!?)\"]}"))
            if clean.lowercased().hasPrefix("https://") || clean.lowercased().hasPrefix("http://") {
                return clean
            }
        }
        return nil
    }

    private static func valid(_ endpoint: String) -> Bool {
        guard let url = URL(string: endpoint) else { return false }
        return VexBridgeNetworking.isBridgeURL(url)
    }

    private static func clean(_ value: String?) -> String? {
        let value = value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return value.isEmpty ? nil : value
    }

    private static func appendExchange(user: String, assistant: String, app: AppModel) {
        app.profile.messages.append(ChatMessage(role: .user, content: user))
        app.profile.messages.append(ChatMessage(role: .assistant, content: assistant))
        app.persist()
    }

    private static func normalize(_ text: String) -> String {
        text.lowercased().replacingOccurrences(of: "’", with: "'")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

// MARK: - Optional PC cognition overlay v0.9.3

@MainActor
private enum PCCognitionOverlay {
    private struct OverlayReply: Decodable {
        let ok: Bool
        let reply: String?
        let model: String?
    }

    static func tryHandle(_ original: String, app: AppModel) async -> Bool {
        guard shouldUse(original) else { return false }
        let endpoints = configuredEndpoints()
        guard !endpoints.isEmpty else { return false }

        let history = app.profile.messages.suffix(28).map { message -> [String: String] in
            ["role": message.role.rawValue, "content": String(message.content.prefix(5000))]
        }

        for endpoint in endpoints {
            guard let url = endpointURL(endpoint, path: "/llm/chat") else { continue }
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.timeoutInterval = 45
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            let body: [String: Any] = [
                "message": String(original.prefix(5000)),
                "history": history
            ]
            request.httpBody = try? JSONSerialization.data(withJSONObject: body)

            do {
                let (data, response) = try await VexBridgeNetworking.data(for: request)
                guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode),
                      let decoded = try? JSONDecoder().decode(OverlayReply.self, from: data),
                      decoded.ok, let reply = decoded.reply?.trimmingCharacters(in: .whitespacesAndNewlines),
                      !reply.isEmpty
                else { continue }

                app.draft = ""
                app.isGenerating = true
                defer { app.isGenerating = false }
                app.profile.messages.append(ChatMessage(role: .user, content: original))
                app.profile.messages.append(ChatMessage(role: .assistant, content: reply))
                app.persist()
                app.pcBrainConnected = true
                if let model = decoded.model, !model.isEmpty {
                    app.pcBrainStatus = "PC cognition • \(model)"
                }
                return true
            } catch {
                continue
            }
        }
        return false
    }

    private static func shouldUse(_ text: String) -> Bool {
        let lower = text.lowercased()
        // Existing native routes stay authoritative for tools, live research and visuals.
        let exclusions = [
            "search the web", "search online", "look up ", "latest", "current ", "today",
            "weather", "news", "http://", "https://", "take a photo", "take photo",
            "picture", " image", "camera", "open youtube", "open google", "open browser",
            "computer", " pc", "iphone", "phone", "volume", "pause", "next track", "playlist"
        ]
        return !exclusions.contains(where: { lower.contains($0) })
    }

    private static func configuredEndpoints() -> [String] {
        let defaults = UserDefaults.standard
        let primary = defaults.string(forKey: WebBrain.searxEndpointKey)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let secondary = defaults.string(forKey: WebBrain.secondaryBridgeEndpointKey)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let last = defaults.string(forKey: "vex.pc.smartBrowser.lastEndpoint.v1") ?? ""
        var values: [String] = []
        for endpoint in [last, primary, secondary] where !endpoint.isEmpty {
            if !values.contains(endpoint), URL(string: endpoint).map(VexBridgeNetworking.isBridgeURL) == true {
                values.append(endpoint)
            }
        }
        return values
    }

    private static func endpointURL(_ endpoint: String, path: String) -> URL? {
        guard let root = URL(string: endpoint), var parts = URLComponents(url: root, resolvingAgainstBaseURL: false) else { return nil }
        parts.path = path
        return parts.url
    }
}

'''
text = text.replace(marker, addition + marker, 1)
path.write_text(text, encoding="utf-8")

for marker in [
    "SmartPCBrowserRouter", "PCCognitionOverlay", "pc.smartBrowser.downstairsEndpoint",
    'path: "/llm/chat"', '"https://www.youtube.com"', "I understood the command"
]:
    if marker not in text:
        raise SystemExit(f"missing v0.9.3 iOS marker: {marker}")

print("Applied v0.9.3 contextual PC browser router + optional PC cognition overlay")
