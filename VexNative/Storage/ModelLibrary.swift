import Foundation

enum ModelLibraryError: LocalizedError {
    case notGGUF
    case badDownload

    var errorDescription: String? {
        switch self {
        case .notGGUF: return "That file is not a .gguf model."
        case .badDownload: return "The model download did not produce a valid GGUF file. I tried the primary and fallback Qwen3 sources."
        }
    }
}

final class ModelLibrary {
    static let shared = ModelLibrary()
    private init() {}

    static let recommendedModelURL = URL(
        string: "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf?download=true"
    )!

    static let smartModelURL = URL(
        string: "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q3_k_m.gguf?download=true"
    )!

    // v0.15.5 local-direct fallback: refusal-suppressed Qwen3 GGUF.
    // PC Ollama remains the higher-quality brain; this one is small enough for the iPhone.
    static let qwen3ModelURL = URL(
        string: "https://huggingface.co/jaahas/Qwen3-0.6B-abliterated-Q4_K_M-GGUF/resolve/main/qwen3-0.6b-abliterated-q4_k_m.gguf?download=true"
    )!

    static let qwen3FallbackURL = URL(
        string: "https://huggingface.co/bartowski/mlabonne_Qwen3-0.6B-abliterated-GGUF/resolve/main/mlabonne_Qwen3-0.6B-abliterated-Q4_K_M.gguf?download=true"
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
        try await download(
            from: Self.recommendedModelURL,
            filename: "qwen2.5-0.5b-instruct-q4_k_m.gguf",
            minimumBytes: 300_000_000
        )
    }

    func downloadSmartModel() async throws -> URL {
        try await download(
            from: Self.smartModelURL,
            filename: "qwen2.5-1.5b-instruct-q3_k_m.gguf",
            minimumBytes: 700_000_000
        )
    }

    func downloadQwen3Model() async throws -> URL {
        do {
            return try await download(
                from: Self.qwen3ModelURL,
                filename: "qwen3-0.6b-abliterated-q4_k_m.gguf",
                minimumBytes: 300_000_000
            )
        } catch {
            return try await download(
                from: Self.qwen3FallbackURL,
                filename: "mlabonne_Qwen3-0.6B-abliterated-Q4_K_M.gguf",
                minimumBytes: 300_000_000
            )
        }
    }

    private func download(from source: URL, filename: String, minimumBytes: Int) async throws -> URL {
        var request = URLRequest(url: source)
        request.setValue("application/octet-stream", forHTTPHeaderField: "Accept")
        request.setValue("VexNative/0.3.8", forHTTPHeaderField: "User-Agent")
        request.setValue("no-cache", forHTTPHeaderField: "Cache-Control")

        let (temporary, response) = try await URLSession.shared.download(for: request)
        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw ModelLibraryError.badDownload
        }

        let destination = LocalStore.shared.modelsDirectory.appendingPathComponent(filename)
        let fm = FileManager.default
        if fm.fileExists(atPath: destination.path) {
            try fm.removeItem(at: destination)
        }
        try fm.moveItem(at: temporary, to: destination)

        let attrs = try fm.attributesOfItem(atPath: destination.path)
        let size = (attrs[.size] as? NSNumber)?.intValue ?? 0
        guard size > minimumBytes, isGGUF(at: destination) else {
            try? fm.removeItem(at: destination)
            throw ModelLibraryError.badDownload
        }

        try? fm.setAttributes([.protectionKey: FileProtectionType.complete], ofItemAtPath: destination.path)
        return destination
    }

    private func isGGUF(at url: URL) -> Bool {
        guard let handle = try? FileHandle(forReadingFrom: url) else { return false }
        defer { try? handle.close() }
        guard let magic = try? handle.read(upToCount: 4), magic.count == 4 else {
            return false
        }
        return magic == Data([0x47, 0x47, 0x55, 0x46])
    }
}
