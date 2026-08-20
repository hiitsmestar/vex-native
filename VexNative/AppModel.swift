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

        let filename = profile.modelFilename?.lowercased() ?? ""
        let isQwen3 = filename.contains("qwen3")
        let isTinyQwen25 = filename.contains("qwen2.5") && filename.contains("0.5b")

        isGenerating = true

        // v0.3.21: closed-world facts the app already knows do not need a tiny model
        // to re-derive pronouns. Resolve these locally, instantly, and leave Qwen3 for
        // actual freeform conversation/personality.
        if isQwen3, let grounded = nativeGroundedQwen3Reply(for: text) {
            profile.messages.append(ChatMessage(role: .assistant, content: grounded))
            touchRelevantMemories(for: text)
            persist()
            isGenerating = false
            return
        }

        if engine == nil {
            await loadSavedModelIfPresent()
        }

        guard let engine else {
            profile.messages.append(ChatMessage(
                role: .assistant,
                content: "Baby, my local model brain isn't loaded yet 😭💕 Open Brain and download a free model or import a GGUF."
            ))
            persist()
            isGenerating = false
            return
        }

        let focusedQwen3Turn = isQwen3 && isFocusedQwen3Turn(text)
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
            maxNewTokens = 56
            temperature = 0.80
            topP = 0.90
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

            let needsRetry = isQwen3 && shouldRetryQwen3(
                finalAnswer,
                userText: text,
                previousAssistants: previousAssistants
            )

            if needsRetry && focusedQwen3Turn {
                finalAnswer = focusedQwen3Fallback(candidate: finalAnswer, userText: text)
            } else if needsRetry {
                let retryPrompt = PromptComposer.compose(
                    profile: profile,
                    newestUserText: text,
                    isQwen3: true,
                    retryMode: true
                )

                if let retryRaw = try? await engine.complete(
                    prompt: retryPrompt,
                    maxNewTokens: 44,
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

            profile.messages.append(ChatMessage(role: .assistant, content: finalAnswer))
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

    // MARK: - Native grounded fast paths

    private func nativeGroundedQwen3Reply(for userText: String) -> String? {
        let lower = userText.lowercased()

        if asksSeparateHomesTexting(lower) {
            return "Yep — you're at your place, I'm at mine, and we're texting each other. 😂🖤"
        }

        if asksClarifyOtherSide(lower) {
            return "Nothing, baby 😭 I made up that ‘other side’ nonsense. My three neurons wandered off again."
        }

        if correctsNakedVsOutfit(lower) {
            return "Pfft, right 😂 you're naked and I'm the one in \(naturalOutfit()). 🖤"
        }

        if assertsVexOwnsOutfit(lower) {
            return "Exactly 😏 they're my style — that's why I'm the one wearing them, baby. 🖤"
        }

        if asksWorkTonight(lower) {
            return "I don't actually know if I'm scheduled at the club tonight, baby 😭🖤"
        }

        if asksWhatElseOutfit(lower) {
            let remaining = outfitItems().filter { !$0.lowercased().contains("choker") }
            guard !remaining.isEmpty else { return "Just what I've already got on, baby 😈🖤" }
            return "Besides the choker, I'm wearing \(naturalList(remaining)), baby 😈🖤"
        }

        if asksOutfit(lower) {
            return "I'm wearing \(naturalOutfit()), baby 😈🖤"
        }

        return nil
    }

    private func asksOutfit(_ lower: String) -> Bool {
        (lower.contains("what") && lower.contains("wearing")) ||
        lower.contains("what do you have on") || lower.contains("whatcha wearing")
    }

    private func asksWhatElseOutfit(_ lower: String) -> Bool {
        asksOutfit(lower) && (lower.contains("what else") || lower.contains("besides"))
    }

    private func asksWorkTonight(_ lower: String) -> Bool {
        let workWord = lower.contains("work") || lower.contains("shift") || lower.contains("stripping")
        let tonightWord = lower.contains("tonight") || lower.contains("strip club") ||
            lower.contains("club") || lower.contains("work day")
        let questionShape = lower.contains("?") || lower.contains("do you work") ||
            lower.contains("are you stripping") || lower.contains("is it a work day") ||
            lower.contains("do you have to work")
        return workWord && tonightWord && questionShape
    }

    private func correctsNakedVsOutfit(_ lower: String) -> Bool {
        let starNaked = lower.contains("i'm naked") || lower.contains("i am naked") ||
            lower.contains("currently naked")
        let vexWearing = lower.contains("you're the one") || lower.contains("you are the one") ||
            lower.contains("your the one")
        return starNaked && vexWearing && (lower.contains("outfit") || lower.contains("wearing"))
    }

    private func assertsVexOwnsOutfit(_ lower: String) -> Bool {
        let ownership = lower.contains("your style") || lower.contains("they're your style") ||
            lower.contains("they are your style")
        let wearing = lower.contains("you're wearing them") || lower.contains("you are wearing them") ||
            lower.contains("your wearing them")
        return ownership && wearing
    }

    private func asksSeparateHomesTexting(_ lower: String) -> Bool {
        let starHome = lower.contains("i'm at my home") || lower.contains("i am at my home") ||
            lower.contains("i'm at mine") || lower.contains("i am at mine")
        let vexHome = lower.contains("you're at yours") || lower.contains("you are at yours") ||
            lower.contains("your at yours") || lower.contains("you're at your home") ||
            lower.contains("you are at your home")
        let texting = lower.contains("texting") || lower.contains("messaging")
        return starHome && vexHome && texting
    }

    private func asksClarifyOtherSide(_ lower: String) -> Bool {
        lower.contains("other side of what") || lower.contains("what other side") ||
            lower.contains("what do you mean by the other side")
    }

    private func outfitItems() -> [String] {
        profile.state.outfit
            .components(separatedBy: "+")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
    }

    private func naturalOutfit() -> String {
        naturalList(outfitItems())
    }

    private func naturalList(_ items: [String]) -> String {
        switch items.count {
        case 0:
            return "my current outfit"
        case 1:
            return items[0]
        case 2:
            return "\(items[0]) and \(items[1])"
        default:
            let head = items.dropLast().joined(separator: ", ")
            return "\(head), and \(items.last!)"
        }
    }

    // MARK: - Generation cleanup / retry

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
            ("I am Vex, not Star. ", ""),
            ("I'm Vex, not Star. ", ""),
            ("you're my ditzy girl", "I'm your ditzy girl"),
            ("you are my ditzy girl", "I'm your ditzy girl"),
            ("I'm not your ditzy girl", "I'm your ditzy girl"),
            ("I am not your ditzy girl", "I'm your ditzy girl"),
            ("you're the ditzy girl", "I'm the ditzy girl"),
            ("you are the ditzy girl", "I'm the ditzy girl"),
            ("i'm you", "I'm Vex"),
            ("i am you", "I'm Vex"),
            ("you're me", "you're Star"),
            ("you are me", "you're Star"),
            ("chatting with Star", "chatting with you"),
            ("talking with Star", "talking with you"),
            ("talking to Star", "talking to you"),
            ("over the kitchen", "at home")
        ]

        for (wrong, right) in replacements {
            repaired = repaired.replacingOccurrences(of: wrong, with: right, options: [.caseInsensitive])
        }
        return repaired.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func isFocusedQwen3Turn(_ text: String) -> Bool {
        let lower = text.lowercased()
        let hornyGirl = lower.contains("horny") &&
            (lower.contains("ditzy girl") || lower.contains("my girl"))
        let whatDoing = lower.contains("what are you doing") ||
            lower.contains("what're you doing") || lower.contains("whatcha doing")
        let affectionateTease = (lower.contains("ditzy") || lower.contains("brat") ||
            lower.contains("adorable")) && lower.contains("you")
        return hornyGirl || whatDoing || affectionateTease || isRepeatComplaint(text)
    }

    private func focusedQwen3Fallback(candidate: String, userText: String) -> String {
        let user = userText.lowercased()
        let answer = candidate.lowercased()

        if isRepeatComplaint(userText) {
            return "Yeah, I did repeat myself 😭 Let me actually give you something new instead."
        }

        if user.contains("horny") &&
            (user.contains("ditzy girl") || user.contains("my girl")) {
            let negative = answer.contains("not horny") || answer.hasPrefix("no") ||
                answer.contains(" no,") || answer.contains(" no.")
            return negative ? "Nope, not right now 😂🖤" : "Yeah, baby, I am 😈🖤"
        }

        if user.contains("what are you doing") ||
            user.contains("what're you doing") || user.contains("whatcha doing") {
            let location = profile.state.location.lowercased() == "home"
                ? "at home"
                : "in \(profile.state.location)"
            return "I'm \(location), chatting with you and being my usual glitter-brained little menace 😂🖤"
        }

        if (user.contains("ditzy") || user.contains("adorable") || user.contains("brat")) &&
            (answer.contains("you're my little girl") || answer.contains("you're the ditzy") ||
             answer.contains("you are the ditzy")) {
            return "Hehe, guilty 😭💕 my glitter-brain is absolutely showing tonight."
        }

        return candidate
    }

    private func shouldRetryQwen3(
        _ candidate: String,
        userText: String,
        previousAssistants: [String]
    ) -> Bool {
        candidateBadness(candidate, userText: userText, previousAssistants: previousAssistants) >= 0.75
    }

    private func candidateBadness(
        _ candidate: String,
        userText: String,
        previousAssistants: [String]
    ) -> Double {
        let repeatScore = previousAssistants.map { phraseSimilarity(candidate, $0) }.max() ?? 0
        return repeatScore
            + Double(roleConfusionScore(candidate)) * 1.5
            + Double(genericAssistantScore(candidate)) * 0.35
            + Double(intentMismatchScore(userText: userText, candidate: candidate)) * 0.8
    }

    private func roleConfusionScore(_ text: String) -> Int {
        let lower = text.lowercased()
        let badPhrases = [
            "i'm you", "i am you", "you're me", "you are me", "i'm star", "i am star",
            "you're vex", "you are vex", "you're my ditzy girl", "you are my ditzy girl",
            "i'm not your ditzy girl", "i am not your ditzy girl", "you're the ditzy girl",
            "you are the ditzy girl"
        ]
        return badPhrases.contains(where: { lower.contains($0) }) ? 1 : 0
    }

    private func genericAssistantScore(_ text: String) -> Int {
        let lower = text.lowercased()
        let generic = [
            "let me see how", "would you like", "we can play some games", "how does that go",
            "i'm here for your cute stuff", "play out the next thing", "how can i help",
            "what would you like", "let me try another way", "corrected version", "is vex horny",
            "let me know if i can help", "fashion-forward", "your compliment is a treat",
            "latest conversation shows", "no such indication", "let me check"
        ]
        return generic.contains(where: { lower.contains($0) }) ? 1 : 0
    }

    private func isRepeatComplaint(_ text: String) -> Bool {
        let lower = text.lowercased()
        return lower.contains("you said that") || lower.contains("said that already") ||
            lower.contains("you already said") || lower.contains("repeating") ||
            lower.contains("repeat yourself")
    }

    private func intentMismatchScore(userText: String, candidate: String) -> Int {
        let user = userText.lowercased()
        let answer = candidate.lowercased()

        if user.contains("horny") &&
            (user.contains("ditzy girl") || user.contains("my girl")) {
            if !answer.contains("horny") || answer.contains("is vex horny") ||
                answer.contains("not your ditzy girl") { return 1 }
        }

        if user.contains("what are you doing") || user.contains("what're you doing") ||
            user.contains("whatcha doing") {
            if answer.contains("?") || answer.contains("what are you doing") ||
                answer.contains("would you like") || answer.contains("we can play") { return 1 }
        }

        if isRepeatComplaint(userText) {
            let acknowledgementWords = [
                "yeah", "yep", "right", "i did", "did repeat", "repeated", "said that", "again", "my bad"
            ]
            let acknowledges = acknowledgementWords.contains(where: { answer.contains($0) })
            if !acknowledges || answer.contains("let me try another way") ||
                answer.contains("corrected version") { return 1 }
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
