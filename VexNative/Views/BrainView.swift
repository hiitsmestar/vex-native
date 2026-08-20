import Foundation
import SwiftUI
import UniformTypeIdentifiers

struct BrainView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss

    @State private var showTeacherPackImporter = false
    @State private var isUpdatingTeacher = false
    @State private var teacherStatus = ""
    @State private var teacherExportURL: URL?
    @State private var lessonUser = ""
    @State private var lessonIdeal = ""

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

                    Text("Qwen3 0.6B is the preferred phone brain. The teacher pack below now carries Vex voice, continuity lessons, and examples separately from the model and app binary.")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    Button("Import a GGUF from Files") {
                        app.showModelImporter = true
                    }
                    .disabled(app.isLoadingModel)
                }

                Section("Vex Teacher Pack") {
                    VStack(alignment: .leading, spacing: 5) {
                        if let pack = app.profile.brainPack {
                            Text("Active: \(pack.name) v\(pack.version)")
                                .font(.subheadline.weight(.semibold))
                            Text("\(pack.rules?.count ?? 0) rules • \(pack.examples?.count ?? 0) teaching examples • \(pack.truths?.count ?? 0) truth anchors")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        } else {
                            Text("Embedded teacher pack will be installed automatically.")
                                .font(.subheadline)
                        }

                        if isUpdatingTeacher {
                            ProgressView("Checking for Vex teacher update…")
                        }
                        if !teacherStatus.isEmpty {
                            Text(teacherStatus)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }

                    Button("Check for Vex teacher update") {
                        Task { await checkForTeacherUpdate() }
                    }
                    .disabled(isUpdatingTeacher)

                    Button("Import private teacher pack JSON") {
                        showTeacherPackImporter = true
                    }

                    Button("Export current teacher pack") {
                        exportTeacherPack()
                    }

                    if let url = teacherExportURL {
                        ShareLink(item: url) {
                            Label("Share teacher pack", systemImage: "square.and.arrow.up")
                        }
                    }

                    Text("Teacher packs update personality, continuity rules, preferred examples, and anti-bot wording without rebuilding the IPA. Public updates stay sanitized; private Star/Vex details can live in an imported pack on this phone.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Section("Teach Vex") {
                    Button("Learn last exchange as a GOOD example") {
                        teachLastExchange()
                    }

                    TextField("Example Star message", text: $lessonUser, axis: .vertical)
                        .lineLimit(2...4)

                    TextEditor(text: $lessonIdeal)
                        .frame(minHeight: 90)
                        .font(.footnote)
                        .overlay(alignment: .topLeading) {
                            if lessonIdeal.isEmpty {
                                Text("Ideal Vex reply")
                                    .font(.footnote)
                                    .foregroundStyle(.tertiary)
                                    .padding(.top, 8)
                                    .padding(.leading, 5)
                                    .allowsHitTesting(false)
                            }
                        }

                    Button("Add teaching example") {
                        addTeachingExample(user: lessonUser, ideal: lessonIdeal)
                    }
                    .disabled(
                        lessonUser.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ||
                        lessonIdeal.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    )

                    Text("A teaching example becomes retrievable local memory immediately. When I make a Brain Pack update later, your locally taught examples are preserved when you use “Check for Vex teacher update.”")
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
                    Text("The model, chat, private profile, teacher pack, and locally taught examples are stored on-device. Checking for a teacher update downloads only the sanitized public teacher JSON; no API key is used.")
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
        .fileImporter(
            isPresented: $showTeacherPackImporter,
            allowedContentTypes: [.json],
            allowsMultipleSelection: false
        ) { result in
            if case .success(let urls) = result, let url = urls.first {
                importTeacherPack(from: url)
            }
        }
    }

    @MainActor
    private func checkForTeacherUpdate() async {
        guard !isUpdatingTeacher else { return }
        isUpdatingTeacher = true
        teacherStatus = ""
        defer { isUpdatingTeacher = false }

        do {
            var components = URLComponents(string: "https://raw.githubusercontent.com/hiitsmestar/vex-native/main/TeacherPacks/vex-teacher-core.json")!
            components.queryItems = [URLQueryItem(name: "v", value: String(Int(Date().timeIntervalSince1970)))]
            guard let url = components.url else { throw URLError(.badURL) }

            let request = URLRequest(
                url: url,
                cachePolicy: .reloadIgnoringLocalCacheData,
                timeoutInterval: 45
            )
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                throw URLError(.badServerResponse)
            }

            var downloaded = try LocalStore.shared.decodeBrainPack(data)

            // Public updates replace public lessons but preserve examples Star taught locally.
            let localExamples = (app.profile.brainPack?.examples ?? [])
                .filter { $0.id.hasPrefix("local-") }
            var mergedExamples = downloaded.examples ?? []
            for example in localExamples where !mergedExamples.contains(where: { $0.id == example.id }) {
                mergedExamples.append(example)
            }
            downloaded.examples = mergedExamples

            var updatedProfile = app.profile
            LocalStore.shared.applyBrainPack(downloaded, to: &updatedProfile)
            app.profile = updatedProfile
            app.persist()
            teacherStatus = "Teacher updated: \(downloaded.name) v\(downloaded.version) ✨"
        } catch {
            teacherStatus = "Teacher update failed: \(error.localizedDescription)"
            app.lastError = error.localizedDescription
        }
    }

    private func importTeacherPack(from url: URL) {
        do {
            var updatedProfile = app.profile
            let pack = try LocalStore.shared.importBrainPack(from: url, into: &updatedProfile)
            app.profile = updatedProfile
            app.persist()
            teacherStatus = "Imported \(pack.name) v\(pack.version) ✨"
        } catch {
            teacherStatus = "Teacher import failed: \(error.localizedDescription)"
            app.lastError = error.localizedDescription
        }
    }

    private func exportTeacherPack() {
        guard let pack = app.profile.brainPack else {
            teacherStatus = "No teacher pack is active yet."
            return
        }
        do {
            teacherExportURL = try LocalStore.shared.exportBrainPack(pack)
            teacherStatus = "Teacher pack export ready."
        } catch {
            teacherStatus = "Teacher export failed: \(error.localizedDescription)"
            app.lastError = error.localizedDescription
        }
    }

    private func teachLastExchange() {
        let tail = app.profile.messages.suffix(2)
        guard tail.count == 2,
              let user = tail.first(where: { $0.role == .user })?.content,
              let assistant = tail.first(where: { $0.role == .assistant })?.content
        else {
            teacherStatus = "Need one Star → Vex exchange first."
            return
        }
        addTeachingExample(user: user, ideal: assistant)
    }

    private func addTeachingExample(user: String, ideal: String) {
        let cleanUser = user.trimmingCharacters(in: .whitespacesAndNewlines)
        let cleanIdeal = ideal.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleanUser.isEmpty, !cleanIdeal.isEmpty else { return }

        var pack = app.profile.brainPack ?? DefaultBrain.teacherPack
        var examples = pack.examples ?? []
        let example = BrainPackExample(
            id: "local-\(UUID().uuidString.lowercased())",
            user: cleanUser,
            assistant: cleanIdeal,
            tags: ["local", "taught-on-device"],
            weight: 1.0
        )
        examples.append(example)
        if examples.count > 80 {
            examples = Array(examples.suffix(80))
        }
        pack.examples = examples

        var updatedProfile = app.profile
        LocalStore.shared.applyBrainPack(pack, to: &updatedProfile)
        app.profile = updatedProfile
        app.persist()

        lessonUser = ""
        lessonIdeal = ""
        teacherStatus = "Learned a new Vex example locally 💕"
    }
}
