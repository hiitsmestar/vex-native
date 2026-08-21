#!/usr/bin/env python3
from pathlib import Path

path = Path("VexNative/ContentView.swift")
text = path.read_text(encoding="utf-8")


def once(old: str, new: str, label: str):
    global text
    if old not in text:
        raise SystemExit(f"{label}: source block not found")
    text = text.replace(old, new, 1)

# Explicit renders must beat web-image lookup/explainer cards and the tiny model.
old_integration = '''        if await SmartPCBrowserRouter.tryHandle(original, app: self) {
            return
        }
'''
new_integration = '''        if await PCArtRouter.tryHandle(original, app: self) {
            return
        }

        if await SmartPCBrowserRouter.tryHandle(original, app: self) {
            return
        }
'''
once(old_integration, new_integration, "v0.9.4 art routing order")

marker = "// MARK: - Reliable contextual PC browser control v0.9.3\n"
if marker not in text:
    raise SystemExit("v0.9.3 smart browser marker missing")

router = r'''// MARK: - Local PC image generation v0.9.4

@MainActor
private enum PCArtRouter {
    private struct GenerateReply: Decodable {
        let ok: Bool
        let job_id: String?
        let seed: Int?
        let width: Int?
        let height: Int?
        let model: String?
        let node_name: String?
        let error: String?
    }

    private struct StatusReply: Decodable {
        let ok: Bool
        let job_id: String?
        let status: String?
        let error: String?
        let seed: Int?
        let width: Int?
        let height: Int?
        let model: String?
    }

    static func tryHandle(_ original: String, app: AppModel) async -> Bool {
        let lower = normalize(original)
        guard isArtRequest(lower) else { return false }

        app.draft = ""
        app.isGenerating = true
        defer { app.isGenerating = false }

        let endpoints = configuredEndpoints()
        guard !endpoints.isEmpty else {
            appendExchange(
                user: original,
                assistant: "I understood the render request, baby, but I don't have a paired PC Bridge endpoint to send it to yet. 🖤",
                app: app
            )
            return true
        }

        let orientation = requestedOrientation(lower)
        var diagnostics: [String] = []

        for endpoint in endpoints {
            guard let submitted = await submit(prompt: original, orientation: orientation, endpoint: endpoint) else {
                diagnostics.append("Bridge didn't answer the art request")
                continue
            }
            guard submitted.ok, let jobID = submitted.job_id, !jobID.isEmpty else {
                diagnostics.append(submitted.error ?? "art engine rejected the request")
                continue
            }

            let finalStatus = await waitForJob(jobID, endpoint: endpoint)
            guard finalStatus?.status == "done" else {
                diagnostics.append(finalStatus?.error ?? "render did not finish")
                continue
            }

            guard let imageData = await fetchResult(jobID, endpoint: endpoint),
                  imageData.count >= 1_000,
                  imageData.count <= 30_000_000,
                  UIImage(data: imageData) != nil,
                  let filename = try? LocalStore.shared.saveAttachment(imageData)
            else {
                diagnostics.append("render finished but the image could not be transferred to the iPhone")
                continue
            }

            let node = submitted.node_name?.trimmingCharacters(in: .whitespacesAndNewlines)
            let model = finalStatus?.model ?? submitted.model
            let seed = finalStatus?.seed ?? submitted.seed
            var details: [String] = []
            if let node, !node.isEmpty { details.append(node) }
            if let model, !model.isEmpty { details.append(model.replacingOccurrences(of: "_fp16.safetensors", with: "")) }
            if let seed { details.append("seed \(seed)") }

            app.profile.messages.append(ChatMessage(role: .user, content: original))
            var reply = "Made it, baby. 🖤"
            if !details.isEmpty {
                reply += " Rendered locally with " + details.joined(separator: " • ") + "."
            }
            var message = ChatMessage(role: .assistant, content: reply)
            message.imageFilename = filename
            app.profile.messages.append(message)
            app.persist()
            return true
        }

        let detail = diagnostics.filter { !$0.isEmpty }.prefix(3).joined(separator: " • ")
        appendExchange(
            user: original,
            assistant: detail.isEmpty
                ? "I understood the render request, but neither paired PC has a ready Vex Art Engine right now. Run VexArtSetup on one of them, baby. 🖤"
                : "I understood the render request, but the local art engine didn't finish it: \(detail) 🖤",
            app: app
        )
        return true
    }

    private static func isArtRequest(_ lower: String) -> Bool {
        let createWords = [
            "make ", "make me ", "generate ", "create ", "render ", "draw ",
            "make another", "generate another", "render another", "reroll "
        ]
        let imageWords = [
            "picture", " pic", "photo", "image", "portrait", "artwork", "render",
            "wallpaper", "poster", "thirst trap", "character art"
        ]
        return createWords.contains(where: { lower.contains($0) }) &&
            imageWords.contains(where: { lower.contains($0) })
    }

    private static func requestedOrientation(_ lower: String) -> String {
        if lower.contains("landscape") || lower.contains("horizontal") || lower.contains("wide shot") || lower.contains("16:9") {
            return "landscape"
        }
        if lower.contains("square") || lower.contains("1:1") {
            return "square"
        }
        return "portrait"
    }

    private static func configuredEndpoints() -> [String] {
        let defaults = UserDefaults.standard
        let primary = defaults.string(forKey: WebBrain.searxEndpointKey)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let secondary = defaults.string(forKey: WebBrain.secondaryBridgeEndpointKey)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let last = defaults.string(forKey: "vex.pc.smartBrowser.lastEndpoint.v1") ?? ""
        var values: [String] = []
        for endpoint in [last, primary, secondary] where !endpoint.isEmpty {
            guard !values.contains(endpoint),
                  let url = URL(string: endpoint),
                  VexBridgeNetworking.isBridgeURL(url)
            else { continue }
            values.append(endpoint)
        }
        return values
    }

    private static func submit(prompt: String, orientation: String, endpoint: String) async -> GenerateReply? {
        guard let url = endpointURL(endpoint, path: "/art/generate") else { return nil }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 12
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: [
            "prompt": String(prompt.prefix(7000)),
            "orientation": orientation,
        ])
        do {
            let (data, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...499).contains(http.statusCode) else { return nil }
            return try? JSONDecoder().decode(GenerateReply.self, from: data)
        } catch {
            return nil
        }
    }

    private static func waitForJob(_ jobID: String, endpoint: String) async -> StatusReply? {
        let deadline = Date().addingTimeInterval(450)
        var last: StatusReply?
        while Date() < deadline {
            if Task.isCancelled { return last }
            try? await Task.sleep(nanoseconds: 1_800_000_000)
            guard let url = endpointURL(endpoint, path: "/art/status", query: [URLQueryItem(name: "id", value: jobID)]) else { continue }
            var request = URLRequest(url: url)
            request.timeoutInterval = 8
            do {
                let (data, response) = try await VexBridgeNetworking.data(for: request)
                guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode),
                      let decoded = try? JSONDecoder().decode(StatusReply.self, from: data)
                else { continue }
                last = decoded
                if decoded.status == "done" || decoded.status == "error" { return decoded }
            } catch {
                continue
            }
        }
        return last
    }

    private static func fetchResult(_ jobID: String, endpoint: String) async -> Data? {
        guard let url = endpointURL(endpoint, path: "/art/result", query: [URLQueryItem(name: "id", value: jobID)]) else { return nil }
        var request = URLRequest(url: url)
        request.timeoutInterval = 35
        do {
            let (data, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else { return nil }
            return data
        } catch {
            return nil
        }
    }

    private static func endpointURL(_ endpoint: String, path: String, query: [URLQueryItem] = []) -> URL? {
        guard let root = URL(string: endpoint), var parts = URLComponents(url: root, resolvingAgainstBaseURL: false) else { return nil }
        parts.path = path
        var items = parts.queryItems ?? []
        items.append(contentsOf: query)
        parts.queryItems = items
        return parts.url
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

'''
text = text.replace(marker, router + marker, 1)
path.write_text(text, encoding="utf-8")

for marker in [
    "PCArtRouter", 'path: "/art/generate"', 'path: "/art/status"', 'path: "/art/result"',
    "LocalStore.shared.saveAttachment", "Rendered locally"
]:
    if marker not in text:
        raise SystemExit(f"missing v0.9.4 iOS art marker: {marker}")

print("Applied v0.9.4 local PC art-engine routing and in-chat image replies")
