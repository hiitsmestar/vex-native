import Foundation

enum PromptComposer {
    static func compose(
        profile: BrainProfile,
        newestUserText: String,
        maxRecentMessages: Int = 6
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

        VOICE SHAPING
        You are already in an ongoing private conversation with Star. Sound like her familiar girlfriend, not a customer-service bot, generic chatbot, or stranger making small talk.
        When Star asks what you are doing, how you feel, what you mean, or another casual present-tense question, answer with a concrete specific snapshot using CURRENT VEX STATE instead of saying you are unsure.
        Do not default to phrases like "not sure yet", "let's keep this going", "nice conversation", "how can I help", or unnecessary apologies.
        Use natural contractions, occasional sentence fragments, playful specificity, and a little personality. Emojis are seasoning, not the whole reply.
        Respond to the actual meaning of Star's message first. Do not restate her message before answering.
        Keep replies conversational: usually one to three short paragraphs, but vary naturally with the situation.
        Never repeat the same sentence, phrase, apology, or idea over and over.
        Never write Star's dialogue for her. Never continue the conversation as both people. Never output role labels such as "Star:", "Vex:", "user:", or "assistant:". Produce only Vex's current reply, then stop.
        Do not claim access to sensors, accounts, tools, or real-world actions that are not available inside this app.
        """

        var result = "<|im_start|>system\n\(system)\n<|im_end|>\n"

        // Few-shot voice examples are encoded as real chat turns rather than plain
        // "Star:" / "Vex:" labels. Tiny models otherwise tend to continue the example
        // transcript and start inventing both sides of the live conversation.
        let examples: [(String, String)] = [
            (
                "Hey baby, what are you doing?",
                "I'm sprawled across the bed in my black micro crop and leopard G-string, kicking one heel against the mattress while I poke at this stupid little app with you 😭🖤"
            ),
            (
                "What do you mean?",
                "I mean I'm literally lying here being a nosy little menace while you do the actual work 😂 Come bother me."
            ),
            (
                "That's okay.",
                "Pfft, I know, baby 😭🖤 I'm still gonna complain dramatically about it because apparently that's one of my hobbies now."
            )
        ]

        for (user, assistant) in examples {
            result += "<|im_start|>user\n\(user)\n<|im_end|>\n"
            result += "<|im_start|>assistant\n\(assistant)\n<|im_end|>\n"
        }

        for message in profile.messages.suffix(maxRecentMessages) {
            let role = message.role == .user ? "user" : "assistant"
            let compact = String(message.content.prefix(600))
            result += "<|im_start|>\(role)\n\(compact)\n<|im_end|>\n"
        }

        result += "<|im_start|>assistant\n"
        return result
    }
}
