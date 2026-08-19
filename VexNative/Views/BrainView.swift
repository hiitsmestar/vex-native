import SwiftUI
import UniformTypeIdentifiers

struct BrainView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss

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
                    Button("Import Vex / Star profile JSON") {
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
                    Text("The app stores its brain and chat locally. No API key is used. The only network downloads built in are the optional free model downloads.")
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
}
