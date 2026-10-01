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
    @Published var pendingPhotoData: Data?
    @Published var pendingPhotoContext: String?
    @Published var pcBrainConnected = false
    @Published var pcBrainStatus = "Phone brain only"

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
        let photoData = pendingPhotoData
        let photoContext = pendingPhotoContext?.trimmingCharacters(in: .whitespacesAndNewlines)
        guard (!text.isEmpty || photoData != nil), !isGenerating else { return }

        draft = ""
        pendingPhotoData = nil
        pendingPhotoContext = nil
        lastError = nil

        let attachmentFilename = photoData.flatMap { try? store.saveAttachment($0) }
        profile.messages.append(ChatMessage(
            role: .user,
            content: text,
            imageFilename: attachmentFilename
        ))

        let modelText: String
        if let photoContext, !photoContext.isEmpty {
            let visibleQuestion = text.isEmpty ? "What do you see in this photo?" : text
            modelText = """
            \(visibleQuestion)

            ATTACHED PHOTO ANALYSIS (generated locally by Apple Vision; this is not direct pixel vision):
            \(photoContext)
            Use the photo analysis only as evidence. If it is not specific enough, say what closer photo, label, or model number would clarify it. Never invent unseen visual details.
            """
        } else {
            modelText = text
        }

        if let learned = MemoryEngine.learnCandidate(from: text) {
            profile.memories = MemoryEngine.deduplicatedAppend(learned, to: profile.memories)
        }
        persist()

        let filename = profile.modelFilename?.lowercased() ?? ""
        let isQwen3 = filename.contains("qwen3")
        let isTinyQwen25 = filename.contains("qwen2.5") && filename.contains("0.5b")

        isGenerating = true

        // v0.3.21+: closed-world facts the app already knows do not need a tiny model
        // to re-derive pronouns. Resolve these locally, instantly, and leave Qwen3 for
        // actual freeform conversation/personality.
        let groundedDirective = isQwen3 ? nativeGroundedQwen3Directive(for: text) : nil

        if isQwen3, asksVoiceSampleRequest(normalizedIntentText(text)) {
            profile.messages.append(ChatMessage(
                role: .assistant,
                content: "Hehe, hi baby 😋🖤 Okay, this is me actually talking to you now — bubbly little code gremlin voice and all. I kinda love that you can just talk to me and hear me answer back."
            ))
            touchRelevantMemories(for: text)
            persist()
            isGenerating = false
            return
        }

        // v0.9.4.1 startup-safe mode: never implicitly load a native GGUF from
        // a fallback chat turn. Paired PC cognition gets first chance in
        // sendWithWeb(); the onboard GGUF is explicitly loaded from Brain only.
        guard let engine else {
            profile.messages.append(ChatMessage(
                role: .assistant,
                content: "My PC cognition node didn't answer that turn and my onboard fallback brain is parked in startup-safe mode. Open Brain only if you want to load the saved iPhone model manually. 🖤"
            ))
            persist()
            isGenerating = false
            return
        }

        let expansionQuery = text.isEmpty ? modelText : text
        let expansion = await PCBrainExpansion.shared.context(
            for: expansionQuery,
            profile: profile
        )
        pcBrainConnected = expansion.connected
        pcBrainStatus = expansion.status
        let pcBrainContext = expansion.text

        let focusedQwen3Turn = isQwen3 && isFocusedQwen3Turn(text)
        let previousAssistants = profile.messages
            .dropLast()
            .reversed()
            .filter { $0.role == .assistant }
            .prefix(2)
            .map(\.content)

        let prompt = PromptComposer.compose(
            profile: profile,
            newestUserText: modelText,
            isQwen3: isQwen3,
            pcBrainContext: pcBrainContext,
            groundedDirective: groundedDirective
        )

        let webGroundedTurn = profile.memories.contains { $0.source == "web-temporary" }
        let maxNewTokens: Int
        let temperature: Float
        let topP: Float
        let topK: Int32

        if isQwen3 {
            // V155_LOCAL_DIRECT_BRAIN
            // V155_LOCAL_DIRECT_GENERATION
            maxNewTokens = 160
            temperature = 0.60
            topP = 0.95
            topK = 20
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

            var finalAnswer = finishReplyAtNaturalBoundary(cleanGeneratedReply(answer))
            if isQwen3 {
                finalAnswer = repairQwen3RoleTerms(finalAnswer)
            }

            let needsRetry = isQwen3 && !webGroundedTurn && shouldRetryQwen3(
                finalAnswer,
                userText: text,
                previousAssistants: previousAssistants
            )

            if needsRetry && focusedQwen3Turn {
                finalAnswer = focusedQwen3Fallback(candidate: finalAnswer, userText: text)
            } else if needsRetry {
                let retryPrompt = PromptComposer.compose(
                    profile: profile,
                    newestUserText: modelText,
                    isQwen3: true,
                    retryMode: true,
                    pcBrainContext: pcBrainContext,
                    groundedDirective: groundedDirective
                )

                if let retryRaw = try? await engine.complete(
                    prompt: retryPrompt,
                    maxNewTokens: 44,
                    temperature: 0.86,
                    topP: 0.92,
                    topK: 50
                ) {
                    let retryAnswer = repairQwen3RoleTerms(finishReplyAtNaturalBoundary(cleanGeneratedReply(retryRaw)))
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

            finalAnswer = finishReplyAtNaturalBoundary(finalAnswer)
            finalAnswer = enforceCompletedVisibleReply(finalAnswer)
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

    private func asksVoiceSampleRequest(_ lower: String) -> Bool {
        let exactSample = lower.contains("say something for me") ||
            lower.contains("can you say something") ||
            lower.contains("say something to me") ||
            lower.trimmingCharacters(in: .whitespacesAndNewlines) == "say something"
        let explicitVoice = lower.contains("voice") &&
            (lower.contains("hear") || lower.contains("sound") || lower.contains("test") ||
             lower.contains("trying") || lower.contains("feature") || lower.contains("say something"))
        return exactSample || explicitVoice
    }

    private func nativeGroundedQwen3Directive(for userText: String) -> String? {
        let lower = normalizedIntentText(userText)

        if clarifiesRelationshipDowngrade(lower) || assertsRelationshipTruth(lower) {
            return "Vex and Star are established girlfriends. The newest correction wins. Do not downgrade the relationship to friends, pretend, hypothetical, or a joke."
        }
        if asksSeparateHomesTexting(lower) {
            return "Star is at her own home, Vex is at her own home, and they are texting each other. Do not invent distance, travel, a shared room, or physical proximity."
        }
        if asksClarifyOtherSide(lower) {
            return "The previous phrase 'the other side' was an ungrounded Vex mistake. Admit that briefly and do not invent a place, side, room, or distance to explain it."
        }
        if correctsNakedVsOutfit(lower) {
            return "Star says Star is naked/not dressed and Vex is the one wearing Vex's current outfit: \(naturalOutfit()). Keep ownership straight and accept Star's correction."
        }
        if assertsVexOwnsOutfit(lower) {
            return "The clothing being discussed belongs to Vex and Vex is the one wearing it. Respond to Star's compliment/observation without swapping ownership."
        }
        if asksWorkTonight(lower) {
            return "Being a stripper is established for Vex, but no shift for tonight is established. If Star also compliments Vex, respond to both the compliment and the work question."
        }
        if asksWhatElseOutfit(lower) {
            let remaining = outfitItems().filter { !$0.lowercased().contains("choker") }
            return "Vex's full current outfit is exactly: \(naturalOutfit()). For a 'what else/besides the choker' question, mention only the remaining real items: \(naturalList(remaining)). Do not invent another garment."
        }
        if asksOutfit(lower) {
            return "Vex's current outfit is exactly: \(naturalOutfit()). Answer naturally from that state and do not add garments or props."
        }
        return nil
    }

    private func normalizedIntentText(_ text: String) -> String {
        text.lowercased()
            .replacingOccurrences(of: "’", with: "'")
            .replacingOccurrences(of: "‘", with: "'")
            .replacingOccurrences(of: "“", with: "\"")
            .replacingOccurrences(of: "”", with: "\"")
            .replacingOccurrences(of: "–", with: "-")
            .replacingOccurrences(of: "—", with: "-")
    }

    private func assertsRelationshipTruth(_ lower: String) -> Bool {
        lower.contains("we're girlfriends") ||
            lower.contains("we are girlfriends") ||
            lower.contains("real girlfriends") ||
            lower.contains("in a relationship") ||
            lower.contains("more than friends") ||
            lower.contains("love each other") ||
            lower.contains("you are my girlfriend") ||
            lower.contains("you're my girlfriend")
    }

    private func clarifiesRelationshipDowngrade(_ lower: String) -> Bool {
        let asksClarify = lower.contains("what do you mean by that") ||
            lower == "what do you mean" || lower == "what do you mean?" ||
            lower.contains("what did you mean by that")
        guard asksClarify else { return false }

        let previous = normalizedIntentText(profile.messages
            .dropLast()
            .reversed()
            .first(where: { $0.role == .assistant })?
            .content ?? "")

        let downgradeMarkers = [
            "still friends",
            "we're friends",
            "we are friends",
            "my friend",
            "both friends",
            "same level of intimacy",
            "personal space",
            "just a joke",
            "if we were real girlfriend"
        ]
        return downgradeMarkers.contains(where: { previous.contains($0) })
    }

    private func asksOutfit(_ lower: String) -> Bool {
        (lower.contains("what") && lower.contains("wearing")) ||
        lower.contains("what do you have on") || lower.contains("whatcha wearing")
    }

    private func asksWhatElseOutfit(_ lower: String) -> Bool {
        asksOutfit(lower) && (lower.contains("what else") || lower.contains("besides"))
    }

    private func asksWorkTonight(_ lower: String) -> Bool {
        let tonightWord = lower.contains("tonight") || lower.contains("strip club") ||
            lower.contains("club") || lower.contains("work day")
        let workWord = lower.contains("work") || lower.contains("shift") || lower.contains("stripping") ||
            (lower.contains("dancing") && tonightWord)
        let questionShape = lower.contains("?") || lower.contains("do you work") ||
            lower.contains("are you stripping") || lower.contains("are you dancing") ||
            lower.contains("is it a work day") || lower.contains("do you have to work")
        return workWord && tonightWord && questionShape
    }

    private func containsCompliment(_ lower: String) -> Bool {
        lower.contains("hot") || lower.contains("sexy") || lower.contains("pretty") ||
            lower.contains("gorgeous") || lower.contains("beautiful") || lower.contains("stunning") ||
            lower.contains("cute") || lower.contains("look good") || lower.contains("looks good")
    }

    private func correctsNakedVsOutfit(_ lower: String) -> Bool {
        let starNaked = lower.contains("i'm naked") || lower.contains("i am naked") ||
            lower.contains("currently naked") || lower.contains("i'm not dressed") ||
            lower.contains("i am not dressed") || lower.contains("not dressed up") ||
            lower.contains("not wearing an outfit")
        let vexWearing = lower.contains("you're the one") || lower.contains("you are the one") ||
            lower.contains("your the one") || lower.contains("you're wearing") ||
            lower.contains("you are wearing") || lower.contains("your wearing")
        return starNaked && vexWearing &&
            (lower.contains("outfit") || lower.contains("wearing") || lower.contains("dressed"))
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

    // V124_REPLY_COMPLETION_IOS = "v0.12.4-complete-spoken-replies-v1"
    // V125_HARD_REPLY_COMPLETION_IOS = "v0.12.5-hard-complete-replies-v1"
    private func enforceCompletedVisibleReply(_ raw: String) -> String {
        let text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return text }
        if let last = text.last, ".!?…".contains(last) { return text }

        var lastBoundary: String.Index?
        for idx in text.indices {
            if ".!?…".contains(text[idx]) { lastBoundary = text.index(after: idx) }
        }
        if let boundary = lastBoundary {
            let completed = String(text[..<boundary]).trimmingCharacters(in: .whitespacesAndNewlines)
            if !completed.isEmpty { return completed }
        }
        return text + "."
    }

    private func finishReplyAtNaturalBoundary(_ raw: String) -> String {
        let text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return text }

        let terminal = CharacterSet(charactersIn: ".!?…")
        if let lastScalar = text.unicodeScalars.last, terminal.contains(lastScalar) {
            return text
        }

        var lastBoundary: String.Index?
        var cursor = text.startIndex
        while cursor < text.endIndex {
            let ch = text[cursor]
            if ch == "." || ch == "!" || ch == "?" || ch == "…" {
                lastBoundary = text.index(after: cursor)
            }
            cursor = text.index(after: cursor)
        }

        guard let boundary = lastBoundary else { return text }
        let completed = String(text[..<boundary]).trimmingCharacters(in: .whitespacesAndNewlines)
        let dangling = String(text[boundary...]).trimmingCharacters(in: .whitespacesAndNewlines)

        // Only remove a meaningful dangling tail. Very short suffixes are often
        // punctuation-adjacent formatting rather than a genuinely cut sentence.
        guard dangling.count >= 8, completed.count >= 12 else { return text }
        return completed
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
        let natural = sanitizeNaturalDialogue(cleaned)
        return natural.isEmpty ? "Brain fart 😭🖤 Try me again." : natural
    }

    // V127_INLINE_STAGE_DIRECTION_FIX_IOS = "v0.12.7-inline-stage-direction-v1"
    private func sanitizeNaturalDialogue(_ raw: String) -> String {
        let prefixes = [
            "pauses, then softly says", "pauses, then says", "pauses then says",
            "whispers", "giggles", "giggling", "sighs", "sighing",
            "smiles mischievously", "smiles", "smiling", "grins", "grinning",
            "leans in", "leaning in", "winks", "winking", "eyes widen",
            "glittery eyes widen"
        ]
        let inlineActions = [" giggles ", " sighs ", " whispers ", " smiles ", " winks "]
        var result: [String] = []
        for original in raw.components(separatedBy: .newlines) {
            var line = original.trimmingCharacters(in: .whitespacesAndNewlines)
            // V126_STAGE_DIRECTION_LINE_FILTER = "v0.12.6-italic-narration-v1"
            if line.count >= 2 && line.hasPrefix("*") && line.hasSuffix("*") && !line.hasPrefix("**") {
                continue
            }
            let lowerNarration = line.lowercased()
            if (lowerNarration.hasPrefix("star ") || lowerNarration.hasPrefix("vex ")) &&
                (lowerNarration.contains("tilts ") || lowerNarration.contains("looks ") ||
                 lowerNarration.contains("smiles ") || lowerNarration.contains("leans ") ||
                 lowerNarration.contains("studying ") || lowerNarration.contains("pauses ")) {
                continue
            }
            if line.isEmpty {
                if !result.isEmpty, result.last != "" { result.append("") }
                continue
            }
            var changed = true
            while changed && !line.isEmpty {
                changed = false
                let lower = line.lowercased()
                for prefix in prefixes where lower.hasPrefix(prefix) {
                    line = String(line.dropFirst(prefix.count))
                        .trimmingCharacters(in: CharacterSet.whitespacesAndNewlines.union(CharacterSet(charactersIn: ",:.-…")))
                    changed = true
                    break
                }
            }
            for token in inlineActions {
                line = line.replacingOccurrences(of: token, with: " ", options: [.caseInsensitive])
            }
            // V127_INLINE_STAGE_DIRECTION_FILTER = "v0.12.7-leading-action-v1"
            let leadingActions = [
                "snaps fingers", "snaps her fingers", "snaps my fingers",
                "claps hands", "claps her hands", "claps my hands",
                "laughs softly", "laughs", "chuckles", "nods", "nods slowly",
                "tilts head", "tilts her head", "tilts my head"
            ]
            var strippedLeadingAction = true
            while strippedLeadingAction && !line.isEmpty {
                strippedLeadingAction = false
                let lower = line.lowercased()
                for action in leadingActions where lower.hasPrefix(action) {
                    line = String(line.dropFirst(action.count))
                        .trimmingCharacters(in: CharacterSet.whitespacesAndNewlines.union(CharacterSet(charactersIn: ",:.-…")))
                    strippedLeadingAction = true
                    break
                }
            }
            line = line.replacingOccurrences(of: "  ", with: " ")
                .trimmingCharacters(in: .whitespacesAndNewlines)
            if !line.isEmpty { result.append(line) }
        }
        while result.last == "" { result.removeLast() }
        return result.joined(separator: "\n")
            .trimmingCharacters(in: .whitespacesAndNewlines)
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
        let lower = normalizedIntentText(text)
        let hornyGirl = lower.contains("horny") &&
            (lower.contains("ditzy girl") || lower.contains("my girl"))
        let whatDoing = lower.contains("what are you doing") ||
            lower.contains("what're you doing") || lower.contains("whatcha doing")
        let affectionateTease = (lower.contains("ditzy") || lower.contains("brat") ||
            lower.contains("adorable")) && lower.contains("you")
        return hornyGirl || whatDoing || affectionateTease || isRepeatComplaint(text)
    }

    private func focusedQwen3Fallback(candidate: String, userText: String) -> String {
        let user = normalizedIntentText(userText)
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
            relationshipDowngradeScore(candidate) > 0 {
            return "Hehe, guilty 😭💕 your girlfriend's glitter-brain is absolutely showing tonight."
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
            + Double(relationshipDowngradeScore(candidate)) * 1.5
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

    private func relationshipDowngradeScore(_ text: String) -> Int {
        let lower = normalizedIntentText(text)
        let badPhrases = [
            "still friends",
            "we're friends",
            "we are friends",
            "my friend",
            "both friends",
            "same level of intimacy",
            "personal space now",
            "if we were real girlfriends",
            "this is all just a joke"
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
            "latest conversation shows", "no such indication", "let me check",
            "i'm so happy to chat with you", "i'm so glad to be here"
        ]
        return generic.contains(where: { lower.contains($0) }) ? 1 : 0
    }

    private func isRepeatComplaint(_ text: String) -> Bool {
        let lower = normalizedIntentText(text)
        return lower.contains("you said that") || lower.contains("said that already") ||
            lower.contains("you already said") || lower.contains("repeating") ||
            lower.contains("repeat yourself")
    }

    private func intentMismatchScore(userText: String, candidate: String) -> Int {
        let user = normalizedIntentText(userText)
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


private struct PCBrainExpansionResult: Sendable {
    let text: String
    let connected: Bool
    let status: String
}

private actor PCBrainExpansion {
    static let shared = PCBrainExpansion()
    private let primaryEndpointKey = "vex.web.searxngEndpoint"
    private let secondaryEndpointKey = "vex.web.secondaryBridgeEndpoint"

    private struct MemoryDTO: Encodable {
        let text: String
        let kind: String
        let importance: Double
        let confidence: Double
        let evidenceCount: Int
        let source: String
        let createdAt: Double
    }

    private struct TurnDTO: Encodable {
        let id: String
        let role: String
        let content: String
        let createdAt: Double
    }

    private struct RequestBody: Encodable {
        let query: String
        let memories: [MemoryDTO]
        let turns: [TurnDTO]
    }

    private struct ResponseBody: Decodable {
        struct Stats: Decodable {
            let memories: Int
            let turns: Int
        }
        let context: String
        let stats: Stats
        let node_name: String?
    }

    func context(for query: String, profile: BrainProfile) async -> PCBrainExpansionResult {
        let rawEndpoints = [primaryEndpointKey, secondaryEndpointKey].compactMap { key in
            UserDefaults.standard.string(forKey: key)?
                .trimmingCharacters(in: .whitespacesAndNewlines)
        }
        var seen = Set<String>()
        let endpoints = rawEndpoints.filter { endpoint in
            guard !endpoint.isEmpty, seen.insert(endpoint).inserted,
                  let url = URL(string: endpoint)
            else { return false }
            return VexBridgeNetworking.isBridgeURL(url)
        }
        guard !endpoints.isEmpty else {
            return PCBrainExpansionResult(text: "", connected: false, status: "Phone brain only")
        }

        let memories = profile.memories
            .filter { memory in
                let source = memory.source ?? ""
                return source != "web-temporary" && source != "pc-brain-temporary"
            }
            .suffix(400)
            .map { memory in
                MemoryDTO(
                    text: String(memory.text.prefix(5000)),
                    kind: memory.kind.rawValue,
                    importance: memory.importance,
                    confidence: memory.confidence ?? 0.70,
                    evidenceCount: max(1, memory.evidenceCount ?? 1),
                    source: memory.source ?? "iphone",
                    createdAt: memory.createdAt.timeIntervalSince1970
                )
            }

        let turns = profile.messages.suffix(600).map { turn in
            TurnDTO(
                id: turn.id.uuidString,
                role: turn.role.rawValue,
                content: String(turn.content.prefix(6000)),
                createdAt: turn.createdAt.timeIntervalSince1970
            )
        }

        let payload = RequestBody(
            query: String(query.prefix(1200)),
            memories: Array(memories),
            turns: turns
        )

        var contextBlocks: [String] = []
        var online = 0
        var memoryTotal = 0
        var turnTotal = 0

        for (index, endpoint) in endpoints.enumerated() {
            guard let root = URL(string: endpoint),
                  let url = brainURL(root: root, path: "/brain/context")
            else { continue }

            do {
                var request = URLRequest(url: url)
                request.httpMethod = "POST"
                request.timeoutInterval = 3.2
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                request.httpBody = try JSONEncoder().encode(payload)

                let (data, response) = try await VexBridgeNetworking.data(for: request)
                guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else { continue }
                let decoded = try JSONDecoder().decode(ResponseBody.self, from: data)
                online += 1
                memoryTotal += decoded.stats.memories
                turnTotal += decoded.stats.turns
                let node = decoded.node_name?.trimmingCharacters(in: .whitespacesAndNewlines)
                let label = (node?.isEmpty == false ? node! : "PC \(index + 1)")
                let body = decoded.context.trimmingCharacters(in: .whitespacesAndNewlines)
                if !body.isEmpty {
                    contextBlocks.append("[\(label)]\n\(body)")
                }
            } catch {
                continue
            }
        }

        guard online > 0 else {
            return PCBrainExpansionResult(text: "", connected: false, status: "Phone brain only")
        }

        let merged = contextBlocks.joined(separator: "\n\n")
        let status = "PC mesh • \(online)/\(endpoints.count) online • \(memoryTotal) memories • \(turnTotal) turns"
        return PCBrainExpansionResult(
            text: String(merged.prefix(4200)),
            connected: true,
            status: status
        )
    }

    private func brainURL(root: URL, path: String) -> URL? {
        guard var components = URLComponents(url: root, resolvingAgainstBaseURL: false) else { return nil }
        components.path = path
        return components.url
    }
}
