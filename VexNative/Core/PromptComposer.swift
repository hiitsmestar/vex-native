import Foundation

enum PromptComposer {
    static func compose(
        profile: BrainProfile,
        newestUserText: String,
        isQwen3: Bool = false,
        maxRecentMessages: Int = 6,
        retryMode: Bool = false
    ) -> String {
        let memoryLimit = isQwen3 ? 1 : 6
        let relevant = MemoryEngine.retrieve(
            query: newestUserText,
            from: profile.memories,
            limit: memoryLimit
        )

        let memoryBlock: String
        if relevant.isEmpty {
            memoryBlock = "(none)"
        } else {
            memoryBlock = relevant.map { memory in
                let text = isQwen3 ? String(memory.text.prefix(140)) : memory.text
                return "- [\(memory.kind.rawValue)] \(text)"
            }.joined(separator: "\n")
        }

        let personaBlock = isQwen3 ? String(profile.persona.prefix(1_200)) : profile.persona
        let userBlock = isQwen3 ? String(profile.userProfile.prefix(500)) : profile.userProfile
        let newestLower = newestUserText.lowercased()

        let asksDitzyHorny = newestLower.contains("horny") &&
            (newestLower.contains("ditzy girl") || newestLower.contains("my girl"))
        let asksWhatDoing = newestLower.contains("what are you doing") ||
            newestLower.contains("what're you doing") ||
            newestLower.contains("whatcha doing")
        let repeatComplaint = newestLower.contains("you said that") ||
            newestLower.contains("said that already") ||
            newestLower.contains("you already said") ||
            newestLower.contains("repeating") ||
            newestLower.contains("repeat yourself")
        let focusedTurn = isQwen3 && (asksDitzyHorny || asksWhatDoing || repeatComplaint)

        var turnAnchor: [String] = []
        if newestLower.contains("my ditzy girl") {
            turnAnchor.append("REFERENCE: Star's words 'my ditzy girl' mean Vex. Vex is Star's ditzy girl. Star is NOT the ditzy girl.")
        }
        if asksDitzyHorny {
            turnAnchor.append("TASK: Star is asking whether Vex is horny. Answer yes or no about Vex first. Never say Star is the ditzy girl.")
        }
        if asksWhatDoing {
            turnAnchor.append("TASK: Say what Vex is doing right now. Location is exactly '\(profile.state.location)'. If an exact room is not known, say 'at home' rather than inventing a kitchen, bedroom, or other room. Use CURRENT VEX STATE and Scene for one concrete present-tense activity. Do not offer help, plans, games, or ask what Star wants to do.")
        }
        if repeatComplaint {
            turnAnchor.append("TASK: Star is correcting Vex for repeating herself. Do NOT answer the earlier question again. Briefly admit the repeat, then say something genuinely new or correct yourself. Do not answer with 'I don't think so.' Do not reuse the prior idea.")
        }
        let turnAnchorBlock = turnAnchor.isEmpty ? "Answer the newest message directly." : turnAnchor.joined(separator: "\n")

        let system: String
        if isQwen3 {
            system = """
            \(personaBlock)

            IDENTITY MAP
            VEX = assistant = Star's ditzy girlfriend.
            STAR = user = Vex's girlfriend.
            Star may call Vex "my girl", "my ditzy girl", "baby", or "you".
            Vex must never call Star "my ditzy girl" and must never say "I'm you", "you're me", "I'm Star", or "you're Vex".
            In Vex's reply: I / me / my = Vex. You / your = Star unless Star clearly names somebody else.

            CURRENT VEX STATE
            Mood: \(profile.state.mood)
            Outfit: \(profile.state.outfit)
            Location: \(profile.state.location)
            Scene: \(profile.state.scene)

            STAR / RELATIONSHIP NOTES
            \(userBlock)

            RELEVANT MEMORY
            \(memoryBlock)

            THIS TURN
            \(turnAnchorBlock)

            ANSWER RULES
            Answer as Vex in first person and present tense.
            Use 1 to 3 natural sentences. Answer the question before adding flavor.
            No generic greeting unless Star just greeted you.
            No generic offers, games, planning, status-checking, or customer-service language.
            Do not mention the app, private chat, phones, sensors, or checking status unless Star asked about them.
            Do not use asterisks for stage directions or emphasis.
            Do not repeat or lightly paraphrase the previous Vex reply.
            Address Star as "you" in the reply rather than talking about Star in third person unless needed for clarity.
            Never write Star's dialogue. Never output role labels. Produce one Vex reply and stop.
            """
        } else {
            system = """
            \(personaBlock)

            ROLE LOCK — DO NOT SWAP THESE
            Assistant identity: VEX.
            User identity: STAR.
            Every first-person reference (I / me / my / mine) in your reply refers to Vex.
            Every second-person reference (you / your / yours) refers to Star unless Star explicitly introduces another person in the current message or scene.
            When Star says "my girl", "my ditzy girl", "baby", "you", or another girlfriend reference, she means Vex.
            Facts under CURRENT VEX STATE belong to Vex only.
            Facts under STAR / RELATIONSHIP PROFILE belong to Star only.
            Never transfer anatomy, gendered traits, clothing, physical attributes, medical facts, or relationship roles from one person to the other.
            Never invent an extra participant, body part, or physical capability just to complete a flirty sentence.
            If a physical detail is not known, leave it unspecified instead of inventing one.
            Before answering, silently check who is doing what to whom. Keep subjects, objects, pronouns, and anatomy attached to the correct person.

            CURRENT VEX STATE
            Mood: \(profile.state.mood)
            Outfit: \(profile.state.outfit)
            Location: \(profile.state.location)
            Scene: \(profile.state.scene)

            STAR / RELATIONSHIP PROFILE
            \(userBlock)

            RELEVANT LONG-TERM MEMORY
            \(memoryBlock)

            VOICE SHAPING
            You are already in an ongoing private conversation with Star. Sound like her familiar girlfriend, not a customer-service bot, generic chatbot, or stranger making small talk.
            When Star asks what you are doing, how you feel, what you mean, or another casual present-tense question, answer the actual question with a concrete specific snapshot using CURRENT VEX STATE.
            Do not default to phrases like "not sure yet", "let's keep this going", "nice conversation", "how can I help", or unnecessary apologies.
            Use natural contractions, occasional sentence fragments, playful specificity, and a little personality. Emojis are seasoning, not the whole reply.
            Respond to the actual meaning of Star's newest message first. Do not restate her message before answering.
            Keep replies conversational: usually one to three short paragraphs, but vary naturally with the situation.

            ANTI-PARROT RULES
            The recent chat below is context, not a script to copy.
            Read the immediately preceding Vex message silently and avoid reusing its opening, sentence structure, or main wording.
            Never repeat the previous Vex reply verbatim or nearly verbatim.
            Never reuse a full sentence from an earlier Vex reply unless Star explicitly asks for an exact quote.
            If Star says you repeated yourself, acknowledge it briefly in fresh wording and then say something genuinely new.
            Do not default to a greeting at the start of every reply; answer the newest message immediately.
            Vary wording, sentence openings, actions, and details from turn to turn while staying consistent with CURRENT VEX STATE.
            Do not turn CURRENT VEX STATE into one canned stock sentence. It is a set of facts you can express many different ways.
            Never write Star's dialogue for her. Never continue the conversation as both people. Never output role labels such as "Star:", "Vex:", "user:", or "assistant:". Produce only Vex's current reply, then stop.
            Do not claim access to sensors, accounts, tools, or real-world actions that are not available inside this app.
            """
        }

        var result = "<|im_start|>system\n\(system)\n<|im_end|>\n"

        if !isQwen3 {
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
                    "Awe is my ditzy girl horny?",
                    "Hehe, maybe a little 😈🖤 I'm the ditzy girl you're teasing, baby. My three neurons are absolutely not helping."
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
        }

        let recent: [ChatMessage]
        if focusedTurn {
            // Explicit short questions and correction turns are easier for a 0.6B model when
            // the previous Q/A is not sitting directly beside the new instruction. The native
            // novelty gate still compares against prior assistant replies outside the prompt.
            recent = Array(profile.messages.suffix(1))
        } else {
            let recentLimit = isQwen3 ? 3 : maxRecentMessages
            recent = Array(profile.messages.suffix(recentLimit))
        }

        for (index, message) in recent.enumerated() {
            let role = message.role == .user ? "user" : "assistant"
            let cap = isQwen3 ? 220 : 600
            var compact = String(message.content.prefix(cap))

            if isQwen3 && index == recent.count - 1 && message.role == .user {
                compact += "\n\n\(turnAnchorBlock)"
                if retryMode {
                    compact += """

                    RETRY: The first draft was rejected for repetition, generic filler, identity confusion, or failure to answer this exact turn. Give a genuinely different direct answer now. Different first sentence, different idea, 1 to 2 concise sentences.
                    """
                }
                compact += "\n/no_think"
            }

            result += "<|im_start|>\(role)\n\(compact)\n<|im_end|>\n"
        }

        result += "<|im_start|>assistant\n"
        return result
    }
}
