import Foundation

enum MemoryEngine {
    private static let stopWords: Set<String> = [
        "the","and","for","that","this","with","from","have","has","was","were","are","you","your",
        "but","not","its","into","then","than","just","they","them","she","her","his","our","out","all",
        "star","vex","correction","learned","lesson","says","said"
    ]

    static func terms(in text: String) -> [String] {
        text.lowercased()
            .split { !$0.isLetter && !$0.isNumber && $0 != "'" }
            .map(String.init)
            .filter { $0.count > 2 && !stopWords.contains($0) }
    }

    static func retrieve(
        query: String,
        from memories: [BrainMemory],
        limit: Int = 10,
        now: Date = Date()
    ) -> [BrainMemory] {
        let queryTerms = Set(terms(in: query))
        guard !memories.isEmpty else { return [] }

        return memories
            .map { memory -> (BrainMemory, Double) in
                let memoryTerms = Set(terms(in: memory.text))
                let overlap = Double(queryTerms.intersection(memoryTerms).count)
                let union = max(1.0, Double(queryTerms.union(memoryTerms).count))
                let lexical = overlap / union

                let ageDays = max(0, now.timeIntervalSince(memory.createdAt) / 86_400)
                let recency = 1.0 / (1.0 + ageDays / 90.0)
                let useBoost = min(0.25, Double(memory.useCount) * 0.02)
                let confidence = memory.confidence ?? defaultConfidence(for: memory.kind)
                let evidence = max(1, memory.evidenceCount ?? 1)
                let evidenceBoost = min(0.24, log2(Double(evidence) + 1.0) * 0.07)

                // Rules and correction-derived lessons should remain retrievable even
                // when Star uses different wording later.
                let kindBoost: Double
                switch memory.kind {
                case .rule:
                    kindBoost = 0.24
                case .lesson:
                    kindBoost = 0.28
                default:
                    kindBoost = 0.0
                }

                let score = lexical * 2.2
                    + memory.importance * 0.70
                    + confidence * 0.52
                    + recency * 0.15
                    + useBoost
                    + evidenceBoost
                    + kindBoost
                return (memory, score)
            }
            .sorted { lhs, rhs in
                if lhs.1 == rhs.1 { return lhs.0.createdAt > rhs.0.createdAt }
                return lhs.1 > rhs.1
            }
            .prefix(limit)
            .map(\.0)
    }

    /// Learns only from fairly explicit user signals. The local model's own output
    /// is never treated as ground truth here, which prevents hallucinations from
    /// recursively teaching themselves.
    static func learnCandidate(from userText: String) -> BrainMemory? {
        let trimmed = userText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count >= 4 else { return nil }

        let lower = normalized(trimmed)

        let correctionSignals = [
            "no,", "no ", "actually", "i mean", "i meant", "that's not", "that isn't",
            "thats not", "you're the one", "you are the one", "your the one",
            "we're girlfriends", "we are girlfriends", "not just friends", "more than friends",
            "i'm naked", "i am naked", "neither of us", "you said that", "already said",
            "you already", "you got that wrong", "that's wrong", "thats wrong", "wrong person",
            "i'm at my", "i am at my", "you're at your", "you are at your"
        ]

        if correctionSignals.contains(where: { lower.contains($0) }) {
            return BrainMemory(
                text: "Star correction: \(trimmed)",
                kind: .lesson,
                importance: 0.96,
                confidence: 0.96,
                evidenceCount: 1,
                lastConfirmedAt: Date(),
                source: "user-correction"
            )
        }

        let ruleSignals = [
            "remember ", "remember that", "from now on", "permanently", "permanent ",
            "never say", "never call", "never use", "do not ", "don't ", "stop using",
            "grates on my brain"
        ]
        if ruleSignals.contains(where: { lower.contains($0) }) {
            return BrainMemory(
                text: trimmed,
                kind: .rule,
                importance: 0.94,
                confidence: 0.95,
                evidenceCount: 1,
                lastConfirmedAt: Date(),
                source: "user-explicit"
            )
        }

        let preferenceSignals = [
            "i like", "i love", "i prefer", "my favorite", "my favourite", "my fave",
            "i hate", "i dislike", "i don't like", "i dont like"
        ]
        if preferenceSignals.contains(where: { lower.contains($0) }) {
            return BrainMemory(
                text: trimmed,
                kind: .preference,
                importance: 0.80,
                confidence: 0.82,
                evidenceCount: 1,
                lastConfirmedAt: Date(),
                source: "user-preference"
            )
        }

        let explicitFactSignals = [
            "we live", "we're dating", "we are dating", "we're girlfriends", "we are girlfriends",
            "you work", "you are a stripper", "you're a stripper", "i live", "my name is"
        ]
        if explicitFactSignals.contains(where: { lower.contains($0) }) {
            return BrainMemory(
                text: trimmed,
                kind: .fact,
                importance: 0.82,
                confidence: 0.82,
                evidenceCount: 1,
                lastConfirmedAt: Date(),
                source: "user-fact"
            )
        }

        return nil
    }

    /// Adds a memory while reinforcing repeated evidence instead of making endless
    /// near-duplicate entries. Strong repeated corrections become increasingly hard
    /// for retrieval to ignore.
    static func deduplicatedAppend(_ memory: BrainMemory, to existing: [BrainMemory]) -> [BrainMemory] {
        var incoming = memory
        incoming.confidence = incoming.confidence ?? defaultConfidence(for: incoming.kind)
        incoming.evidenceCount = max(1, incoming.evidenceCount ?? 1)
        incoming.lastConfirmedAt = incoming.lastConfirmedAt ?? Date()

        var result = existing
        if let index = bestMergeIndex(for: incoming, in: result) {
            var merged = result[index]
            let oldEvidence = max(1, merged.evidenceCount ?? 1)
            let newEvidence = max(1, incoming.evidenceCount ?? 1)
            let oldConfidence = merged.confidence ?? defaultConfidence(for: merged.kind)
            let incomingConfidence = incoming.confidence ?? defaultConfidence(for: incoming.kind)

            merged.importance = min(1.0, max(merged.importance, incoming.importance) + 0.015)
            merged.confidence = min(1.0, max(oldConfidence, incomingConfidence) + 0.025)
            merged.evidenceCount = oldEvidence + newEvidence
            merged.lastConfirmedAt = Date()
            merged.source = merged.source ?? incoming.source

            // Prefer the clearer/more specific wording when both memories describe
            // essentially the same lesson.
            if incoming.text.count > merged.text.count && incoming.importance >= merged.importance - 0.05 {
                merged.text = incoming.text
            }
            result[index] = merged
        } else {
            result.append(incoming)
        }

        return consolidate(result, now: Date(), maxCount: 300)
    }

    /// Deterministic local consolidation: merges duplicates, reinforces repeated
    /// lessons, drops stale weak noise, and keeps high-authority rules intact.
    static func consolidate(
        _ memories: [BrainMemory],
        now: Date = Date(),
        maxCount: Int = 300
    ) -> [BrainMemory] {
        var merged: [BrainMemory] = []

        let ordered = memories.sorted {
            priorityScore($0, now: now) > priorityScore($1, now: now)
        }

        for original in ordered {
            var memory = original
            memory.confidence = memory.confidence ?? defaultConfidence(for: memory.kind)
            memory.evidenceCount = max(1, memory.evidenceCount ?? 1)

            if shouldDiscard(memory, now: now) { continue }

            if let index = bestMergeIndex(for: memory, in: merged) {
                var target = merged[index]
                target.importance = min(1.0, max(target.importance, memory.importance) + 0.01)
                target.confidence = min(
                    1.0,
                    max(target.confidence ?? 0.6, memory.confidence ?? 0.6) + 0.02
                )
                target.evidenceCount = max(1, target.evidenceCount ?? 1) + max(1, memory.evidenceCount ?? 1)
                target.lastConfirmedAt = [target.lastConfirmedAt, memory.lastConfirmedAt]
                    .compactMap { $0 }
                    .max()
                target.lastUsedAt = [target.lastUsedAt, memory.lastUsedAt]
                    .compactMap { $0 }
                    .max()
                target.useCount = max(target.useCount, memory.useCount)
                if memory.text.count > target.text.count && memory.importance >= target.importance - 0.05 {
                    target.text = memory.text
                }
                merged[index] = target
            } else {
                merged.append(memory)
            }
        }

        return Array(
            merged
                .sorted { priorityScore($0, now: now) > priorityScore($1, now: now) }
                .prefix(maxCount)
        )
    }

    static func learnedLessonCount(in memories: [BrainMemory]) -> Int {
        memories.filter { $0.kind == .lesson || ($0.source?.hasPrefix("user-") ?? false) }.count
    }

    static func reinforcedCount(in memories: [BrainMemory]) -> Int {
        memories.filter { ($0.evidenceCount ?? 1) > 1 }.count
    }

    private static func normalized(_ text: String) -> String {
        text.lowercased()
            .replacingOccurrences(of: "’", with: "'")
            .replacingOccurrences(of: "‘", with: "'")
            .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func normalizedKey(_ text: String) -> String {
        normalized(text)
            .replacingOccurrences(of: "star correction:", with: "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func bestMergeIndex(for incoming: BrainMemory, in existing: [BrainMemory]) -> Int? {
        let incomingKey = normalizedKey(incoming.text)
        let incomingTerms = Set(terms(in: incomingKey))

        var bestIndex: Int?
        var bestScore = 0.0

        for (index, candidate) in existing.enumerated() {
            guard compatibleKinds(incoming.kind, candidate.kind) else { continue }
            let candidateKey = normalizedKey(candidate.text)
            if candidateKey == incomingKey { return index }

            let candidateTerms = Set(terms(in: candidateKey))
            guard incomingTerms.count >= 2, candidateTerms.count >= 2 else { continue }
            let intersection = Double(incomingTerms.intersection(candidateTerms).count)
            let union = Double(max(1, incomingTerms.union(candidateTerms).count))
            let similarity = intersection / union
            if similarity >= 0.82 && similarity > bestScore {
                bestScore = similarity
                bestIndex = index
            }
        }
        return bestIndex
    }

    private static func compatibleKinds(_ lhs: MemoryKind, _ rhs: MemoryKind) -> Bool {
        if lhs == rhs { return true }
        let instructional: Set<MemoryKind> = [.rule, .lesson]
        return instructional.contains(lhs) && instructional.contains(rhs)
    }

    private static func defaultConfidence(for kind: MemoryKind) -> Double {
        switch kind {
        case .rule: return 0.92
        case .lesson: return 0.90
        case .preference: return 0.78
        case .fact: return 0.76
        case .scene: return 0.72
        case .note: return 0.62
        }
    }

    private static func shouldDiscard(_ memory: BrainMemory, now: Date) -> Bool {
        if memory.kind == .rule || memory.kind == .lesson { return false }
        let confidence = memory.confidence ?? defaultConfidence(for: memory.kind)
        let ageDays = now.timeIntervalSince(memory.createdAt) / 86_400
        return memory.importance < 0.38 && confidence < 0.45 && memory.useCount == 0 && ageDays > 120
    }

    private static func priorityScore(_ memory: BrainMemory, now: Date) -> Double {
        let confidence = memory.confidence ?? defaultConfidence(for: memory.kind)
        let evidence = Double(max(1, memory.evidenceCount ?? 1))
        let ageDays = max(0, now.timeIntervalSince(memory.createdAt) / 86_400)
        let recency = 1.0 / (1.0 + ageDays / 180.0)
        let kindBoost: Double = memory.kind == .rule ? 0.30 : (memory.kind == .lesson ? 0.34 : 0.0)
        return memory.importance * 0.9
            + confidence * 0.8
            + min(0.30, log2(evidence + 1.0) * 0.08)
            + min(0.20, Double(memory.useCount) * 0.015)
            + recency * 0.10
            + kindBoost
    }
}
