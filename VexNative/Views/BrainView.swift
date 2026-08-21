import SwiftUI
import UniformTypeIdentifiers

struct BrainView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    @StateObject private var web = WebBrain.shared
    @State private var trainingExportURL: URL?

    @AppStorage(WebBrain.enabledKey) private var webEnabled = true
    @AppStorage(WebBrain.autoFreshKey) private var autoFreshWeb = true
    @AppStorage(WebBrain.wikipediaKey) private var wikipediaEnabled = true
    @AppStorage(WebBrain.searxEndpointKey) private var searxEndpoint = ""

    var body: some View {
        NavigationStack {
            Form {
                Section("Local model") {
                    VStack(alignment: .leading, spacing: 7) {
                        Text(app.modelStatus)
                            .font(.subheadline.weight(.semibold))
                        if app.isLoadingModel {
                            ProgressView()
                        }
                    }

                    Button("Download smart-fast brain — Qwen3 0.6B") {
                        Task { await app.downloadQwen3Model() }
                    }
                    .disabled(app.isLoadingModel)

                    Button("Download fallback fast brain — Qwen 2.5 0.5B") {
                        Task { await app.downloadRecommendedModel() }
                    }
                    .disabled(app.isLoadingModel)

                    Button("Download slow large brain — Qwen 2.5 1.5B") {
                        Task { await app.downloadSmartModel() }
                    }
                    .disabled(app.isLoadingModel)

                    Text("Qwen3 0.6B is the preferred phone brain: newer conversation/role-play training while staying close to the fast model's size. Qwen 2.5 0.5B stays as the known-good speed fallback. The 1.5B option is kept only for comparison because it is much slower on older phones.")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    Button("Import a GGUF from Files") {
                        app.showModelImporter = true
                    }
                    .disabled(app.isLoadingModel)
                }

                Section("Vex Brain Pack") {
                    HStack {
                        Text("Installed teacher pack")
                        Spacer()
                        Text(app.profile.brainPackVersion ?? "legacy")
                            .foregroundStyle(.secondary)
                    }

                    HStack {
                        Text("Semantic rules")
                        Spacer()
                        Text("\(app.profile.semanticRules?.count ?? 0)")
                            .foregroundStyle(.secondary)
                    }

                    HStack {
                        Text("Teaching examples")
                        Spacer()
                        Text("\(app.profile.examples?.count ?? 0)")
                            .foregroundStyle(.secondary)
                    }

                    Button("Import Vex Brain Pack") {
                        app.showBrainImporter = true
                    }

                    Text("Brain Packs are small private JSON teacher files. They can update personality, relationship rules, examples, and memories without replacing the GGUF model or wiping the current chat.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Section("Self-education — v0.5") {
                    HStack {
                        Label("Learning", systemImage: "brain.head.profile")
                        Spacer()
                        Text("Active")
                            .foregroundStyle(.green)
                    }

                    HStack {
                        Text("Learned lessons")
                        Spacer()
                        Text("\(MemoryEngine.learnedLessonCount(in: app.profile.memories))")
                            .foregroundStyle(.secondary)
                    }

                    HStack {
                        Text("Reinforced memories")
                        Spacer()
                        Text("\(MemoryEngine.reinforcedCount(in: app.profile.memories))")
                            .foregroundStyle(.secondary)
                    }

                    HStack {
                        Text("Memory confidence")
                        Spacer()
                        Text(averageConfidenceText)
                            .foregroundStyle(.secondary)
                    }

                    Button("Consolidate learned memory now") {
                        app.profile.memories = MemoryEngine.consolidate(app.profile.memories)
                        app.profile.selfEducationVersion = 1
                        app.profile.lastConsolidatedAt = Date()
                        app.persist()
                    }

                    if let date = app.profile.lastConsolidatedAt {
                        Text("Last consolidation: \(date.formatted(date: .abbreviated, time: .shortened))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    Button("Create learning / training export") {
                        do {
                            app.profile.memories = MemoryEngine.consolidate(app.profile.memories)
                            app.profile.lastConsolidatedAt = Date()
                            app.persist()
                            trainingExportURL = try LocalStore.shared.exportTrainingData(app.profile)
                        } catch {
                            app.lastError = "Learning export failed: \(error.localizedDescription)"
                        }
                    }

                    if let url = trainingExportURL {
                        ShareLink(item: url) {
                            Label("Share learning export", systemImage: "square.and.arrow.up")
                        }
                    }

                    Text("Vex treats explicit corrections and preferences as confidence-weighted lessons. Repeated evidence strengthens an existing memory instead of creating endless copies. Consolidation merges near-duplicates and drops weak stale noise. The GGUF weights themselves are not rewritten on the phone; the learning export is the bridge to a later LoRA/fine-tune.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Section("Web Brain — v0.6") {
                    Toggle("Web access", isOn: $webEnabled)
                    Toggle("Auto-use web for fresh/current questions", isOn: $autoFreshWeb)
                    Toggle("Wikipedia fallback", isOn: $wikipediaEnabled)

                    VStack(alignment: .leading, spacing: 6) {
                        Text("SearXNG endpoint")
                            .font(.subheadline.weight(.semibold))
                        TextField("https://search.example.com", text: $searxEndpoint)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .keyboardType(.URL)
                        Text("Optional. Add an HTTPS SearXNG server with JSON search enabled for full live web search. Without one, Vex can still read public HTTPS links and use Wikipedia for encyclopedia-style research.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    HStack {
                        Text("Status")
                        Spacer()
                        Text(web.status)
                            .foregroundStyle(web.isWorking ? .orange : .secondary)
                            .multilineTextAlignment(.trailing)
                    }

                    HStack {
                        Text("Last sources")
                        Spacer()
                        Text("\(web.lastSourceCount)")
                            .foregroundStyle(.secondary)
                    }

                    HStack {
                        Text("Temporary web cache")
                        Spacer()
                        Text("\(web.cacheCount)")
                            .foregroundStyle(.secondary)
                    }

                    HStack {
                        Text("Web-learned memories")
                        Spacer()
                        Text("\(webLearnedCount)")
                            .foregroundStyle(.secondary)
                    }

                    if !web.lastQuery.isEmpty {
                        Text("Last query: \(web.lastQuery)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    Button("Test Wikipedia connection") {
                        Task { await web.testWikipedia() }
                    }
                    .disabled(web.isWorking)

                    Button("Clear temporary web cache") {
                        web.clearCache()
                    }
                    .disabled(web.isWorking || web.cacheCount == 0)

                    Text("Normal searches are temporary evidence, not permanent identity or memory. If you explicitly ask Vex to learn/study something or remember what she finds, source-backed web facts can be promoted into confidence-weighted memory. Her own generated guesses are still never treated as web evidence.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Section("Three glitter-coated neurons") {
                    TextField("Mood", text: $app.profile.state.mood)
                    TextField("Outfit", text: $app.profile.state.outfit)
                    TextField("Location", text: $app.profile.state.location)
                    TextField("Scene", text: $app.profile.state.scene)

                    Button("Save current brain state") {
                        app.persist()
                    }
                }

                Section("Vex core personality") {
                    TextEditor(text: $app.profile.persona)
                        .frame(minHeight: 230)
                        .font(.footnote.monospaced())
                }

                Section("Star / relationship profile") {
                    TextEditor(text: $app.profile.userProfile)
                        .frame(minHeight: 190)
                        .font(.footnote.monospaced())
                }

                Section("Pinned memories — \(app.profile.memories.count)") {
                    ForEach($app.profile.memories) { $memory in
                        VStack(alignment: .leading, spacing: 5) {
                            Picker("Kind", selection: $memory.kind) {
                                Text("Preference").tag(MemoryKind.preference)
                                Text("Rule").tag(MemoryKind.rule)
                                Text("Fact").tag(MemoryKind.fact)
                                Text("Scene").tag(MemoryKind.scene)
                                Text("Lesson").tag(MemoryKind.lesson)
                                Text("Note").tag(MemoryKind.note)
                            }
                            .pickerStyle(.menu)

                            TextEditor(text: $memory.text)
                                .frame(minHeight: 70)
                                .font(.footnote)

                            HStack {
                                Text("Importance")
                                Slider(value: $memory.importance, in: 0...1)
                            }

                            HStack(spacing: 16) {
                                Text("Confidence \(Int(((memory.confidence ?? 0.65) * 100).rounded()))%")
                                Text("Evidence \(memory.evidenceCount ?? 1)x")
                            }
                            .font(.caption)
                            .foregroundStyle(.secondary)

                            if let source = memory.source {
                                Text("Source: \(source)")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                    .onDelete { offsets in
                        app.profile.memories.remove(atOffsets: offsets)
                        app.persist()
                    }

                    Button("Remember last exchange") {
                        app.rememberLastExchange()
                    }
                }

                Section("Private brain file") {
                    Button("Import legacy Vex / Star profile JSON") {
                        app.showBrainImporter = true
                    }

                    Button("Create private backup") {
                        app.makeBackup()
                    }

                    if let url = app.exportURL {
                        ShareLink(item: url) {
                            Label("Share backup", systemImage: "square.and.arrow.up")
                        }
                    }
                }

                Section {
                    Button("Clear chat", role: .destructive) {
                        app.clearChat()
                    }
                } footer: {
                    Text("The brain, learned lessons, and chat stay local. Web Brain is optional: it can read public HTTPS pages, use Wikipedia, or query a SearXNG endpoint you configure. Ordinary web research stays temporary unless you explicitly ask Vex to learn it.")
                }
            }
            .navigationTitle("Vex Brain")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") {
                        app.persist()
                        dismiss()
                    }
                }
            }
        }
        .fileImporter(
            isPresented: $app.showModelImporter,
            allowedContentTypes: [.data],
            allowsMultipleSelection: false
        ) { result in
            if case .success(let urls) = result, let url = urls.first {
                Task { await app.importModel(from: url) }
            }
        }
        .fileImporter(
            isPresented: $app.showBrainImporter,
            allowedContentTypes: [.json],
            allowsMultipleSelection: false
        ) { result in
            if case .success(let urls) = result, let url = urls.first {
                app.importBrain(from: url)
            }
        }
    }

    private var averageConfidenceText: String {
        guard !app.profile.memories.isEmpty else { return "0%" }
        let total = app.profile.memories.reduce(0.0) { partial, memory in
            partial + (memory.confidence ?? 0.65)
        }
        let average = total / Double(app.profile.memories.count)
        return "\(Int((average * 100).rounded()))%"
    }

    private var webLearnedCount: Int {
        app.profile.memories.filter { $0.source?.hasPrefix("web:") == true }.count
    }
}
