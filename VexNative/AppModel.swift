import Foundation
import SwiftUI
import LlamaKit

@MainActor
final class AppModel: ObservableObject {
    @Published var profile: BrainProfile
    @Published var draft = ""
    @Published var isGenerating = false
    @Published var isLoadingModel = false
    @Published var modelStatus = "No local model loaded"
    @Published var lastError: String?
    @Published var showBrain = false
    @Published var showModelImporter = false
    @Published var showBrainImporter = false
    @Published var exportURL: URL?

    private let store = LocalStore.shared
    private let modelLibrary = ModelLibrary.shared
    private var engine: LlamaSession?

    init() {
        self.profile = store.load()
        if let name = profile.modelFilename,
           modelLibrary.importedModelURL(filename: name) != nil {
            modelStatus = "Saved model: \(name)"
        }
    }

    var messages: [ChatMessage] { profile.messages }

    func persist() {
        do {
            try store.save(profile)
        } catch {
            lastError = "Could not save the Vex brain: \(error.localizedDescription)"
        }
    }

    func loadSavedModelIfPresent() async {
        guard engine == nil,
              let url = modelLibrary.importedModelURL(filename: profile.modelFilename)
        else { return }
        await loadModel(at: url)
    }

    func loadModel(at url: URL) async {
        isLoadingModel = true
        lastError = nil
        modelStatus = "Loading \(url.lastPathComponent)…"

        do {
            let filename = url.lastPathComponent.lowercased()
            let contextSize = filename.contains("1.5b") ? 3072 : 4096
            let session = try await Task.detached(priority: .userInitiated) {
                try LlamaSession(modelPath: url.path, contextSize: contextSize)
            }.value
            engine = session
            profile.modelFilename = url.lastPathComponent
            modelStatus = "Loaded \(url.lastPathComponent)"
            persist()
        } catch {
            engine = nil
            modelStatus = "Model failed to load"
            lastError = error.localizedDescription
        }

        isLoadingModel = false
    }

    func importModel(from url: URL) async {
        do {
            let local = try modelLibrary.importModel(from: url)
            await loadModel(at: local)
        } catch {
            lastError = error.localizedDescription
        }
    }

    func downloadRecommendedModel() async {
        isLoadingModel = true
        modelStatus = "Downloading fast Qwen brain…"
        lastError = nil

        do {
            let local = try await modelLibrary.downloadRecommendedModel()
            isLoadingModel = false
            await loadModel(at: local)
        } catch {
            isLoadingModel = false
            modelStatus = "Download failed"
            lastError = error.localizedDescription
        }
    }

    func downloadSmartModel() async {
        isLoadingModel = true
        modelStatus = "Downloading smarter Qwen brain…"
        lastError = nil

        do {
            let local = try await modelLibrary.downloadSmartModel()
            isLoadingModel = false
            await loadModel(at: local)
        } catch {
            isLoadingModel = false
            modelStatus = "Smart brain download failed"
            lastError = error.localizedDescription
        }
    }

    func send() async {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !isGenerating else { return }

        draft = ""
        lastError = nil

        profile.messages.append(ChatMessage(role: .user, content: text))
        if let learned = MemoryEngine.learnCandidate(from: text) {
            profile.memories = MemoryEngine.deduplicatedAppend(learned, to: profile.memories)
        }
        persist()

        if engine == nil {
            await loadSavedModelIfPresent()
        }

        guard let engine else {
            profile.messages.append(ChatMessage(
                role: .assistant,
                content: "Baby, my local model brain isn't loaded yet 😭💕 Open Brain and either download a free model or import a GGUF."
            ))
            persist()
            return
        }

        isGenerating = true
        let prompt = PromptComposer.compose(profile: profile, newestUserText: text)

        let filename = profile.modelFilename?.lowercased() ?? ""
        let isTinyModel = filename.contains("0.5b")
        let maxNewTokens = isTinyModel ? 180 : 220
        let temperature: Float = isTinyModel ? 0.80 : 0.86
        let topP: Float = isTinyModel ? 0.92 : 0.94

        do {
            let answer = try await engine.complete(
                prompt: prompt,
                maxNewTokens: maxNewTokens,
                temperature: temperature,
                topP: topP
            )
            profile.messages.append(ChatMessage(
                role: .assistant,
                content: cleanGeneratedReply(answer)
            ))
            touchRelevantMemories(for: text)
            persist()
        } catch {
            profile.messages.append(ChatMessage(
                role: .assistant,
                content: "My tiny local brain tripped over itself 😭 \(error.localizedDescription)"
            ))
            lastError = error.localizedDescription
            persist()
        }

        isGenerating = false
    }

    private func cleanGeneratedReply(_ raw: String) -> String {
        let normalized = raw.replacingOccurrences(of: "\r\n", with: "\n")
        var kept: [String] = []

        for line in normalized.components(separatedBy: "\n") {
            let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
            let lower = trimmed.lowercased()

            if lower.contains("<|im_start|>") || lower.contains("<|im_end|>") {
                if kept.isEmpty { continue }
                break
            }

            let isUserRole = lower == "star" || lower == "user" ||
                lower.hasPrefix("star:") || lower.hasPrefix("user:")
            if isUserRole {
                if kept.isEmpty { continue }
                break
            }

            let isAssistantRole = lower == "vex" || lower == "assistant" ||
                lower.hasPrefix("vex:") || lower.hasPrefix("assistant:")
            if isAssistantRole {
                if kept.isEmpty {
                    if let colon = trimmed.firstIndex(of: ":") {
                        let payload = String(trimmed[trimmed.index(after: colon)...])
                            .trimmingCharacters(in: .whitespacesAndNewlines)
                        if !payload.isEmpty { kept.append(payload) }
                    }
                    continue
                }
                break
            }

            kept.append(line)
        }

        let cleaned = kept.joined(separator: "\n")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return cleaned.isEmpty ? "Brain fart 😭🖤 Try me again." : cleaned
    }

    private func touchRelevantMemories(for text: String) {
        let ids = Set(MemoryEngine.retrieve(query: text, from: profile.memories, limit: 10).map(\.id))
        let now = Date()
        for index in profile.memories.indices where ids.contains(profile.memories[index].id) {
            profile.memories[index].lastUsedAt = now
            profile.memories[index].useCount += 1
        }
    }

    func clearChat() {
        profile.messages = [
            ChatMessage(role: .assistant, content: "Fresh chat, same glitter-coated little brain. 💕✨")
        ]
        persist()
    }

    func importBrain(from url: URL) {
        do {
            try store.importBrain(from: url, into: &profile)
            persist()
        } catch {
            lastError = "Brain import failed: \(error.localizedDescription)"
        }
    }

    func makeBackup() {
        do {
            exportURL = try store.exportBackup(profile)
        } catch {
            lastError = "Backup failed: \(error.localizedDescription)"
        }
    }

    func rememberLastExchange() {
        guard !profile.messages.isEmpty else { return }
        let chunk = profile.messages.suffix(2).map {
            "\($0.role == .user ? "Star" : "Vex"): \($0.content)"
        }.joined(separator: " | ")

        profile.memories = MemoryEngine.deduplicatedAppend(
            BrainMemory(text: chunk, kind: .note, importance: 0.7),
            to: profile.memories
        )
        persist()
    }
}
