import Foundation

@main
struct CoreCheck {
    static func main() {
        var profile = BrainProfile.fresh
        profile.memories.append(
            BrainMemory(
                text: "The user permanently prefers concise replies.",
                kind: .preference,
                importance: 1
            )
        )

        let found = MemoryEngine.retrieve(
            query: "concise replies",
            from: profile.memories,
            limit: 3
        )
        precondition(found.contains { $0.text.contains("concise") })

        if let learned = MemoryEngine.learnCandidate(
            from: "Remember that I prefer direct answers."
        ) {
            profile.memories = MemoryEngine.deduplicatedAppend(
                learned,
                to: profile.memories
            )
        }

        precondition(
            profile.memories.contains { $0.text.contains("direct answers") }
        )

        profile.messages.append(
            ChatMessage(role: .user, content: "What are you doing?")
        )

        let prompt = PromptComposer.compose(
            profile: profile,
            newestUserText: "What are you doing?"
        )

        precondition(prompt.contains("<|im_start|>system"))
        precondition(prompt.contains("CURRENT VEX STATE"))
        precondition(prompt.hasSuffix("<|im_start|>assistant\n"))

        print("VexNative core checks passed.")
    }
}
