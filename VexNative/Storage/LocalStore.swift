import Foundation

final class LocalStore {
    static let shared = LocalStore()

    private let fileManager = FileManager.default
    private let encoder: JSONEncoder
    private let decoder = JSONDecoder()

    private let packStart = "[[VEX_RUNTIME_TEACHER_PACK]]"
    private let packEnd = "[[/VEX_RUNTIME_TEACHER_PACK]]"
    private let memoryPrefix = "[BrainPack "

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
        var profile: BrainProfile
        if let data = try? Data(contentsOf: brainURL),
           let saved = try? decoder.decode(BrainProfile.self, from: data) {
            profile = saved
        } else {
            profile = .fresh
        }

        let pack = profile.brainPack ?? DefaultBrain.teacherPack
        applyBrainPack(pack, to: &profile)
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

        if let full = try? decoder.decode(BrainProfile.self, from: data) {
            profile = full
            applyBrainPack(profile.brainPack ?? DefaultBrain.teacherPack, to: &profile)
            return
        }

        if let pack = try? decodeBrainPack(data) {
            applyBrainPack(pack, to: &profile)
            return
        }

        let partial = try decoder.decode(BrainImport.self, from: data)
        if let persona = partial.persona { profile.persona = persona }
        if let userProfile = partial.userProfile { profile.userProfile = userProfile }
        if let state = partial.state { profile.state = state }
        if let memories = partial.memories {
            for text in memories {
                profile.memories = MemoryEngine.deduplicatedAppend(
                    BrainMemory(text: text, kind: .note, importance: 0.72),
                    to: profile.memories
                )
            }
        }
        applyBrainPack(partial.brainPack ?? profile.brainPack ?? DefaultBrain.teacherPack, to: &profile)
    }

    func importBrainPack(from source: URL, into profile: inout BrainProfile) throws -> VexBrainPack {
        let accessed = source.startAccessingSecurityScopedResource()
        defer { if accessed { source.stopAccessingSecurityScopedResource() } }
        let data = try Data(contentsOf: source)
        return try installBrainPack(data: data, into: &profile)
    }

    @discardableResult
    func installBrainPack(data: Data, into profile: inout BrainProfile) throws -> VexBrainPack {
        let pack = try decodeBrainPack(data)
        applyBrainPack(pack, to: &profile)
        return pack
    }

    func decodeBrainPack(_ data: Data) throws -> VexBrainPack {
        let pack = try decoder.decode(VexBrainPack.self, from: data)
        try validate(pack)
        return pack
    }

    func applyBrainPack(_ pack: VexBrainPack, to profile: inout BrainProfile) {
        profile.brainPack = pack

        // Replace the prior runtime teacher header without touching the user's private
        // persona text below it. PromptComposer already reads persona, so packs can teach
        // new voice/continuity behavior without another app rebuild.
        let basePersona = strippingRuntimePack(from: profile.persona)
        let addendum = String((pack.personaAddendum ?? "").prefix(250))
        let truthAnchors = (pack.truths ?? [])
            .prefix(2)
            .map { String($0.prefix(110)) }
            .joined(separator: " | ")

        var runtimeHeader = "\(packStart)\nTeacher: \(pack.name) v\(pack.version)."
        if !addendum.isEmpty { runtimeHeader += " \(addendum)" }
        if !truthAnchors.isEmpty { runtimeHeader += " Anchors: \(truthAnchors)" }
        runtimeHeader += "\n\(packEnd)"
        profile.persona = runtimeHeader + "\n" + basePersona

        // Teacher lessons are normal on-device memories, so the existing lexical memory
        // engine can retrieve a relevant rule/example. Remove older pack lessons first.
        profile.memories.removeAll { $0.text.hasPrefix(memoryPrefix) }
        let marker = "[BrainPack \(pack.packID) v\(pack.version)]"

        for truth in (pack.truths ?? []).prefix(8) {
            profile.memories = MemoryEngine.deduplicatedAppend(
                BrainMemory(text: "\(marker) Truth: \(truth)", kind: .fact, importance: 0.98),
                to: profile.memories
            )
        }

        for rule in (pack.rules ?? []).sorted(by: { $0.priority > $1.priority }).prefix(12) {
            let triggerText = rule.triggers.joined(separator: ", ")
            profile.memories = MemoryEngine.deduplicatedAppend(
                BrainMemory(
                    text: "\(marker) Teacher rule (\(triggerText)): \(rule.instruction)",
                    kind: .rule,
                    importance: min(1.0, 0.82 + Double(rule.priority) / 600.0)
                ),
                to: profile.memories
            )
        }

        if let banned = pack.bannedPhrases, !banned.isEmpty {
            profile.memories = MemoryEngine.deduplicatedAppend(
                BrainMemory(
                    text: "\(marker) Avoid canned phrases: \(banned.prefix(12).joined(separator: " | "))",
                    kind: .rule,
                    importance: 0.94
                ),
                to: profile.memories
            )
        }

        for example in (pack.examples ?? []).prefix(40) {
            profile.memories = MemoryEngine.deduplicatedAppend(
                BrainMemory(
                    text: "\(marker) Teaching example — Star: \(example.user) | Vex: \(example.assistant)",
                    kind: .note,
                    importance: min(1.0, max(0.72, example.weight))
                ),
                to: profile.memories
            )
        }
    }

    private func strippingRuntimePack(from persona: String) -> String {
        guard let start = persona.range(of: packStart),
              let end = persona.range(of: packEnd, range: start.upperBound..<persona.endIndex)
        else {
            return persona.trimmingCharacters(in: .whitespacesAndNewlines)
        }

        var cleaned = persona
        cleaned.removeSubrange(start.lowerBound..<end.upperBound)
        return cleaned.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func validate(_ pack: VexBrainPack) throws {
        guard pack.schemaVersion == 1 else {
            throw NSError(
                domain: "VexBrainPack",
                code: 1,
                userInfo: [NSLocalizedDescriptionKey: "This teacher pack uses schema v\(pack.schemaVersion). This build supports schema v1."]
            )
        }
        guard !pack.packID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !pack.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !pack.version.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else {
            throw NSError(
                domain: "VexBrainPack",
                code: 2,
                userInfo: [NSLocalizedDescriptionKey: "Teacher pack is missing its id, name, or version."]
            )
        }
    }

    func exportBackup(_ profile: BrainProfile) throws -> URL {
        let data = try encoder.encode(profile)
        let url = fileManager.temporaryDirectory
            .appendingPathComponent("VexNative-Backup-\(Int(Date().timeIntervalSince1970)).json")
        try data.write(to: url, options: [.atomic, .completeFileProtection])
        return url
    }

    func exportBrainPack(_ pack: VexBrainPack) throws -> URL {
        try validate(pack)
        let data = try encoder.encode(pack)
        let safeVersion = pack.version.replacingOccurrences(of: "/", with: "-")
        let url = fileManager.temporaryDirectory
            .appendingPathComponent("Vex-Teacher-Pack-\(safeVersion).json")
        try data.write(to: url, options: [.atomic, .completeFileProtection])
        return url
    }
}
