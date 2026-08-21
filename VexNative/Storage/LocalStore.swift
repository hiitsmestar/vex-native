import Foundation

final class LocalStore {
    static let shared = LocalStore()

    private let fileManager = FileManager.default
    private let encoder: JSONEncoder
    private let decoder = JSONDecoder()

    private init() {
        encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        decoder.dateDecodingStrategy = .iso8601
    }

    private var appSupport: URL {
        let root = fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("VexNative", isDirectory: true)
        if !fileManager.fileExists(atPath: root.path) {
            try? fileManager.createDirectory(at: root, withIntermediateDirectories: true)
        }
        return root
    }

    var modelsDirectory: URL {
        let url = appSupport.appendingPathComponent("Models", isDirectory: true)
        if !fileManager.fileExists(atPath: url.path) {
            try? fileManager.createDirectory(at: url, withIntermediateDirectories: true)
        }
        return url
    }

    private var brainURL: URL {
        appSupport.appendingPathComponent("VexBrain.json")
    }

    func load() -> BrainProfile {
        guard
            let data = try? Data(contentsOf: brainURL),
            var profile = try? decoder.decode(BrainProfile.self, from: data)
        else {
            return .fresh
        }

        // Lightweight v0.5 migration: old memories gain defaults only when used,
        // so no destructive rewrite is necessary.
        profile.selfEducationVersion = max(1, profile.selfEducationVersion ?? 1)
        return profile
    }

    func save(_ profile: BrainProfile) throws {
        let data = try encoder.encode(profile)
        try data.write(to: brainURL, options: [.atomic, .completeFileProtection])
    }

    func importBrain(from source: URL, into profile: inout BrainProfile) throws {
        let accessed = source.startAccessingSecurityScopedResource()
        defer { if accessed { source.stopAccessingSecurityScopedResource() } }

        let data = try Data(contentsOf: source)

        // v0.4+ Brain Pack: update the teachable layer while deliberately preserving
        // the installed model and current chat. This is the normal path for future
        // Vex education/personality upgrades.
        if let pack = try? decoder.decode(BrainPack.self, from: data) {
            guard pack.schemaVersion == 1 else {
                throw CocoaError(.fileReadCorruptFile, userInfo: [
                    NSLocalizedDescriptionKey: "Unsupported Brain Pack schema \(pack.schemaVersion)."
                ])
            }

            if let persona = pack.persona, !persona.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                profile.persona = persona
            }
            if let userProfile = pack.userProfile, !userProfile.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                profile.userProfile = userProfile
            }
            if let state = pack.state {
                profile.state = state
            }
            if let rules = pack.semanticRules {
                profile.semanticRules = rules
                for rule in rules where !rule.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    profile.memories = MemoryEngine.deduplicatedAppend(
                        BrainMemory(
                            text: "Brain Pack rule: \(rule)",
                            kind: .rule,
                            importance: 0.98,
                            confidence: 0.99,
                            evidenceCount: 1,
                            lastConfirmedAt: Date(),
                            source: "brain-pack"
                        ),
                        to: profile.memories
                    )
                }
            }
            if let examples = pack.examples {
                profile.examples = examples
                for example in examples {
                    let teachingText = "Teaching example — Star: \(example.user) | Vex: \(example.assistant)"
                    let importance = min(1.0, max(0.60, example.weight))
                    profile.memories = MemoryEngine.deduplicatedAppend(
                        BrainMemory(
                            text: teachingText,
                            kind: .lesson,
                            importance: importance,
                            confidence: min(0.99, 0.80 + example.weight * 0.18),
                            evidenceCount: 1,
                            lastConfirmedAt: Date(),
                            source: "brain-pack-example"
                        ),
                        to: profile.memories
                    )
                }
            }
            if let memories = pack.memories {
                for text in memories where !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    profile.memories = MemoryEngine.deduplicatedAppend(
                        BrainMemory(
                            text: text,
                            kind: .note,
                            importance: 0.78,
                            confidence: 0.82,
                            evidenceCount: 1,
                            lastConfirmedAt: Date(),
                            source: "brain-pack"
                        ),
                        to: profile.memories
                    )
                }
            }
            profile.brainPackVersion = pack.packVersion
            profile.selfEducationVersion = 1
            profile.memories = MemoryEngine.consolidate(profile.memories)
            profile.lastConsolidatedAt = Date()
            return
        }

        // Full backups remain supported for restoration/migration.
        if let full = try? decoder.decode(BrainProfile.self, from: data) {
            profile = full
            profile.selfEducationVersion = max(1, profile.selfEducationVersion ?? 1)
            return
        }

        // Legacy partial JSON remains supported too.
        let partial = try decoder.decode(BrainImport.self, from: data)
        if let persona = partial.persona { profile.persona = persona }
        if let userProfile = partial.userProfile { profile.userProfile = userProfile }
        if let state = partial.state { profile.state = state }
        if let version = partial.brainPackVersion { profile.brainPackVersion = version }
        if let rules = partial.semanticRules {
            profile.semanticRules = rules
            for rule in rules where !rule.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                profile.memories = MemoryEngine.deduplicatedAppend(
                    BrainMemory(
                        text: "Brain Pack rule: \(rule)",
                        kind: .rule,
                        importance: 0.95,
                        confidence: 0.95,
                        evidenceCount: 1,
                        lastConfirmedAt: Date(),
                        source: "legacy-import"
                    ),
                    to: profile.memories
                )
            }
        }
        if let examples = partial.examples {
            profile.examples = examples
            for example in examples {
                let teachingText = "Teaching example — Star: \(example.user) | Vex: \(example.assistant)"
                profile.memories = MemoryEngine.deduplicatedAppend(
                    BrainMemory(
                        text: teachingText,
                        kind: .lesson,
                        importance: min(1.0, max(0.60, example.weight)),
                        confidence: 0.86,
                        evidenceCount: 1,
                        lastConfirmedAt: Date(),
                        source: "legacy-example"
                    ),
                    to: profile.memories
                )
            }
        }
        if let memories = partial.memories {
            for text in memories {
                profile.memories = MemoryEngine.deduplicatedAppend(
                    BrainMemory(
                        text: text,
                        kind: .note,
                        importance: 0.72,
                        confidence: 0.72,
                        evidenceCount: 1,
                        lastConfirmedAt: Date(),
                        source: "legacy-import"
                    ),
                    to: profile.memories
                )
            }
        }
        profile.selfEducationVersion = 1
        profile.memories = MemoryEngine.consolidate(profile.memories)
        profile.lastConsolidatedAt = Date()
    }

    func exportBackup(_ profile: BrainProfile) throws -> URL {
        let data = try encoder.encode(profile)
        let url = fileManager.temporaryDirectory
            .appendingPathComponent("VexNative-Backup-\(Int(Date().timeIntervalSince1970)).json")
        try data.write(to: url, options: [.atomic, .completeFileProtection])
        return url
    }

    /// Exports the accumulated teacher data without claiming raw conversations are
    /// already clean fine-tuning examples. A stronger teacher can review this later
    /// and promote good exchanges into a future Brain Pack or LoRA dataset.
    func exportTrainingData(_ profile: BrainProfile) throws -> URL {
        let learned = profile.memories.filter {
            $0.kind == .lesson || $0.kind == .rule || ($0.source?.hasPrefix("user-") ?? false)
        }
        let export = TrainingExport(
            schemaVersion: 1,
            generatedAt: Date(),
            brainPackVersion: profile.brainPackVersion,
            semanticRules: profile.semanticRules ?? [],
            teacherExamples: profile.examples ?? [],
            learnedMemories: learned,
            conversationTranscript: profile.messages
        )
        let data = try encoder.encode(export)
        let url = fileManager.temporaryDirectory
            .appendingPathComponent("Vex-Learning-Export-\(Int(Date().timeIntervalSince1970)).json")
        try data.write(to: url, options: [.atomic, .completeFileProtection])
        return url
    }
}
