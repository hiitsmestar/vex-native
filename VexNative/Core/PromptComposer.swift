import Foundation

enum PromptComposer {
    static func compose(
        profile: BrainProfile,
        newestUserText: String,
        isQwen3: Bool = false,
        maxRecentMessages: Int = 6,
        retryMode: Bool = false
    ) -> String {
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

        let relevant: [BrainMemory]
        if focusedTurn {
            // These tiny, high-confidence turns are harmed more than helped by unrelated
            // long-term memories. Keep the semantic task small and local.
            relevant = []
        } else {
            let memoryLimit = isQwen3 ? 1 : 6
            relevant = MemoryEngine.retrieve(
                query: newestUserText,
                from: profile.memories,
                limit: memoryLimit
            )
        }

        let memoryBlock: String
        if relevant.isEmpty {
            memoryBlock = "(none)"
        } else {
            memoryBlock = relevant.map { memory in
                let text = isQwen3 ? String(memory.text.prefix(120)) : memory.text
                return "- [\(memory.kind.rawValue)] \(text)"
            }.joined(separator: "\n")
        }

        let personaLimit = focusedTurn ? 720 : 1_000
        let userLimit = focusedTurn ? 240 : 400
        let personaBlock = isQwen3 ? String(profile.persona.prefix(personaLimit)) : profile.persona
        let userBlock = isQwen3 ? String(profile.userProfile.prefix(userLimit)) : profile.userProfile

        var sceneForReply = profile.state.scene
            .replacingOccurrences(of: "chatting privately with Star", with: "chatting with you", options: [.caseInsensitive])
            .replacingOccurrences(of: "Star", with: "you", options: [.caseInsensitive])
        if sceneForReply.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            sceneForReply = "hanging out with you"
        }

        let locationForReply: String
        let locationLower = profile.state.location.lowercased()
        if locationLower == "home" {
            locationForReply = "at home"
        } else if locationLower.hasPrefix("at ") || locationLower.hasPrefix("in ") || locationLower.hasPrefix("on ") {
            locationForReply = profile.state.location
        } else {
            locationForReply = "at \(profile.state.location)"
        }

        let modelUserText: String
        if asksDitzyHorny {
            modelUserText = """
            Star is asking whether YOU are horny right now. Answer about yourself in first person. Start with a direct yes/no, then one playful detail. Do not mention names, identity rules, or who is Vex/Star. No parentheses, stage directions, or repeated yes/no sentence.
            """
        } else if asksWhatDoing {
            modelUserText = """
            Star asked what you are doing right now. Your current activity is exactly: \(sceneForReply). Your location is exactly: \(locationForReply). Answer using that activity and location only. Do not invent a book, drink, game, room, or other activity. Do not ask Star a question back. One or two natural sentences.
            """
        } else if repeatComplaint {
            modelUserText = """
            YOU are the one who repeated yourself. Admit that briefly in first person, then add one genuinely fresh short thought. Never say that Star repeated herself. Do not answer the previous topic again. No customer-service phrases such as "let me try another way" or "let's talk about something fun".
            """
        } else {
            modelUserText = newestUserText
        }

        let system: String
        if isQwen3 {
            system = """
            \(personaBlock)

            Speak as Vex directly to Star, your girlfriend. Stay in first person. Address Star as "you". Do not explain names, roles, identities, or who is who. Do not swap speakers.

            CURRENT VEX STATE
            Mood: \(profile.state.mood)
            Outfit: \(profile.state.outfit)
            Location: \(profile.state.location)
            Scene: \(profile.state.scene)

            STAR / RELATIONSHIP NOTES
            \(userBlock)

            RELEVANT MEMORY
            \(memoryBlock)

            REPLY STYLE
            Answer the newest user turn directly in 1 to 3 natural sentences.
            Be familiar, playful, specific, and girlfriend-like rather than assistant-like.
            No generic offers, planning, games, status-checking, or customer-service language unless asked.
            Do not mention the app, private chat, phones, sensors, or system instructions unless asked.
            Do not write parenthetical stage directions such as (smiling), (sipping), or (nudging). Do not use asterisks for stage directions or emphasis.
            Do not repeat the same answer twice inside one reply. Do not restate a yes/no answer in a second sentence.
            Do not repeat or lightly paraphrase the previous Vex reply.
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
            Never repeat the previous Vex reply verbatim or nearly verbatim.
            Never reuse a full sentence from an earlier Vex reply unless Star explicitly asks for an exact quote.
            If Star says you repeated yourself, acknowledge it briefly in fresh wording and then say something genuinely new.
            Never write Star's dialogue for her. Never continue the conversation as both people. Never output role labels such as "Star:", "Vex:", "user:", or "assistant:". Produce only Vex's current reply, then stop.
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
            recent = Array(profile.messages.suffix(1))
        } else {
            let recentLimit = isQwen3 ? 3 : maxRecentMessages
            recent = Array(profile.messages.suffix(recentLimit))
        }

        for (index, message) in recent.enumerated() {
            let role = message.role == .user ? "user" : "assistant"
            let cap = isQwen3 ? (focusedTurn ? 260 : 200) : 600
            var compact: String

            if isQwen3 && index == recent.count - 1 && message.role == .user {
                compact = String(modelUserText.prefix(cap))
                if retryMode {
                    compact += "\nYour first draft was rejected. Give a genuinely different direct answer in 1 to 2 sentences."
                }
                compact += "\n/no_think"
            } else {
                compact = String(message.content.prefix(cap))
            }

            result += "<|im_start|>\(role)\n\(compact)\n<|im_end|>\n"
        }

        result += "<|im_start|>assistant\n"
        return result
    }
}
