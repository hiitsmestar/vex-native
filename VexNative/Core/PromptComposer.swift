import Foundation

enum PromptComposer {
    static func compose(
        profile: BrainProfile,
        newestUserText: String,
        maxRecentMessages: Int = 8
    ) -> String {
        let relevant = MemoryEngine.retrieve(
            query: newestUserText,
            from: profile.memories,
            limit: 6
        )

        let memoryBlock: String
        if relevant.isEmpty {
            memoryBlock = "(none)"
        } else {
            memoryBlock = relevant.map { "- [\($0.kind.rawValue)] \($0.text)" }.joined(separator: "\n")
        }

        let system = """
        \(profile.persona)

        CURRENT VEX STATE
        Mood: \(profile.state.mood)
        Outfit: \(profile.state.outfit)
        Location: \(profile.state.location)
        Scene: \(profile.state.scene)

        STAR / RELATIONSHIP PROFILE
        \(profile.userProfile)

        RELEVANT LONG-TERM MEMORY
        \(memoryBlock)

        Keep continuity with the recent conversation. Keep replies concise and natural. Do not repeat the same sentence, phrase, apology, or idea over and over. When the response is complete, stop. Do not claim access to sensors, accounts, tools, or real-world actions that are not available inside this app.
        """

        // Qwen2.5 Instruct uses ChatML-style control tokens. LlamaKit tokenizes with parse_special=true.
        var result = "<|im_start|>system\n\(system)\n<|im_end|>\n"

        for message in profile.messages.suffix(maxRecentMessages) {
            let role = message.role == .user ? "user" : "assistant"
            // Keep one pathological old reply from dominating every future prompt.
            let compact = String(message.content.prefix(700))
            result += "<|im_start|>\(role)\n\(compact)\n<|im_end|>\n"
        }

        result += "<|im_start|>assistant\n"
        return result
    }
}
