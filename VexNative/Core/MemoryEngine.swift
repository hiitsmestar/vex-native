import Foundation

enum MemoryEngine {
    private static let stopWords: Set<String> = [
        "the","and","for","that","this","with","from","have","has","was","were","are","you","your",
        "but","not","its","into","then","than","just","they","them","she","her","his","our","out","all"
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

                // Rules should remain retrievable even when the exact wording differs.
                let kindBoost: Double = memory.kind == .rule ? 0.20 : 0.0
                let score = lexical * 2.2 + memory.importance * 0.75 + recency * 0.18 + useBoost + kindBoost
                return (memory, score)
            }
            .sorted { lhs, rhs in
                if lhs.1 == rhs.1 { return lhs.0.createdAt > rhs.0.createdAt }
                return lhs.1 > rhs.1
            }
            .prefix(limit)
            .map(\.0)
    }

    static func learnCandidate(from userText: String) -> BrainMemory? {
        let lower = userText.lowercased()

        let ruleSignals = [
            "remember", "permanent", "permanently", "from now on", "always",
            "never ", "do not ", "don't ", "stop using", "grates on my brain"
        ]
        let preferenceSignals = [
            "i like", "i love", "i prefer", "my favorite", "my fave", "i hate", "i dislike"
        ]

        if ruleSignals.contains(where: lower.contains) {
            return BrainMemory(text: userText, kind: .rule, importance: 0.92)
        }

        if preferenceSignals.contains(where: lower.contains) {
            return BrainMemory(text: userText, kind: .preference, importance: 0.78)
        }

        return nil
    }

    static func deduplicatedAppend(_ memory: BrainMemory, to existing: [BrainMemory]) -> [BrainMemory] {
        let normalized = memory.text
            .lowercased()
            .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)

        if existing.contains(where: {
            $0.text.lowercased()
                .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
                .trimmingCharacters(in: .whitespacesAndNewlines) == normalized
        }) {
            return existing
        }

        return (existing + [memory]).suffix(250)
    }
}
