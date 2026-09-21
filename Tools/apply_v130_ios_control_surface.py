#!/usr/bin/env python3
from pathlib import Path

CONTENT = Path("VexNative/ContentView.swift")
MARKER = 'V130_CONTROL_SURFACE = "v0.13.0-control-surface-v1"'

text = CONTENT.read_text(encoding="utf-8")
if MARKER in text:
    print("v0.13.0 control surface already applied")
    raise SystemExit(0)

if "import UserNotifications" not in text:
    text = text.replace("import UIKit\n", "import UIKit\nimport UserNotifications\n", 1)

old = "struct ContentView: View {"
if old not in text:
    raise SystemExit("ContentView struct marker missing")
text = text.replace(old, "struct VexChatView: View {", 1)
text = text.replace('Text("LOCAL GIRLFRIEND ENGINE")', 'Text("VEXNATIVE")', 1)

shell = r'''

// V130_CONTROL_SURFACE = "v0.13.0-control-surface-v1"
private enum VexRootTab: Hashable {
    case chat, system, art, memory, phone
}

struct ContentView: View {
    @EnvironmentObject private var app: AppModel
    @StateObject private var control = VexControlSurfaceModel()
    @State private var selection: VexRootTab = .chat

    var body: some View {
        TabView(selection: $selection) {
            VexChatView()
                .tag(VexRootTab.chat)
                .tabItem { Label("Chat", systemImage: "bubble.left.and.bubble.right.fill") }

            VexSystemView(control: control)
                .tag(VexRootTab.system)
                .tabItem { Label("System", systemImage: "cpu.fill") }

            VexArtControlView(control: control)
                .tag(VexRootTab.art)
                .tabItem { Label("Art", systemImage: "sparkles.rectangle.stack.fill") }

            VexMemoryView(control: control)
                .tag(VexRootTab.memory)
                .tabItem { Label("Memory", systemImage: "brain.head.profile") }

            VexPhoneView(selection: $selection)
                .tag(VexRootTab.phone)
                .tabItem { Label("Phone", systemImage: "iphone") }
        }
        .tint(VexTheme.hotPink)
    }
}

@MainActor
final class VexControlSurfaceModel: ObservableObject {
    @Published var isRefreshing = false
    @Published var bridgePreview = "Not checked"
    @Published var adaptivePreview = "Not checked"
    @Published var wantsPreview = "Not checked"
    @Published var memoryPreview = "Not checked"
    @Published var artHealthPreview = "Not checked"
    @Published var lastRefresh: Date?

    @Published var artBusy = false
    @Published var artJobID = ""
    @Published var artJobPreview = "No render queued"
    @Published var artImage: UIImage?

    private var endpoints: [String] {
        let defaults = UserDefaults.standard
        let primary = defaults.string(forKey: WebBrain.searxEndpointKey)?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let secondary = defaults.string(forKey: WebBrain.secondaryBridgeEndpointKey)?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        var values: [String] = []
        if !primary.isEmpty { values.append(primary) }
        if !secondary.isEmpty, secondary != primary { values.append(secondary) }
        return values
    }

    var endpointCount: Int { endpoints.count }

    func refreshAll() async {
        guard !isRefreshing else { return }
        isRefreshing = true
        defer { isRefreshing = false }
        bridgePreview = await preview(path: "/status")
        adaptivePreview = await preview(path: "/adaptive/status")
        wantsPreview = await preview(path: "/autonomy/requests")
        memoryPreview = await preview(path: "/memory/status")
        artHealthPreview = await preview(path: "/art/health")
        lastRefresh = Date()
    }

    func refreshMemory() async {
        memoryPreview = await preview(path: "/memory/status")
    }

    func refreshArtHealth() async {
        artHealthPreview = await preview(path: "/art/health")
    }

    func startArt(prompt: String, orientation: String) async {
        let clean = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty, !artBusy else { return }
        artBusy = true
        artImage = nil
        defer { artBusy = false }
        do {
            let json = try await requestJSON(
                path: "/art/generate",
                method: "POST",
                body: [
                    "prompt": clean,
                    "raw_prompt": clean,
                    "orientation": orientation
                ]
            )
            let job = (json["job_id"] as? String) ?? (json["id"] as? String) ?? ""
            artJobID = job
            artJobPreview = compact(json)
            if !job.isEmpty {
                await refreshArtJob()
            }
        } catch {
            artJobPreview = "Render request failed: \(error.localizedDescription)"
        }
    }

    func refreshArtJob() async {
        guard !artJobID.isEmpty, !artBusy else { return }
        artBusy = true
        defer { artBusy = false }
        do {
            var status = try await requestJSON(
                path: "/art/status",
                queryItems: [URLQueryItem(name: "job_id", value: artJobID)]
            )
            if (status["ok"] as? Bool) == false {
                status = try await requestJSON(
                    path: "/art/status",
                    queryItems: [URLQueryItem(name: "id", value: artJobID)]
                )
            }
            artJobPreview = compact(status)
            let state = String(describing: status["status"] ?? "").lowercased()
            if state == "done" {
                artImage = try await fetchArtResult()
            }
        } catch {
            artJobPreview = "Status failed: \(error.localizedDescription)"
        }
    }

    private func fetchArtResult() async throws -> UIImage? {
        for key in ["job_id", "id"] {
            do {
                let data = try await requestData(
                    path: "/art/result",
                    queryItems: [URLQueryItem(name: key, value: artJobID)]
                )
                if let image = UIImage(data: data) { return image }
            } catch {
                continue
            }
        }
        return nil
    }

    private func preview(path: String) async -> String {
        do {
            return compact(try await requestJSON(path: path))
        } catch {
            return "Unavailable: \(error.localizedDescription)"
        }
    }

    private func compact(_ json: [String: Any]) -> String {
        let priority = [
            "ok", "status", "version", "model", "installed", "running",
            "open_gaps", "active_lessons", "indexed_files", "memory_count",
            "request_count", "ownership", "bridge_role"
        ]
        var parts: [String] = []
        for key in priority {
            if let value = json[key] {
                parts.append("\(key): \(value)")
            }
        }
        if let requests = json["requests"] as? [Any] {
            parts.append("requests: \(requests.count)")
        }
        if !parts.isEmpty { return parts.joined(separator: "  •  ") }

        if JSONSerialization.isValidJSONObject(json),
           let data = try? JSONSerialization.data(withJSONObject: json, options: [.prettyPrinted]),
           let text = String(data: data, encoding: .utf8) {
            return String(text.prefix(1200))
        }
        return String(describing: json).prefix(1200).description
    }

    private func requestJSON(
        path: String,
        method: String = "GET",
        body: [String: Any]? = nil,
        queryItems: [URLQueryItem] = []
    ) async throws -> [String: Any] {
        let data = try await requestData(path: path, method: method, body: body, queryItems: queryItems)
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw NSError(domain: "VexNative.Control", code: 2, userInfo: [NSLocalizedDescriptionKey: "Bridge returned invalid JSON"])
        }
        return object
    }

    private func requestData(
        path: String,
        method: String = "GET",
        body: [String: Any]? = nil,
        queryItems: [URLQueryItem] = []
    ) async throws -> Data {
        guard !endpoints.isEmpty else {
            throw NSError(domain: "VexNative.Control", code: 1, userInfo: [NSLocalizedDescriptionKey: "No paired Vex Bridge endpoint"])
        }

        var lastError: Error?
        for endpoint in endpoints {
            guard let root = URL(string: endpoint),
                  VexBridgeNetworking.isBridgeURL(root),
                  var components = URLComponents(url: root, resolvingAgainstBaseURL: false)
            else { continue }

            components.path = path
            var items = components.queryItems ?? []
            items.append(contentsOf: queryItems)
            components.queryItems = items
            guard let url = components.url else { continue }

            var request = URLRequest(url: url)
            request.httpMethod = method
            request.timeoutInterval = 24
            if let body {
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                request.httpBody = try JSONSerialization.data(withJSONObject: body)
            }

            do {
                let (data, response) = try await VexBridgeNetworking.data(for: request)
                guard let http = response as? HTTPURLResponse,
                      (200...299).contains(http.statusCode)
                else {
                    let code = (response as? HTTPURLResponse)?.statusCode ?? -1
                    throw NSError(domain: "VexNative.Control", code: code, userInfo: [NSLocalizedDescriptionKey: "Bridge HTTP \(code)"])
                }
                return data
            } catch {
                lastError = error
            }
        }
        throw lastError ?? NSError(domain: "VexNative.Control", code: 3, userInfo: [NSLocalizedDescriptionKey: "No Vex Bridge endpoint responded"])
    }
}

private struct VexSurfaceBackground<Content: View>: View {
    let content: Content

    init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    var body: some View {
        ZStack {
            LinearGradient(
                colors: [
                    VexTheme.ink,
                    Color(red: 0.10, green: 0.035, blue: 0.12),
                    VexTheme.ink
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()

            content
        }
    }
}

private struct VexPanel<Content: View>: View {
    let title: String
    let systemImage: String
    let content: Content

    init(title: String, systemImage: String, @ViewBuilder content: () -> Content) {
        self.title = title
        self.systemImage = systemImage
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(title, systemImage: systemImage)
                .font(.headline)
                .foregroundStyle(VexTheme.hotPink)
            content
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(VexTheme.panel.opacity(0.94))
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(VexTheme.violet.opacity(0.24), lineWidth: 1)
        )
    }
}

private struct VexSystemView: View {
    @EnvironmentObject private var app: AppModel
    @ObservedObject var control: VexControlSurfaceModel

    var body: some View {
        NavigationStack {
            VexSurfaceBackground {
                ScrollView {
                    VStack(spacing: 12) {
                        VexPanel(title: "VexNative", systemImage: "bolt.horizontal.circle.fill") {
                            HStack {
                                Text(app.pcBrainConnected ? "PC cognition linked" : "Phone brain / fallback")
                                    .foregroundStyle(app.pcBrainConnected ? Color.green : VexTheme.muted)
                                Spacer()
                                Text("\(control.endpointCount) bridge\(control.endpointCount == 1 ? "" : "s")")
                                    .foregroundStyle(VexTheme.muted)
                            }
                            Text(app.pcBrainStatus)
                                .font(.caption)
                                .foregroundStyle(VexTheme.muted)
                        }

                        VexPanel(title: "Runtime", systemImage: "server.rack") {
                            Text(control.bridgePreview)
                                .font(.caption.monospaced())
                                .foregroundStyle(.white.opacity(0.88))
                        }

                        VexPanel(title: "Adaptive learning", systemImage: "arrow.triangle.2.circlepath") {
                            Text(control.adaptivePreview)
                                .font(.caption.monospaced())
                                .foregroundStyle(.white.opacity(0.88))
                        }

                        VexPanel(title: "Wants / autonomy", systemImage: "sparkles") {
                            Text(control.wantsPreview)
                                .font(.caption.monospaced())
                                .foregroundStyle(.white.opacity(0.88))
                        }

                        VexPanel(title: "Art worker", systemImage: "photo.stack.fill") {
                            Text(control.artHealthPreview)
                                .font(.caption.monospaced())
                                .foregroundStyle(.white.opacity(0.88))
                        }

                        NavigationLink {
                            BrainView()
                                .environmentObject(app)
                        } label: {
                            Label("Advanced Brain & Bridge Settings", systemImage: "slider.horizontal.3")
                                .frame(maxWidth: .infinity)
                                .padding(13)
                                .background(VexTheme.panel2)
                                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                        }
                        .buttonStyle(.plain)
                    }
                    .padding()
                }
                .refreshable { await control.refreshAll() }
            }
            .navigationTitle("System")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        Task { await control.refreshAll() }
                    } label: {
                        if control.isRefreshing { ProgressView() }
                        else { Image(systemName: "arrow.clockwise") }
                    }
                    .disabled(control.isRefreshing)
                }
            }
            .task {
                if control.lastRefresh == nil { await control.refreshAll() }
            }
        }
    }
}

private struct VexArtControlView: View {
    @ObservedObject var control: VexControlSurfaceModel
    @State private var prompt = ""
    @State private var orientation = "portrait"

    var body: some View {
        NavigationStack {
            VexSurfaceBackground {
                ScrollView {
                    VStack(spacing: 12) {
                        VexPanel(title: "Renderer", systemImage: "paintbrush.pointed.fill") {
                            Text(control.artHealthPreview)
                                .font(.caption.monospaced())
                                .foregroundStyle(.white.opacity(0.88))

                            Button("Refresh renderer") {
                                Task { await control.refreshArtHealth() }
                            }
                            .buttonStyle(.bordered)
                        }

                        VexPanel(title: "Create", systemImage: "wand.and.stars") {
                            TextField("Describe the render…", text: $prompt, axis: .vertical)
                                .lineLimit(3...8)
                                .textFieldStyle(.roundedBorder)

                            Picker("Frame", selection: $orientation) {
                                Text("Portrait").tag("portrait")
                                Text("Square").tag("square")
                                Text("Landscape").tag("landscape")
                            }
                            .pickerStyle(.segmented)

                            Button {
                                Task { await control.startArt(prompt: prompt, orientation: orientation) }
                            } label: {
                                HStack {
                                    if control.artBusy { ProgressView() }
                                    Text(control.artBusy ? "Working…" : "Send to VexArt")
                                }
                                .frame(maxWidth: .infinity)
                            }
                            .buttonStyle(.borderedProminent)
                            .tint(VexTheme.hotPink)
                            .disabled(prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || control.artBusy)
                        }

                        if !control.artJobID.isEmpty {
                            VexPanel(title: "Current render", systemImage: "clock.arrow.circlepath") {
                                Text("Job \(control.artJobID)")
                                    .font(.caption2.monospaced())
                                    .foregroundStyle(VexTheme.muted)
                                Text(control.artJobPreview)
                                    .font(.caption.monospaced())
                                Button("Refresh render status") {
                                    Task { await control.refreshArtJob() }
                                }
                                .buttonStyle(.bordered)
                                .disabled(control.artBusy)
                            }
                        }

                        if let image = control.artImage {
                            VexPanel(title: "Result", systemImage: "photo.fill") {
                                Image(uiImage: image)
                                    .resizable()
                                    .scaledToFit()
                                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                            }
                        }
                    }
                    .padding()
                }
            }
            .navigationTitle("Art")
            .task {
                if control.artHealthPreview == "Not checked" {
                    await control.refreshArtHealth()
                }
            }
        }
    }
}

private struct VexMemoryView: View {
    @EnvironmentObject private var app: AppModel
    @ObservedObject var control: VexControlSurfaceModel

    var body: some View {
        NavigationStack {
            VexSurfaceBackground {
                ScrollView {
                    VStack(spacing: 12) {
                        VexPanel(title: "Phone memory", systemImage: "iphone") {
                            Text("\(app.profile.memories.count) local memories")
                                .font(.title3.bold())
                            Text("\(app.messages.count) visible conversation turns")
                                .foregroundStyle(VexTheme.muted)
                        }

                        VexPanel(title: "PC memory", systemImage: "externaldrive.connected.to.line.below") {
                            Text(control.memoryPreview)
                                .font(.caption.monospaced())
                                .foregroundStyle(.white.opacity(0.88))
                            Button("Refresh memory status") {
                                Task { await control.refreshMemory() }
                            }
                            .buttonStyle(.bordered)
                        }

                        VexPanel(title: "Continuity", systemImage: "checkmark.seal.fill") {
                            Text("Verified copilot lessons stay PC-side and feed delegated VexCopilot tasks. Phone memory remains separate but can use the paired PC memory/cognition path.")
                                .font(.callout)
                                .foregroundStyle(VexTheme.muted)
                        }

                        NavigationLink {
                            BrainView()
                                .environmentObject(app)
                        } label: {
                            Label("Manage detailed brain memory", systemImage: "brain")
                                .frame(maxWidth: .infinity)
                                .padding(13)
                                .background(VexTheme.panel2)
                                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                        }
                        .buttonStyle(.plain)
                    }
                    .padding()
                }
            }
            .navigationTitle("Memory")
            .task {
                if control.memoryPreview == "Not checked" {
                    await control.refreshMemory()
                }
            }
        }
    }
}

private struct VexPhoneView: View {
    @EnvironmentObject private var app: AppModel
    @Binding var selection: VexRootTab
    @State private var notificationStatus = "Checking…"

    private var cameraStatus: String {
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized: return "Camera: allowed"
        case .denied: return "Camera: denied"
        case .restricted: return "Camera: restricted"
        case .notDetermined: return "Camera: not requested"
        @unknown default: return "Camera: unknown"
        }
    }

    private var micStatus: String {
        switch AVAudioSession.sharedInstance().recordPermission {
        case .granted: return "Microphone: allowed"
        case .denied: return "Microphone: denied"
        case .undetermined: return "Microphone: not requested"
        @unknown default: return "Microphone: unknown"
        }
    }

    private var speechStatus: String {
        switch SFSpeechRecognizer.authorizationStatus() {
        case .authorized: return "Speech recognition: allowed"
        case .denied: return "Speech recognition: denied"
        case .restricted: return "Speech recognition: restricted"
        case .notDetermined: return "Speech recognition: not requested"
        @unknown default: return "Speech recognition: unknown"
        }
    }

    var body: some View {
        NavigationStack {
            VexSurfaceBackground {
                ScrollView {
                    VStack(spacing: 12) {
                        VexPanel(title: "Phone permissions", systemImage: "lock.shield.fill") {
                            Text(cameraStatus)
                            Text(micStatus)
                            Text(speechStatus)
                            Text(notificationStatus)
                        }

                        VexPanel(title: "Native actions", systemImage: "iphone.and.arrow.forward") {
                            Button {
                                selection = .chat
                            } label: {
                                Label("Open camera / photo / voice controls", systemImage: "camera.fill")
                            }
                            .buttonStyle(.borderedProminent)
                            .tint(VexTheme.hotPink)

                            Button {
                                if let last = app.messages.last?.content, !last.isEmpty {
                                    UIPasteboard.general.string = last
                                }
                            } label: {
                                Label("Copy latest Vex reply", systemImage: "doc.on.doc")
                            }
                            .buttonStyle(.bordered)

                            Button {
                                Task {
                                    do {
                                        let granted = try await UNUserNotificationCenter.current()
                                            .requestAuthorization(options: [.alert, .sound, .badge])
                                        notificationStatus = granted ? "Notifications: allowed" : "Notifications: denied"
                                    } catch {
                                        notificationStatus = "Notifications: \(error.localizedDescription)"
                                    }
                                }
                            } label: {
                                Label("Request notifications", systemImage: "bell.badge")
                            }
                            .buttonStyle(.bordered)

                            Button {
                                guard let url = URL(string: UIApplication.openSettingsURLString) else { return }
                                UIApplication.shared.open(url)
                            } label: {
                                Label("Open iOS app settings", systemImage: "gear")
                            }
                            .buttonStyle(.bordered)
                        }

                        VexPanel(title: "Control boundary", systemImage: "link") {
                            Text("VexNative can expose permitted iPhone capabilities through its app and paired Bridge. iOS still controls camera, microphone, notifications, background work, and other protected features.")
                                .font(.callout)
                                .foregroundStyle(VexTheme.muted)
                        }
                    }
                    .padding()
                }
            }
            .navigationTitle("Phone")
            .task { await updateNotificationStatus() }
        }
    }

    private func updateNotificationStatus() async {
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        switch settings.authorizationStatus {
        case .authorized, .provisional, .ephemeral:
            notificationStatus = "Notifications: allowed"
        case .denied:
            notificationStatus = "Notifications: denied"
        case .notDetermined:
            notificationStatus = "Notifications: not requested"
        @unknown default:
            notificationStatus = "Notifications: unknown"
        }
    }
}
'''

text += shell
CONTENT.write_text(text, encoding="utf-8")

check = CONTENT.read_text(encoding="utf-8")
required = [
    MARKER,
    "struct VexChatView: View",
    "struct ContentView: View",
    'Text("VEXNATIVE")',
    'Label("Chat"',
    'Label("System"',
    'Label("Art"',
    'Label("Memory"',
    'Label("Phone"',
    '"/adaptive/status"',
    '"/autonomy/requests"',
    '"/memory/status"',
    '"/art/health"',
    '"/art/generate"',
    "UNUserNotificationCenter"
]
for marker in required:
    if marker not in check:
        raise SystemExit(f"v0.13.0 invariant missing: {marker}")
if 'Text("LOCAL GIRLFRIEND ENGINE")' in check:
    raise SystemExit("old girlfriend engine title still present")

print("Applied v0.13.0 VexNative control surface")