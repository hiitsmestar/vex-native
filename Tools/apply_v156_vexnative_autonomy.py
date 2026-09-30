#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "VexNative" / "ContentView.swift"
MARKER = 'V156_VEXNATIVE_AUTONOMY = "v0.15.6-vexnative-autonomy-v1"'

text = CONTENT.read_text(encoding="utf-8")

if MARKER not in text:
    anchor = '@MainActor\nprivate final class VexControlSurfaceModel: ObservableObject {'
    if anchor not in text:
        raise SystemExit("v0.15.6 control-surface anchor missing")
    text = text.replace(anchor, 'private let ' + MARKER + '\n\n' + anchor, 1)

    props = '    @Published var error = ""'
    repl = '''    @Published var error = ""
    @Published var vexNativeOnline = false
    @Published var vexNativeAgentCount = 0
    @Published var autonomyEnabled = false
    @Published var autonomyRunning = false
    @Published var autonomyGoalSummary = "—"
    @Published var autonomyWorkSummary = "—"
    @Published var autonomyActionStatus = ""'''
    if props not in text:
        raise SystemExit("v0.15.6 property anchor missing")
    text = text.replace(props, repl, 1)

    reset = '''        runtimeOnline = false
        wants = []'''
    reset_new = '''        runtimeOnline = false
        vexNativeOnline = false
        wants = []'''
    if reset not in text:
        raise SystemExit("v0.15.6 reset anchor missing")
    text = text.replace(reset, reset_new, 1)

    before_refresh = '''            lastRefresh = Date()
            return'''
    native_refresh = '''            if let native = await json(endpoint: endpoint, path: "/vexnative/status"),
               (native["ok"] as? Bool) == true,
               let a2a = native["a2a"] as? [String: Any] {
                vexNativeOnline = true
                if let health = a2a["health"] as? [String: Any] {
                    vexNativeAgentCount = number(health["agent_count"])
                }
                if let runtime = a2a["runtime"] as? [String: Any] {
                    autonomyRunning = (runtime["running"] as? Bool) ?? false
                    if let store = runtime["store"] as? [String: Any] {
                        autonomyEnabled = (store["enabled"] as? Bool) ?? false
                        if let goals = store["goals"] as? [String: Any] {
                            autonomyGoalSummary = summary(goals)
                        }
                        if let work = store["work"] as? [String: Any] {
                            autonomyWorkSummary = summary(work)
                        }
                    }
                }
            }

            lastRefresh = Date()
            return'''
    if before_refresh not in text:
        raise SystemExit("v0.15.6 refresh anchor missing")
    text = text.replace(before_refresh, native_refresh, 1)

    json_anchor = '''        parts.path = path
        guard let url = parts.url else { return nil }'''
    json_new = '''        if path.hasPrefix("/vexnative/") { parts.port = 8771 }
        parts.path = path
        guard let url = parts.url else { return nil }'''
    if json_anchor not in text:
        raise SystemExit("v0.15.6 json route anchor missing")
    text = text.replace(json_anchor, json_new, 1)

    host_anchor = '''    private func hostLabel(_ endpoint: String) -> String {
        URL(string: endpoint)?.host ?? "Vex Bridge"
    }
}'''
    host_new = '''    func setAutonomy(enabled: Bool) async {
        guard let endpoint = configuredEndpoints().first else { return }
        autonomyActionStatus = enabled ? "Resuming…" : "Pausing…"
        let response = await postJSON(
            endpoint: endpoint,
            path: "/vexnative/autonomy",
            payload: ["action": enabled ? "enable" : "pause"]
        )
        autonomyActionStatus = (response?["ok"] as? Bool) == true ? "Done." : "VexNative action failed."
        await refresh()
    }

    func createGoal(title: String) async {
        let clean = title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty, let endpoint = configuredEndpoints().first else { return }
        autonomyActionStatus = "Sending goal…"
        let response = await postJSON(
            endpoint: endpoint,
            path: "/vexnative/autonomy",
            payload: ["action": "create_goal", "title": clean, "description": clean, "priority": 50]
        )
        autonomyActionStatus = (response?["ok"] as? Bool) == true ? "Goal accepted." : "Goal was not accepted."
        await refresh()
    }

    private func postJSON(endpoint: String, path: String, payload: [String: Any]) async -> [String: Any]? {
        guard let root = URL(string: endpoint),
              var parts = URLComponents(url: root, resolvingAgainstBaseURL: false)
        else { return nil }
        if path.hasPrefix("/vexnative/") { parts.port = 8771 }
        parts.path = path
        guard let url = parts.url else { return nil }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 12
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: payload)
        do {
            let (data, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse,
                  (200...299).contains(http.statusCode),
                  let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            else { return nil }
            return json
        } catch {
            return nil
        }
    }

    private func summary(_ values: [String: Any]) -> String {
        values.keys.sorted().compactMap { key in
            let count = number(values[key])
            return count > 0 ? "\(key) \(count)" : nil
        }.joined(separator: " • ")
    }

    private func hostLabel(_ endpoint: String) -> String {
        URL(string: endpoint)?.host ?? "Vex Bridge"
    }
}'''
    if host_anchor not in text:
        raise SystemExit("v0.15.6 model-method anchor missing")
    text = text.replace(host_anchor, host_new, 1)

    state_anchor = '''private struct VexSystemView: View {
    @EnvironmentObject private var app: AppModel
    @StateObject private var system = VexControlSurfaceModel()'''
    state_new = '''private struct VexSystemView: View {
    @EnvironmentObject private var app: AppModel
    @StateObject private var system = VexControlSurfaceModel()
    @State private var goalDraft = ""'''
    if state_anchor not in text:
        raise SystemExit("v0.15.6 system-state anchor missing")
    text = text.replace(state_anchor, state_new, 1)

    adaptive = '''                        VexMetricCard(
                            title: "Adaptive",'''
    native_card = '''                        VexMetricCard(
                            title: "VexNative",
                            value: system.vexNativeOnline ? (system.autonomyRunning ? "Autonomous" : "Online") : "Offline",
                            detail: system.vexNativeOnline ? "\(system.vexNativeAgentCount) agents • goals \(system.autonomyGoalSummary) • work \(system.autonomyWorkSummary)" : "Waiting for VexNative relay",
                            active: system.vexNativeOnline && system.autonomyEnabled
                        )
''' + adaptive
    if adaptive not in text:
        raise SystemExit("v0.15.6 metric anchor missing")
    text = text.replace(adaptive, native_card, 1)

    wants = '''                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            Text("Runtime wants")'''
    controls = '''                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Text("VexNative autonomy")
                                .font(.headline)
                            Spacer()
                            Text(system.autonomyEnabled ? "ENABLED" : "PAUSED")
                                .font(.caption2.bold())
                                .foregroundStyle(system.autonomyEnabled ? .green : .orange)
                        }
                        HStack {
                            Button("Resume") { Task { await system.setAutonomy(enabled: true) } }
                                .buttonStyle(.bordered)
                            Button("Pause") { Task { await system.setAutonomy(enabled: false) } }
                                .buttonStyle(.bordered)
                        }
                        TextField("Give VexNative a new goal", text: $goalDraft, axis: .vertical)
                            .textFieldStyle(.roundedBorder)
                        Button {
                            let value = goalDraft
                            goalDraft = ""
                            Task { await system.createGoal(title: value) }
                        } label: {
                            Label("Send goal to VexNative", systemImage: "paperplane.fill")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(VexTheme.hotPink)
                        .disabled(goalDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !system.vexNativeOnline)
                        if !system.autonomyActionStatus.isEmpty {
                            Text(system.autonomyActionStatus)
                                .font(.caption)
                                .foregroundStyle(VexTheme.muted)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(16)
                    .background(VexTheme.panel.opacity(0.94))
                    .clipShape(RoundedRectangle(cornerRadius: 18))

''' + wants
    if wants not in text:
        raise SystemExit("v0.15.6 controls anchor missing")
    text = text.replace(wants, controls, 1)

CONTENT.write_text(text, encoding="utf-8")

final = CONTENT.read_text(encoding="utf-8")
for marker in [
    MARKER,
    'parts.port = 8771',
    'path: "/vexnative/status"',
    'path: "/vexnative/autonomy"',
    "Send goal to VexNative",
    "setAutonomy(enabled:",
    "createGoal(title:",
    "autonomyGoalSummary",
]:
    if marker not in final:
        raise SystemExit(f"v0.15.6 marker missing: {marker}")

print("PASS v0.15.6 VexNative autonomy link patch")
