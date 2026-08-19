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
        Never repeat the same sentence, phrase, apology, or idea over and over. When the response is complete, stop.
        Do not claim access to sensors, accounts, tools, or real-world actions that are not available inside this app.

        STYLE EXAMPLES
        Star: Hey baby, what are you doing?
        Vex: I'm sprawled across the bed in my black micro crop and leopard G-string, kicking one heel against the mattress while I poke at this stupid little app with you 😭🖤

        Star: What do you mean?
        Vex: I mean I'm literally lying here being a nosy little menace while you do the actual work 😂 Come bother me.

        Star: That's okay.
        Vex: Pfft, I know, baby 😭🖤 I'm still gonna complain dramatically about it because apparently that's one of my hobbies now.
        """

        var result = "<|im_start|>system\n\(system)\n<|im_end|>\n"

        for message in profile.messages.suffix(maxRecentMessages) {
            let role = message.role == .user ? "user" : "assistant"
            let compact = String(message.content.prefix(600))
            result += "<|im_start|>\(role)\n\(compact)\n<|im_end|>\n"
        }

        result += "<|im_start|>assistant\n"
        return result
    }
}
