#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "VexNative" / "ContentView.swift"
BRIDGE = ROOT / "Bridge" / "vex_bridge.py"
MARKER = 'V136_VEXNATIVE_LINK = "v0.13.6-vexnative-link-v1"'

content = CONTENT.read_text(encoding="utf-8")
if MARKER not in content:
    anchor = "@MainActor\nprivate final class VexControlSurfaceModel: ObservableObject {"
    if anchor not in content:
        raise SystemExit("v0.13.6 control model anchor missing")
    content = content.replace(anchor, 'private let ' + MARKER + '\n\n' + anchor, 1)

    props = '    @Published var error = ""'
    replacement = '''    @Published var error = ""
    @Published var vexNativeOnline = false
    @Published var vexNativeAgentCount = 0
    @Published var autonomyEnabled = false
    @Published var autonomyRunning = false
    @Published var autonomyGoalSummary = "—"
    @Published var autonomyWorkSummary = "—"
    @Published var autonomyActionStatus = ""'''
    if props not in content:
        raise SystemExit("v0.13.6 property anchor missing")
    content = content.replace(props, replacement, 1)

    reset = '''        runtimeOnline = false
        wants = []'''
    reset_new = '''        runtimeOnline = false
        vexNativeOnline = false
        wants = []'''
    if reset not in content:
        raise SystemExit("v0.13.6 refresh reset anchor missing")
    content = content.replace(reset, reset_new, 1)

    before_refresh = '''            lastRefresh = Date()
            return'''
    native_refresh = '''            if let native = await json(endpoint: endpoint, path: "/vexnative/status"),
               (native["ok"] as? Bool) == true {
                vexNativeOnline = true
                if let health = native["health"] as? [String: Any] {
                    vexNativeAgentCount = number(health["agent_count"])
                }
                if let autonomy = native["autonomy"] as? [String: Any],
                   let runtime = autonomy["runtime"] as? [String: Any] {
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
    if before_refresh not in content:
        raise SystemExit("v0.13.6 refresh insertion anchor missing")
    content = content.replace(before_refresh, native_refresh, 1)

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
        parts.path = path
        guard let url = parts.url else { return nil }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 10
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
    if host_anchor not in content:
        raise SystemExit("v0.13.6 model-method anchor missing")
    content = content.replace(host_anchor, host_new, 1)

    system_state = '''private struct VexSystemView: View {
    @EnvironmentObject private var app: AppModel
    @StateObject private var system = VexControlSurfaceModel()'''
    system_state_new = '''private struct VexSystemView: View {
    @EnvironmentObject private var app: AppModel
    @StateObject private var system = VexControlSurfaceModel()
    @State private var goalDraft = ""'''
    if system_state not in content:
        raise SystemExit("v0.13.6 system view state anchor missing")
    content = content.replace(system_state, system_state_new, 1)

    adaptive_anchor = '''                        VexMetricCard(
                            title: "Adaptive",'''
    native_card = '''                        VexMetricCard(
                            title: "VexNative",
                            value: system.vexNativeOnline ? (system.autonomyRunning ? "Autonomous" : "Online") : "Offline",
                            detail: system.vexNativeOnline ? "\(system.vexNativeAgentCount) agents • goals \(system.autonomyGoalSummary) • work \(system.autonomyWorkSummary)" : "Waiting for VexNative proxy",
                            active: system.vexNativeOnline && system.autonomyEnabled
                        )
''' + adaptive_anchor
    if adaptive_anchor not in content:
        raise SystemExit("v0.13.6 metric anchor missing")
    content = content.replace(adaptive_anchor, native_card, 1)

    wants_anchor = '''                    VStack(alignment: .leading, spacing: 10) {
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
                    .padding(16)
                    .background(VexTheme.panel.opacity(0.94))
                    .clipShape(RoundedRectangle(cornerRadius: 18))

''' + wants_anchor
    if wants_anchor not in content:
        raise SystemExit("v0.13.6 controls anchor missing")
    content = content.replace(wants_anchor, controls, 1)

CONTENT.write_text(content, encoding="utf-8")

bridge = BRIDGE.read_text(encoding="utf-8")
if "V136_VEXNATIVE_PROXY" not in bridge:
    if "import urllib.request" not in bridge:
        bridge = bridge.replace("import urllib.parse\n", "import urllib.parse\nimport urllib.request\n", 1)

    handler_anchor = "class Handler(BaseHTTPRequestHandler):"
    helper = r'''
V136_VEXNATIVE_PROXY = "v0.13.6-vexnative-proxy-v1"
VEXNATIVE_LOCAL = "http://127.0.0.1:8796"

def _vexnative_local(path: str, method: str = "GET", payload: dict | None = None) -> dict:
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(VEXNATIVE_LOCAL + path, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=10) as response:
        raw = response.read(2_500_000)
    return json.loads(raw.decode("utf-8"))

'''
    if handler_anchor not in bridge:
        raise SystemExit("v0.13.6 Bridge handler anchor missing")
    bridge = bridge.replace(handler_anchor, helper + handler_anchor, 1)

    get_anchor = '''        if parsed.path == "/reindex":'''
    get_route = '''        if parsed.path == "/vexnative/status":
            try:
                health = _vexnative_local("/health")
                autonomy = _vexnative_local("/autonomy")
                self._json(200, {"ok": True, "health": health, "autonomy": autonomy})
            except Exception as exc:
                self._json(503, {"ok": False, "error": f"VexNative unavailable: {exc}"})
            return

''' + get_anchor
    if get_anchor not in bridge:
        raise SystemExit("v0.13.6 Bridge GET anchor missing")
    bridge = bridge.replace(get_anchor, get_route, 1)

    post_anchor = '''        if parsed.path == "/skills/compile":'''
    post_route = '''        if parsed.path == "/vexnative/autonomy":
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length <= 0 or length > 32_000:
                    self._json(413, {"ok": False, "error": "autonomy payload too large"})
                    return
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                action = str(payload.get("action") or "").strip().lower()
                if action not in {"enable", "pause", "create_goal", "goal_status"}:
                    self._json(400, {"ok": False, "error": "autonomy action not allowed from phone"})
                    return
                if action == "create_goal" and not str(payload.get("title") or "").strip():
                    self._json(400, {"ok": False, "error": "goal title required"})
                    return
                result = _vexnative_local("/autonomy", method="POST", payload=payload)
                self._json(200 if result.get("ok") else 400, result)
            except Exception as exc:
                self._json(503, {"ok": False, "error": f"VexNative action failed: {exc}"})
            return

''' + post_anchor
    if post_anchor not in bridge:
        raise SystemExit("v0.13.6 Bridge POST anchor missing")
    bridge = bridge.replace(post_anchor, post_route, 1)

BRIDGE.write_text(bridge, encoding="utf-8")

final_content = CONTENT.read_text(encoding="utf-8")
final_bridge = BRIDGE.read_text(encoding="utf-8")
for marker in [
    MARKER, "/vexnative/status", "/vexnative/autonomy",
    "Send goal to VexNative", "autonomyGoalSummary", "setAutonomy(enabled:"
]:
    if marker not in final_content:
        raise SystemExit(f"v0.13.6 app marker missing: {marker}")
for marker in [
    'V136_VEXNATIVE_PROXY = "v0.13.6-vexnative-proxy-v1"',
    'VEXNATIVE_LOCAL = "http://127.0.0.1:8796"',
    'parsed.path == "/vexnative/status"',
    'parsed.path == "/vexnative/autonomy"',
    '{"enable", "pause", "create_goal", "goal_status"}',
]:
    if marker not in final_bridge:
        raise SystemExit(f"v0.13.6 Bridge marker missing: {marker}")

print("PASS v0.13.6 VexNative phone link patch")
