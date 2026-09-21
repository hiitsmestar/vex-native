from __future__ import annotations
from pathlib import Path
import shutil, sys

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "VexNative" / "ContentView.swift"

MARKER = 'V130_CONTROL_SURFACE = "v0.13.0-control-surface-v1"'

SHELL = r'''

// MARK: - VexNative v0.13.0 control surface

private let V130_CONTROL_SURFACE = "v0.13.0-control-surface-v1"

private enum VexMainTab: Hashable {
    case chat
    case system
    case art
    case memory
    case phone
}

struct ContentView: View {
    @EnvironmentObject private var app: AppModel
    @State private var tab: VexMainTab = .chat

    var body: some View {
        TabView(selection: $tab) {
            VexChatView()
                .tag(VexMainTab.chat)
                .tabItem { Label("Chat", systemImage: "bubble.left.and.bubble.right.fill") }

            VexSystemView()
                .tag(VexMainTab.system)
                .tabItem { Label("System", systemImage: "network") }

            VexArtStudioView(onOpenChat: { tab = .chat })
                .tag(VexMainTab.art)
                .tabItem { Label("Art", systemImage: "sparkles.rectangle.stack") }

            VexMemoryView()
                .tag(VexMainTab.memory)
                .tabItem { Label("Memory", systemImage: "brain.head.profile") }

            VexPhoneView(onOpenChat: { tab = .chat })
                .tag(VexMainTab.phone)
                .tabItem { Label("Phone", systemImage: "iphone") }
        }
        .tint(VexTheme.hotPink)
        .toolbarBackground(VexTheme.ink.opacity(0.97), for: .tabBar)
        .toolbarBackground(.visible, for: .tabBar)
    }
}

@MainActor
private final class VexControlSurfaceModel: ObservableObject {
    @Published var runtimeOnline = false
    @Published var nodeName = "Not connected"
    @Published var bridgeVersion = "—"
    @Published var runtimeBundle = "—"
    @Published var indexedFiles = 0
    @Published var adaptiveLessons = 0
    @Published var openGaps = 0
    @Published var stagedUpgrades = 0
    @Published var wants: [String] = []
    @Published var artInstalled = false
    @Published var artRunning = false
    @Published var artModel = "—"
    @Published var isRefreshing = false
    @Published var lastRefresh: Date?
    @Published var error = ""

    func refresh() async {
        guard !isRefreshing else { return }
        isRefreshing = true
        defer { isRefreshing = false }

        error = ""
        runtimeOnline = false
        wants = []

        let endpoints = configuredEndpoints()
        guard !endpoints.isEmpty else {
            error = "No paired Vex Bridge endpoint is configured."
            return
        }

        for endpoint in endpoints {
            guard let status = await json(endpoint: endpoint, path: "/status") else { continue }

            runtimeOnline = true
            nodeName = (status["name"] as? String) ?? hostLabel(endpoint)
            bridgeVersion = (status["version"] as? String) ?? "unknown"
            runtimeBundle = (status["agent_runtime_bundle"] as? String) ?? "unknown"
            indexedFiles = number(status["indexed_files"])

            if let adaptive = await json(endpoint: endpoint, path: "/adaptive/status") {
                adaptiveLessons = number(adaptive["active_lessons"])
                openGaps = number(adaptive["open_gaps"])
                stagedUpgrades = number(adaptive["staged_upgrades"])
            }

            if let autonomy = await json(endpoint: endpoint, path: "/autonomy/requests") {
                if let counts = autonomy["counts"] as? [String: Any] {
                    openGaps = number(counts["open_gaps"])
                    stagedUpgrades = number(counts["staged_upgrades"])
                }

                var current: [String] = []
                if let gaps = autonomy["gaps"] as? [[String: Any]] {
                    for gap in gaps.prefix(8) {
                        let detail = (gap["detail"] as? String) ?? (gap["request_text"] as? String) ?? "Open capability gap"
                        current.append("Gap: " + detail)
                    }
                }
                if let upgrades = autonomy["upgrades"] as? [[String: Any]] {
                    for upgrade in upgrades.prefix(8) {
                        let component = (upgrade["component"] as? String) ?? "runtime"
                        let proposal = (upgrade["proposal"] as? String) ?? (upgrade["problem"] as? String) ?? "Staged upgrade"
                        current.append("\(component): \(proposal)")
                    }
                }
                wants = current
            }

            if let art = await json(endpoint: endpoint, path: "/art/health") {
                artInstalled = (art["installed"] as? Bool) ?? false
                artRunning = (art["running"] as? Bool) ?? false
                artModel = (art["model"] as? String) ?? "—"
            }

            lastRefresh = Date()
            return
        }

        error = "Configured Vex Bridge nodes did not answer."
    }

    private func configuredEndpoints() -> [String] {
        let defaults = UserDefaults.standard
        let primary = defaults.string(forKey: WebBrain.searxEndpointKey)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let secondary = defaults.string(forKey: WebBrain.secondaryBridgeEndpointKey)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let cognition = defaults.string(forKey: "vex.pc.cognition.lastGoodEndpoint.v1") ?? ""
        var result: [String] = []
        for value in [primary, cognition, secondary] where !value.isEmpty {
            guard !result.contains(value), let url = URL(string: value), VexBridgeNetworking.isBridgeURL(url) else { continue }
            result.append(value)
        }
        return result
    }

    private func json(endpoint: String, path: String) async -> [String: Any]? {
        guard let root = URL(string: endpoint),
              var parts = URLComponents(url: root, resolvingAgainstBaseURL: false)
        else { return nil }

        parts.path = path
        guard let url = parts.url else { return nil }

        var request = URLRequest(url: url)
        request.timeoutInterval = 7

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

    private func number(_ value: Any?) -> Int {
        if let n = value as? Int { return n }
        if let n = value as? NSNumber { return n.intValue }
        if let text = value as? String, let n = Int(text) { return n }
        return 0
    }

    private func hostLabel(_ endpoint: String) -> String {
        URL(string: endpoint)?.host ?? "Vex Bridge"
    }
}

private struct VexSurfaceBackground: View {
    var body: some View {
        LinearGradient(
            colors: [
                VexTheme.ink,
                Color(red: 0.12, green: 0.045, blue: 0.14),
                VexTheme.ink
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
        .ignoresSafeArea()
    }
}

private struct VexSurfaceHeader: View {
    let eyebrow: String
    let title: String
    let subtitle: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(eyebrow.uppercased())
                .font(.caption2.weight(.black))
                .tracking(1.5)
                .foregroundStyle(VexTheme.hotPink)
            Text(title)
                .font(.largeTitle.bold())
            Text(subtitle)
                .font(.subheadline)
                .foregroundStyle(VexTheme.muted)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct VexMetricCard: View {
    let title: String
    let value: String
    let detail: String
    var active = true

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Circle()
                    .fill(active ? VexTheme.hotPink : VexTheme.muted.opacity(0.45))
                    .frame(width: 7, height: 7)
                Text(title.uppercased())
                    .font(.caption2.weight(.bold))
                    .tracking(0.8)
                    .foregroundStyle(VexTheme.muted)
            }
            Text(value)
                .font(.title3.bold())
                .lineLimit(2)
                .minimumScaleFactor(0.75)
            Text(detail)
                .font(.caption)
                .foregroundStyle(VexTheme.muted)
                .lineLimit(3)
        }
        .frame(maxWidth: .infinity, minHeight: 108, alignment: .topLeading)
        .padding(14)
        .background(VexTheme.panel.opacity(0.94))
        .overlay(
            RoundedRectangle(cornerRadius: 18)
                .stroke(.white.opacity(0.07), lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: 18))
    }
}

private struct VexSystemView: View {
    @EnvironmentObject private var app: AppModel
    @StateObject private var system = VexControlSurfaceModel()

    var body: some View {
        ZStack {
            VexSurfaceBackground()
            ScrollView {
                VStack(spacing: 16) {
                    HStack(alignment: .top) {
                        VexSurfaceHeader(
                            eyebrow: "VEXNATIVE // CONTROL SURFACE",
                            title: "System",
                            subtitle: "Live state from the phone, paired PCs, adaptive memory, wants, and art worker."
                        )
                        Button {
                            app.showBrain = true
                        } label: {
                            Image(systemName: "slider.horizontal.3")
                                .font(.headline)
                                .padding(12)
                                .background(.white.opacity(0.08))
                                .clipShape(Circle())
                        }
                        .tint(.white)
                    }

                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                        VexMetricCard(
                            title: "PC cognition",
                            value: app.pcBrainConnected ? "Connected" : "Standby",
                            detail: app.pcBrainStatus,
                            active: app.pcBrainConnected
                        )
                        VexMetricCard(
                            title: "Bridge",
                            value: system.runtimeOnline ? system.bridgeVersion : "Offline",
                            detail: system.runtimeOnline ? "\(system.nodeName) • runtime \(system.runtimeBundle)" : "No Bridge response",
                            active: system.runtimeOnline
                        )
                        VexMetricCard(
                            title: "Adaptive",
                            value: "\(system.adaptiveLessons) lessons",
                            detail: "\(system.openGaps) open gaps • \(system.stagedUpgrades) staged upgrade\(system.stagedUpgrades == 1 ? "" : "s")",
                            active: system.runtimeOnline && system.openGaps == 0
                        )
                        VexMetricCard(
                            title: "Art",
                            value: system.artInstalled ? (system.artRunning ? "Rendering" : "Ready") : "Unavailable",
                            detail: system.artInstalled ? system.artModel : "Art worker not installed",
                            active: system.artInstalled
                        )
                        VexMetricCard(
                            title: "Index",
                            value: system.indexedFiles == 0 ? "—" : "\(system.indexedFiles)",
                            detail: "Indexed PC files available to Vex Bridge",
                            active: system.indexedFiles > 0
                        )
                        VexMetricCard(
                            title: "Phone brain",
                            value: app.modelStatus,
                            detail: app.isLoadingModel ? "Loading local fallback model" : "Local fallback remains independent of PC cognition",
                            active: !app.isLoadingModel
                        )
                    }

                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            Text("Runtime wants")
                                .font(.headline)
                            Spacer()
                            Text("\(system.wants.count)")
                                .font(.caption.bold())
                                .foregroundStyle(VexTheme.hotPink)
                        }

                        if system.wants.isEmpty {
                            Text(system.runtimeOnline ? "No open gaps. Staged upgrades appear here when Vex has something concrete to improve." : "Refresh to read Vex runtime wants.")
                                .font(.subheadline)
                                .foregroundStyle(VexTheme.muted)
                        } else {
                            ForEach(Array(system.wants.enumerated()), id: \.offset) { _, item in
                                Text("• " + item)
                                    .font(.subheadline)
                                    .foregroundStyle(.white.opacity(0.92))
                            }
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(16)
                    .background(VexTheme.panel.opacity(0.94))
                    .clipShape(RoundedRectangle(cornerRadius: 18))

                    if !system.error.isEmpty {
                        Text(system.error)
                            .font(.caption)
                            .foregroundStyle(.orange)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    Button {
                        Task { await system.refresh() }
                    } label: {
                        HStack {
                            if system.isRefreshing { ProgressView().tint(.white) }
                            Image(systemName: "arrow.clockwise")
                            Text(system.isRefreshing ? "Refreshing…" : "Refresh system")
                                .fontWeight(.bold)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 13)
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(VexTheme.hotPink)
                    .disabled(system.isRefreshing)

                    if let refreshed = system.lastRefresh {
                        Text("Last refresh \(refreshed.formatted(date: .omitted, time: .standard))")
                            .font(.caption2)
                            .foregroundStyle(VexTheme.muted)
                    }
                }
                .padding(16)
            }
        }
        .sheet(isPresented: $app.showBrain) {
            BrainView()
                .environmentObject(app)
        }
        .task { await system.refresh() }
    }
}

private struct VexArtStudioView: View {
    @EnvironmentObject private var app: AppModel
    let onOpenChat: () -> Void
    @State private var prompt = ""
    @State private var rendering = false

    private var latestImage: UIImage? {
        guard let filename = app.profile.messages.reversed().compactMap(\.imageFilename).first,
              let data = LocalStore.shared.attachmentData(named: filename)
        else { return nil }
        return UIImage(data: data)
    }

    var body: some View {
        ZStack {
            VexSurfaceBackground()
            ScrollView {
                VStack(spacing: 16) {
                    VexSurfaceHeader(
                        eyebrow: "VEXART // LOCAL PIPELINE",
                        title: "Art",
                        subtitle: "Render through the PC Art Worker. Finished images still land in Vex chat history."
                    )

                    if let image = latestImage {
                        Image(uiImage: image)
                            .resizable()
                            .scaledToFit()
                            .frame(maxWidth: .infinity)
                            .clipShape(RoundedRectangle(cornerRadius: 20))
                            .overlay(
                                RoundedRectangle(cornerRadius: 20)
                                    .stroke(.white.opacity(0.08), lineWidth: 1)
                            )
                    } else {
                        VStack(spacing: 10) {
                            Image(systemName: "sparkles.rectangle.stack")
                                .font(.system(size: 42))
                                .foregroundStyle(VexTheme.hotPink)
                            Text("Your latest local render will appear here.")
                                .foregroundStyle(VexTheme.muted)
                        }
                        .frame(maxWidth: .infinity, minHeight: 220)
                        .background(VexTheme.panel.opacity(0.9))
                        .clipShape(RoundedRectangle(cornerRadius: 20))
                    }

                    VStack(alignment: .leading, spacing: 10) {
                        Text("Render prompt")
                            .font(.headline)
                        TextEditor(text: $prompt)
                            .frame(minHeight: 120)
                            .scrollContentBackground(.hidden)
                            .padding(10)
                            .background(.black.opacity(0.22))
                            .clipShape(RoundedRectangle(cornerRadius: 14))

                        HStack {
                            Button("Open chat") { onOpenChat() }
                                .buttonStyle(.bordered)

                            Spacer()

                            Button {
                                let request = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
                                guard !request.isEmpty, !rendering else { return }
                                rendering = true
                                Task {
                                    _ = await PCArtRouter.tryHandle("render image: " + request, app: app)
                                    rendering = false
                                }
                            } label: {
                                HStack {
                                    if rendering { ProgressView().tint(.white) }
                                    Image(systemName: "wand.and.stars")
                                    Text(rendering ? "Rendering…" : "Render")
                                }
                                .fontWeight(.bold)
                            }
                            .buttonStyle(.borderedProminent)
                            .tint(VexTheme.hotPink)
                            .disabled(prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || rendering)
                        }
                    }
                    .padding(16)
                    .background(VexTheme.panel.opacity(0.94))
                    .clipShape(RoundedRectangle(cornerRadius: 18))

                    Text("VexArt v0.10.12 field flow: render → release Comfy → Q6 visual review → at most one corrected rerender.")
                        .font(.caption)
                        .foregroundStyle(VexTheme.muted)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .padding(16)
            }
        }
    }
}

private struct VexMemoryCount: Identifiable {
    let kind: MemoryKind
    let count: Int
    var id: String { kind.rawValue }
}

private struct VexMemoryView: View {
    @EnvironmentObject private var app: AppModel

    private var counts: [VexMemoryCount] {
        let grouped = Dictionary(grouping: app.profile.memories, by: \.kind)
        return MemoryKind.allCases.map { VexMemoryCount(kind: $0, count: grouped[$0]?.count ?? 0) }
    }

    private var recent: [BrainMemory] {
        Array(app.profile.memories.sorted {
            if $0.importance == $1.importance { return $0.createdAt > $1.createdAt }
            return $0.importance > $1.importance
        }.prefix(24))
    }

    var body: some View {
        ZStack {
            VexSurfaceBackground()
            ScrollView {
                VStack(spacing: 16) {
                    VexSurfaceHeader(
                        eyebrow: "VEX MEMORY // PHONE + PC",
                        title: "Memory",
                        subtitle: "Phone profile memory stays local; Bridge memory and adaptive lessons stay on the paired PC."
                    )

                    HStack(spacing: 12) {
                        VexMetricCard(
                            title: "Phone memories",
                            value: "\(app.profile.memories.count)",
                            detail: "Persistent app-local memories",
                            active: true
                        )
                        VexMetricCard(
                            title: "Messages",
                            value: "\(app.profile.messages.count)",
                            detail: "Current on-device transcript",
                            active: true
                        )
                    }

                    VStack(alignment: .leading, spacing: 12) {
                        Text("Memory mix")
                            .font(.headline)
                        ForEach(counts) { item in
                            HStack {
                                Text(item.kind.rawValue.capitalized)
                                    .foregroundStyle(.white.opacity(0.92))
                                Spacer()
                                Text("\(item.count)")
                                    .font(.subheadline.bold())
                                    .foregroundStyle(VexTheme.hotPink)
                            }
                        }
                    }
                    .padding(16)
                    .background(VexTheme.panel.opacity(0.94))
                    .clipShape(RoundedRectangle(cornerRadius: 18))

                    VStack(alignment: .leading, spacing: 12) {
                        Text("High-value phone memory")
                            .font(.headline)
                        if recent.isEmpty {
                            Text("No phone-local memories yet.")
                                .foregroundStyle(VexTheme.muted)
                        } else {
                            ForEach(recent) { memory in
                                VStack(alignment: .leading, spacing: 4) {
                                    HStack {
                                        Text(memory.kind.rawValue.uppercased())
                                            .font(.caption2.bold())
                                            .foregroundStyle(VexTheme.hotPink)
                                        Spacer()
                                        Text(String(format: "%.0f%%", memory.importance * 100))
                                            .font(.caption2)
                                            .foregroundStyle(VexTheme.muted)
                                    }
                                    Text(memory.text)
                                        .font(.subheadline)
                                        .foregroundStyle(.white.opacity(0.94))
                                }
                                .padding(.vertical, 5)
                            }
                        }
                    }
                    .padding(16)
                    .background(VexTheme.panel.opacity(0.94))
                    .clipShape(RoundedRectangle(cornerRadius: 18))
                }
                .padding(16)
            }
        }
    }
}

private struct VexPhoneView: View {
    @EnvironmentObject private var app: AppModel
    let onOpenChat: () -> Void
    @State private var brightness = Double(UIScreen.main.brightness) * 100
    @State private var clipboardText = ""
    @State private var actionStatus = "Ready"

    var body: some View {
        ZStack {
            VexSurfaceBackground()
            ScrollView {
                VStack(spacing: 16) {
                    VexSurfaceHeader(
                        eyebrow: "IPHONE // NATIVE ACTIONS",
                        title: "Phone",
                        subtitle: "Actions stay inside normal iOS permissions. Vex never gets an imaginary jailbreak."
                    )

                    VStack(alignment: .leading, spacing: 12) {
                        Text("Quick controls")
                            .font(.headline)

                        HStack {
                            Button("Settings") { run("on my iPhone open settings") }
                                .buttonStyle(.bordered)
                            Button("Flashlight") { run("on my iPhone toggle flashlight") }
                                .buttonStyle(.bordered)
                            Button("Maps") { run("on my iPhone open maps") }
                                .buttonStyle(.bordered)
                        }

                        Text("Brightness \(Int(brightness.rounded()))%")
                            .font(.subheadline)
                        Slider(value: $brightness, in: 0...100, step: 1)
                            .tint(VexTheme.hotPink)
                            .onChange(of: brightness) { _, value in
                                UIScreen.main.brightness = CGFloat(value / 100)
                            }
                    }
                    .padding(16)
                    .background(VexTheme.panel.opacity(0.94))
                    .clipShape(RoundedRectangle(cornerRadius: 18))

                    VStack(alignment: .leading, spacing: 10) {
                        Text("Clipboard")
                            .font(.headline)
                        TextField("Text to copy", text: $clipboardText, axis: .vertical)
                            .textFieldStyle(.roundedBorder)
                        Button {
                            let value = clipboardText.trimmingCharacters(in: .whitespacesAndNewlines)
                            guard !value.isEmpty else { return }
                            UIPasteboard.general.string = value
                            actionStatus = "Copied to iPhone clipboard."
                        } label: {
                            Label("Copy", systemImage: "doc.on.doc")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(VexTheme.hotPink)
                    }
                    .padding(16)
                    .background(VexTheme.panel.opacity(0.94))
                    .clipShape(RoundedRectangle(cornerRadius: 18))

                    VStack(alignment: .leading, spacing: 10) {
                        Text("Camera + voice")
                            .font(.headline)
                        Text("The proven camera/photo Vision and hands-free voice controls remain in Chat so they keep sharing the same conversation context.")
                            .font(.subheadline)
                            .foregroundStyle(VexTheme.muted)
                        Button {
                            onOpenChat()
                        } label: {
                            Label("Open Chat controls", systemImage: "camera.mic")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                    }
                    .padding(16)
                    .background(VexTheme.panel.opacity(0.94))
                    .clipShape(RoundedRectangle(cornerRadius: 18))

                    Text(actionStatus)
                        .font(.caption)
                        .foregroundStyle(VexTheme.muted)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .padding(16)
            }
        }
    }

    private func run(_ command: String) {
        actionStatus = "Working…"
        Task {
            let handled = await PhoneToolRouter.tryHandle(command, app: app)
            actionStatus = handled ? "Done." : "That action is not exposed by the current iOS router."
        }
    }
}
'''

def main() -> None:
    text = CONTENT.read_text(encoding="utf-8")
    if MARKER in text:
        print("v0.13.0 control surface already applied")
        return

    needle = "struct ContentView: View {"
    if needle not in text:
        raise SystemExit("ContentView declaration not found")

    text = text.replace(needle, "struct VexChatView: View {", 1)
    text = text.replace('Text("LOCAL GIRLFRIEND ENGINE")', 'Text("VEXNATIVE // CHAT")', 1)
    text += SHELL

    if "enum MemoryKind: String, Codable, Sendable" in (ROOT / "VexNative" / "Core" / "BrainModels.swift").read_text(encoding="utf-8"):
        models = ROOT / "VexNative" / "Core" / "BrainModels.swift"
        mtext = models.read_text(encoding="utf-8")
        if "enum MemoryKind: String, Codable, Sendable, CaseIterable" not in mtext:
            mtext = mtext.replace(
                "enum MemoryKind: String, Codable, Sendable {",
                "enum MemoryKind: String, Codable, Sendable, CaseIterable {",
                1
            )
            models.write_text(mtext, encoding="utf-8")

    CONTENT.write_text(text, encoding="utf-8")

    final = CONTENT.read_text(encoding="utf-8")
    for marker in [
        MARKER,
        "struct VexChatView: View",
        "struct ContentView: View",
        'Label("System", systemImage: "network")',
        'Label("Art", systemImage: "sparkles.rectangle.stack")',
        'Label("Memory", systemImage: "brain.head.profile")',
        'Label("Phone", systemImage: "iphone")',
        "/autonomy/requests",
        "/adaptive/status",
        "/art/health",
        "PCArtRouter.tryHandle",
        "PhoneToolRouter.tryHandle",
    ]:
        if marker not in final:
            raise SystemExit(f"missing v0.13.0 marker: {marker}")

    print("PASS v0.13.0 VexNative control surface patch")

if __name__ == "__main__":
    main()