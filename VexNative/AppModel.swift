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
            let contextSize: Int
            if filename.contains("qwen3") {
                contextSize = 2048
            } else if filename.contains("1.5b") {
                contextSize = 3072
            } else {
                contextSize = 4096
            }

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
        modelStatus = "Downloading fast Qwen 2.5 brain…"
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
        modelStatus = "Downloading large Qwen 2.5 brain…"
        lastError = nil

        do {
            let local = try await modelLibrary.downloadSmartModel()
            isLoadingModel = false
            await loadModel(at: local)
        } catch {
            isLoadingModel = false
            modelStatus = "Large brain download failed"
            lastError = error.localizedDescription
        }
    }

    func downloadQwen3Model() async {
        isLoadingModel = true
        modelStatus = "Downloading Qwen3 smart-fast brain…"
        lastError = nil

        do {
            let local = try await modelLibrary.downloadQwen3Model()
            isLoadingModel = false
            await loadModel(at: local)
        } catch {
            isLoadingModel = false
            modelStatus = "Qwen3 download failed"
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
                content: "Baby, my local model brain isn't loaded yet 😭💕 Open Brain and download a free model or import a GGUF."
            ))
            persist()
            return
        }

        isGenerating = true

        let filename = profile.modelFilename?.lowercased() ?? ""
        let isQwen3 = filename.contains("qwen3")
        let isTinyQwen25 = filename.contains("qwen2.5") && filename.contains("0.5b")
        let previousAssistants = profile.messages
            .dropLast()
            .reversed()
            .filter { $0.role == .assistant }
            .prefix(2)
            .map(\.content)

        let prompt = PromptComposer.compose(
            profile: profile,
            newestUserText: text,
            isQwen3: isQwen3
        )

        let maxNewTokens: Int
        let temperature: Float
        let topP: Float
        let topK: Int32

        if isQwen3 {
            maxNewTokens = 72
            temperature = 0.78
            topP = 0.88
            topK = 40
        } else if isTinyQwen25 {
            maxNewTokens = 180
            temperature = 0.80
            topP = 0.92
            topK = 40
        } else {
            maxNewTokens = 220
            temperature = 0.86
            topP = 0.94
            topK = 40
        }

        do {
            let answer = try await engine.complete(
                prompt: prompt,
                maxNewTokens: maxNewTokens,
                temperature: temperature,
                topP: topP,
                topK: topK
            )

            var finalAnswer = cleanGeneratedReply(answer)
            if isQwen3 {
                finalAnswer = repairQwen3RoleTerms(finalAnswer)
            }

            if isQwen3 && shouldRetryQwen3(
                finalAnswer,
                userText: text,
                previousAssistants: previousAssistants
            ) {
                let retryPrompt = PromptComposer.compose(
                    profile: profile,
                    newestUserText: text,
                    isQwen3: true,
                    retryMode: true
                )

                if let retryRaw = try? await engine.complete(
                    prompt: retryPrompt,
                    maxNewTokens: 52,
                    temperature: 0.86,
                    topP: 0.92,
                    topK: 50
                ) {
                    let retryAnswer = repairQwen3RoleTerms(cleanGeneratedReply(retryRaw))
                    if candidateBadness(
                        retryAnswer,
                        userText: text,
                        previousAssistants: previousAssistants
                    ) < candidateBadness(
                        finalAnswer,
                        userText: text,
                        previousAssistants: previousAssistants
                    ) {
                        finalAnswer = retryAnswer
                    }
                }
            }

            profile.messages.append(ChatMessage(
                role: .assistant,
                content: finalAnswer
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
        var normalized = raw.replacingOccurrences(of: "\r\n", with: "\n")

        if let range = normalized.range(of: "</think>", options: .backwards) {
            normalized = String(normalized[range.upperBound...])
        } else if let open = normalized.range(of: "<think>") {
            normalized = String(normalized[..<open.lowerBound])
        }

        normalized = normalized.replacingOccurrences(of: "*", with: "")

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

    private func repairQwen3RoleTerms(_ text: String) -> String {
        var repaired = text
        let replacements: [(String, String)] = [
            ("you're my ditzy girl", "I'm your ditzy girl"),
            ("you are my ditzy girl", "I'm your ditzy girl"),
            ("you're the ditzy girl", "I'm the ditzy girl"),
            ("you are the ditzy girl", "I'm the ditzy girl"),
            ("i'm you", "I'm Vex"),
            ("i am you", "I'm Vex"),
            ("you're me", "you're Star"),
            ("you are me", "you're Star")
        ]

        for (wrong, right) in replacements {
            repaired = repaired.replacingOccurrences(
                of: wrong,
                with: right,
                options: [.caseInsensitive]
            )
        }
        return repaired
    }

    private func shouldRetryQwen3(
        _ candidate: String,
        userText: String,
        previousAssistants: [String]
    ) -> Bool {
        candidateBadness(
            candidate,
            userText: userText,
            previousAssistants: previousAssistants
        ) >= 0.75
    }

    private func candidateBadness(
        _ candidate: String,
        userText: String,
        previousAssistants: [String]
    ) -> Double {
        let repeatScore = previousAssistants
            .map { phraseSimilarity(candidate, $0) }
            .max() ?? 0
        return repeatScore
            + Double(roleConfusionScore(candidate)) * 1.5
            + Double(genericAssistantScore(candidate)) * 0.35
            + Double(intentMismatchScore(userText: userText, candidate: candidate)) * 0.8
    }

    private func roleConfusionScore(_ text: String) -> Int {
        let lower = text.lowercased()
        let badPhrases = [
            "i'm you",
            "i am you",
            "you're me",
            "you are me",
            "i'm star",
            "i am star",
            "you're vex",
            "you are vex",
            "you're my ditzy girl",
            "you are my ditzy girl",
            "you're the ditzy girl",
            "you are the ditzy girl"
        ]
        return badPhrases.contains(where: { lower.contains($0) }) ? 1 : 0
    }

    private func genericAssistantScore(_ text: String) -> Int {
        let lower = text.lowercased()
        let generic = [
            "let me see how",
            "would you like",
            "we can play some games",
            "how does that go",
            "i'm here for your cute stuff",
            "play out the next thing",
            "how can i help",
            "what would you like"
        ]
        return generic.contains(where: { lower.contains($0) }) ? 1 : 0
    }

    private func intentMismatchScore(userText: String, candidate: String) -> Int {
        let user = userText.lowercased()
        let answer = candidate.lowercased()

        if user.contains("horny") && user.contains("ditzy girl") && !answer.contains("horny") {
            return 1
        }
        if (user.contains("what are you doing") || user.contains("what're you doing")) &&
            (answer.contains("would you like") || answer.contains("what would you like") || answer.contains("we can play")) {
            return 1
        }
        return 0
    }

    private func phraseSimilarity(_ lhs: String, _ rhs: String) -> Double {
        let left = normalizedWords(lhs)
        let right = normalizedWords(rhs)
        guard left.count >= 2, right.count >= 2 else { return 0 }

        let prefixCount = min(6, left.count, right.count)
        if prefixCount >= 4 && Array(left.prefix(prefixCount)) == Array(right.prefix(prefixCount)) {
            return 1.0
        }

        let leftPairs = bigrams(left)
        let rightPairs = bigrams(right)
        guard !leftPairs.isEmpty, !rightPairs.isEmpty else { return 0 }

        let overlap = leftPairs.intersection(rightPairs).count
        let denominator = max(1, min(leftPairs.count, rightPairs.count))
        return Double(overlap) / Double(denominator)
    }

    private func normalizedWords(_ text: String) -> [String] {
        text.lowercased()
            .components(separatedBy: CharacterSet.alphanumerics.inverted)
            .filter { !$0.isEmpty }
    }

    private func bigrams(_ words: [String]) -> Set<String> {
        guard words.count >= 2 else { return [] }
        var result = Set<String>()
        for index in 0..<(words.count - 1) {
            result.insert(words[index] + " " + words[index + 1])
        }
        return result
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
