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
            let profile = try? decoder.decode(BrainProfile.self, from: data)
        else {
            return .fresh
        }
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
    }

    func exportBackup(_ profile: BrainProfile) throws -> URL {
        let data = try encoder.encode(profile)
        let url = fileManager.temporaryDirectory
            .appendingPathComponent("VexNative-Backup-\(Int(Date().timeIntervalSince1970)).json")
        try data.write(to: url, options: [.atomic, .completeFileProtection])
        return url
    }
}
