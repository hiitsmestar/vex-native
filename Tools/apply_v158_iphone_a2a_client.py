#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "VexNative" / "ContentView.swift"
MARKER = 'V158_IPHONE_A2A_CLIENT = "v0.15.8-iphone-a2a-client-v1"'

SWIFT = r'''

// MARK: - VexNative v0.15.8 current A2A client

private let V158_IPHONE_A2A_CLIENT = "v0.15.8-iphone-a2a-client-v1"

@MainActor
private final class VexNativeA2AClient: ObservableObject {
    @Published var online = false
    @Published var agentCount = 0
    @Published var autonomyEnabled = false
    @Published var autonomyRunning = false
    @Published var goalSummary = "—"
    @Published var workSummary = "—"
    @Published var latestGoal = "No system initiative yet"
    @Published var response = ""
    @Published var error = ""
    @Published var refreshing = false
    @Published var sending = false
    @Published var lastRefresh: Date?

    func refresh() async {
        guard !refreshing else { return }
        refreshing = true
        defer { refreshing = false }

        do {
            let object = try await request(path: "/vexnative/status")
            guard (object["ok"] as? Bool) == true,
                  let a2a = object["a2a"] as? [String: Any]
            else { throw ClientError.badResponse }

            let health = a2a["health"] as? [String: Any] ?? [:]
            let runtime = a2a["runtime"] as? [String: Any] ?? [:]
            let store = runtime["store"] as? [String: Any] ?? [:]
            let goals = a2a["goals"] as? [[String: Any]] ?? []
            let work = a2a["work"] as? [[String: Any]] ?? []

            online = (health["ok"] as? Bool) ?? false
            agentCount = number(health["agent_count"])
            autonomyEnabled = (store["enabled"] as? Bool) ?? false
            autonomyRunning = (runtime["running"] as? Bool) ?? false
            goalSummary = statusSummary(store["goals"])
            workSummary = statusSummary(store["work"])

            if let newest = goals.first {
                let title = (newest["title"] as? String) ?? "Untitled goal"
                let status = (newest["status"] as? String) ?? "unknown"
                latestGoal = "\(title) • \(status)"
            } else {
                latestGoal = "No goals reported"
            }
            error = ""
            lastRefresh = Date()
        } catch {
            online = false
            self.error = "VexNative status: \(error.localizedDescription)"
        }
    }

    func send(_ message: String) async {
        let clean = message.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty, !sending else { return }
        sending = true
        defer { sending = false }

        do {
            let object = try await request(
                path: "/vexnative/send",
                method: "POST",
                body: ["agent": "coordinator", "message": clean],
                timeout: 75
            )
            guard (object["ok"] as? Bool) == true else { throw ClientError.badResponse }
            response = extractText(object["result"]) ?? compactJSON(object["result"]) ?? "VexNative completed the request."
            error = ""
            await refresh()
        } catch {
            self.error = "VexNative request: \(error.localizedDescription)"
        }
    }

    private enum ClientError: LocalizedError {
        case noRelay
        case badResponse
        case http(Int)

        var errorDescription: String? {
            switch self {
            case .noRelay: return "No paired Vex relay endpoint is configured."
            case .badResponse: return "The VexNative relay returned an invalid response."
            case .http(let code): return "The VexNative relay returned HTTP \(code)."
            }
        }
    }

    private func relayURL(path: String) -> URL? {
        let defaults = UserDefaults.standard
        let candidates = [
            defaults.string(forKey: WebBrain.searxEndpointKey) ?? "",
            defaults.string(forKey: "vex.pc.cognition.lastGoodEndpoint.v1") ?? "",
            defaults.string(forKey: WebBrain.secondaryBridgeEndpointKey) ?? ""
        ]
        for raw in candidates {
            let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty,
                  let root = URL(string: trimmed),
                  VexBridgeNetworking.isBridgeURL(root),
                  var parts = URLComponents(url: root, resolvingAgainstBaseURL: false)
            else { continue }
            parts.port = 8771
            parts.path = path
            return parts.url
        }
        return nil
    }

    private func request(
        path: String,
        method: String = "GET",
        body: [String: Any]? = nil,
        timeout: TimeInterval = 20
    ) async throws -> [String: Any] {
        guard let url = relayURL(path: path) else { throw ClientError.noRelay }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = timeout
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let body {
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let (data, response) = try await VexBridgeNetworking.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw ClientError.badResponse }
        guard (200...299).contains(http.statusCode) else { throw ClientError.http(http.statusCode) }
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw ClientError.badResponse
        }
        return object
    }

    private func number(_ value: Any?) -> Int {
        if let n = value as? Int { return n }
        if let n = value as? NSNumber { return n.intValue }
        if let s = value as? String { return Int(s) ?? 0 }
        return 0
    }

    private func statusSummary(_ value: Any?) -> String {
        guard let dict = value as? [String: Any], !dict.isEmpty else { return "0" }
        let ordered = dict.keys.sorted().compactMap { key -> String? in
            let count = number(dict[key])
            return count > 0 ? "\(count) \(key)" : nil
        }
        return ordered.isEmpty ? "0" : ordered.joined(separator: " • ")
    }

    private func extractText(_ value: Any?) -> String? {
        if let text = value as? String, !text.isEmpty { return text }
        guard let dict = value as? [String: Any] else { return nil }
        for key in ["response", "answer", "text", "message", "output", "result"] {
            if let text = extractText(dict[key]), !text.isEmpty { return text }
        }
        return nil
    }

    private func compactJSON(_ value: Any?) -> String? {
        guard let value, JSONSerialization.isValidJSONObject(value),
              let data = try? JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted]),
              let text = String(data: data, encoding: .utf8)
        else { return nil }
        return String(text.prefix(4000))
    }
}

private struct VexNativeA2APanel: View {
    @StateObject private var client = VexNativeA2AClient()
    @State private var prompt = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text("VexNative Core")
                        .font(.headline)
                    Text("Current A2A / autonomy • paired through Vex relay")
                        .font(.caption)
                        .foregroundStyle(VexTheme.muted)
                }
                Spacer()
                Circle()
                    .fill(client.online ? Color.green : Color.orange)
                    .frame(width: 9, height: 9)
            }

            HStack(spacing: 12) {
                VexMetricCard(
                    title: "A2A",
                    value: client.online ? "Online" : "Offline",
                    detail: client.online ? "\(client.agentCount) agents" : "Refresh to reconnect",
                    active: client.online
                )
                VexMetricCard(
                    title: "Autonomy",
                    value: client.autonomyEnabled ? (client.autonomyRunning ? "Running" : "Enabled") : "Paused",
                    detail: "Goals \(client.goalSummary)\nWork \(client.workSummary)",
                    active: client.autonomyEnabled
                )
            }

            VStack(alignment: .leading, spacing: 5) {
                Text("Latest goal")
                    .font(.caption.bold())
                    .foregroundStyle(VexTheme.hotPink)
                Text(client.latestGoal)
                    .font(.subheadline)
                    .foregroundStyle(.white.opacity(0.94))
            }

            TextField("Ask current VexNative…", text: $prompt, axis: .vertical)
                .textFieldStyle(.roundedBorder)

            HStack {
                Button {
                    Task { await client.refresh() }
                } label: {
                    Label(client.refreshing ? "Refreshing…" : "Refresh", systemImage: "arrow.clockwise")
                }
                .buttonStyle(.bordered)
                .disabled(client.refreshing)

                Button {
                    let message = prompt
                    prompt = ""
                    Task { await client.send(message) }
                } label: {
                    Label(client.sending ? "Sending…" : "Send to VexNative", systemImage: "paperplane.fill")
                }
                .buttonStyle(.borderedProminent)
                .tint(VexTheme.hotPink)
                .disabled(client.sending || prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }

            if !client.response.isEmpty {
                Text(client.response)
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.9))
                    .textSelection(.enabled)
            }
            if !client.error.isEmpty {
                Text(client.error)
                    .font(.caption)
                    .foregroundStyle(.orange)
            }
            if let refreshed = client.lastRefresh {
                Text("Core refreshed \(refreshed.formatted(date: .omitted, time: .standard))")
                    .font(.caption2)
                    .foregroundStyle(VexTheme.muted)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(VexTheme.panel.opacity(0.94))
        .clipShape(RoundedRectangle(cornerRadius: 18))
        .task { await client.refresh() }
    }
}
'''

def main() -> None:
    text = CONTENT.read_text(encoding="utf-8")
    if MARKER in text:
        print("PASS v0.15.8 iPhone A2A client already applied")
        return

    anchor = "                    if !system.error.isEmpty {"
    if anchor not in text:
        raise SystemExit("v0.15.8 System-view insertion anchor missing")
    text = text.replace(anchor, "                    VexNativeA2APanel()\n\n" + anchor, 1)
    text += SWIFT
    CONTENT.write_text(text, encoding="utf-8")

    final = CONTENT.read_text(encoding="utf-8")
    for marker in [
        MARKER,
        "VexNativeA2APanel()",
        'path: "/vexnative/status"',
        'path: "/vexnative/send"',
        '"agent": "coordinator"',
        "parts.port = 8771",
        "PhoneRemoteCommandRelay.shared.run(app: app)",
        "LOCAL DIRECT MODE — V155_LOCAL_DIRECT_BRAIN",
    ]:
        if marker not in final:
            raise SystemExit(f"missing v0.15.8 marker: {marker}")

    print("PASS v0.15.8 current VexNative A2A client patch")

if __name__ == "__main__":
    main()
