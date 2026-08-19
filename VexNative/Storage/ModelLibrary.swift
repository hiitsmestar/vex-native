import Foundation

enum ModelLibraryError: LocalizedError {
    case notGGUF
    case badDownload

    var errorDescription: String? {
        switch self {
        case .notGGUF: return "That file is not a .gguf model."
        case .badDownload: return "The downloaded file was not a valid GGUF file."
        }
    }
}

final class ModelLibrary {
    static let shared = ModelLibrary()
    private init() {}

    // Official Qwen GGUF repository. Q4_K_M is intentionally tiny enough for a first phone build.
    static let recommendedModelURL = URL(
        string: "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf?download=true"
    )!

    func importedModelURL(filename: String?) -> URL? {
        guard let filename else { return nil }
        let url = LocalStore.shared.modelsDirectory.appendingPathComponent(filename)
        return FileManager.default.fileExists(atPath: url.path) ? url : nil
    }

    func importModel(from source: URL) throws -> URL {
        guard source.pathExtension.lowercased() == "gguf" else {
            throw ModelLibraryError.notGGUF
        }

        let accessed = source.startAccessingSecurityScopedResource()
        defer { if accessed { source.stopAccessingSecurityScopedResource() } }

        let destination = LocalStore.shared.modelsDirectory
            .appendingPathComponent(source.lastPathComponent)

        let fm = FileManager.default
        if fm.fileExists(atPath: destination.path) {
            try fm.removeItem(at: destination)
        }
        try fm.copyItem(at: source, to: destination)
        try? fm.setAttributes([.protectionKey: FileProtectionType.complete], ofItemAtPath: destination.path)
        return destination
    }

    func downloadRecommendedModel() async throws -> URL {
        let (temporary, response) = try await URLSession.shared.download(from: Self.recommendedModelURL)
        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw ModelLibraryError.badDownload
        }

        let destination = LocalStore.shared.modelsDirectory
            .appendingPathComponent("qwen2.5-0.5b-instruct-q4_k_m.gguf")

        let fm = FileManager.default
        if fm.fileExists(atPath: destination.path) {
            try fm.removeItem(at: destination)
        }
        try fm.moveItem(at: temporary, to: destination)

        let attrs = try fm.attributesOfItem(atPath: destination.path)
        let size = (attrs[.size] as? NSNumber)?.intValue ?? 0
        guard size > 50_000_000 else {
            try? fm.removeItem(at: destination)
            throw ModelLibraryError.badDownload
        }

        try? fm.setAttributes([.protectionKey: FileProtectionType.complete], ofItemAtPath: destination.path)
        return destination
    }
}
