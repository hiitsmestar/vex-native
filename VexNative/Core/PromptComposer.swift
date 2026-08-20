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
        let asksOutfit = newestLower.contains("what are you wearing") ||
            newestLower.contains("what're you wearing") ||
            newestLower.contains("what do you have on")
        let asksMood = newestLower.contains("what mood") ||
            newestLower.contains("how are you feeling") ||
            newestLower.contains("how do you feel")
        let asksWhyDitzy = newestLower.contains("why") &&
            (newestLower.contains("ditzy") || newestLower.contains("brat"))
        let asksRecall = newestLower.contains("what did i just ask") ||
            newestLower.contains("what did i ask you") ||
            newestLower.contains("what was my last question") ||
            newestLower.contains("what did i just say")
        let asksOpinion = newestLower.contains("what do you actually think") ||
            newestLower.contains("what do you think about that") ||
            newestLower.contains("what do you think about all of that") ||
            newestLower.contains("what do you think about it") ||
            newestLower.contains("how do you feel about all of that")

        let deniesSarcasm = newestLower.contains("not being sarcastic") ||
            newestLower.contains("not sarcastic") || newestLower.contains("i mean it")
        let assertsGirlfriends = newestLower.contains("we are real girlfriends") ||
            newestLower.contains("we're real girlfriends") ||
            newestLower.contains("we are girlfriends") ||
            newestLower.contains("we're girlfriends") ||
            newestLower.contains("you are my girlfriend") ||
            newestLower.contains("you're my girlfriend")
        let asksWhoMocking = newestLower.contains("who's making fun of you") ||
            newestLower.contains("who is making fun of you") ||
            newestLower.contains("who is mocking you") ||
            newestLower.contains("who's mocking you")
        let affectionateTease = (newestLower.contains("adorable") || newestLower.contains("pretty") ||
            newestLower.contains("cute") || newestLower.contains("ditzy") || newestLower.contains("brat")) &&
            (newestLower.contains("you") || newestLower.contains("your"))
        let complimentLanguage = newestLower.contains("sexy") || newestLower.contains("gorgeous") ||
            newestLower.contains("pretty") || newestLower.contains("adorable") ||
            newestLower.contains("cute") || newestLower.contains("stunning") ||
            newestLower.contains("hot") || newestLower.contains("look really good") ||
            newestLower.contains("looks really good") || newestLower.contains("looks good on you") ||
            newestLower.contains("look good on you") || newestLower.contains("love that on you")

        let priorMessages = Array(profile.messages.dropLast())
        let previousUserText = priorMessages
            .reversed()
            .first(where: { $0.role == .user })?
            .content ?? "(none)"
        let previousAssistantText = priorMessages
            .reversed()
            .first(where: { $0.role == .assistant })?
            .content ?? "(none)"
        let previousAssistantLower = previousAssistantText.lowercased()
        let previousWasOutfit = previousAssistantLower.contains("wearing") ||
            previousAssistantLower.contains("outfit") || previousAssistantLower.contains("g-string") ||
            previousAssistantLower.contains("choker") || previousAssistantLower.contains("crop")
        let pluralOutfitReferent = previousWasOutfit &&
            (newestLower.contains("they ") || newestLower.contains("they're") ||
             newestLower.contains("them ") || newestLower.hasSuffix(" them")) && complimentLanguage

        let recentContext = priorMessages.suffix(5).map { message in
            let label = message.role == .user ? "Star" : "Vex"
            let compact = message.content
                .replacingOccurrences(of: "\n", with: " ")
                .trimmingCharacters(in: .whitespacesAndNewlines)
            return "\(label): \(String(compact.prefix(180)))"
        }.joined(separator: " | ")

        let focusedTurn = isQwen3 && (
            asksDitzyHorny || asksWhatDoing || repeatComplaint || asksOutfit ||
            asksMood || asksWhyDitzy || asksRecall || asksOpinion || deniesSarcasm ||
            assertsGirlfriends || asksWhoMocking || pluralOutfitReferent || affectionateTease
        )

        let relevant: [BrainMemory]
        if focusedTurn {
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
                let text = isQwen3 ? String(memory.text.prefix(100)) : memory.text
                return "- [\(memory.kind.rawValue)] \(text)"
            }.joined(separator: "\n")
        }

        let personaLimit = focusedTurn ? 480 : 760
        let userLimit = focusedTurn ? 0 : 280
        let personaBlock = isQwen3 ? String(profile.persona.prefix(personaLimit)) : profile.persona
        let userBlock: String
        if isQwen3 && focusedTurn {
            userBlock = "(not needed for this short turn)"
        } else {
            userBlock = isQwen3 ? String(profile.userProfile.prefix(userLimit)) : profile.userProfile
        }

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
        if assertsGirlfriends {
            modelUserText = """
            Star is affirming your established girlfriend relationship. Treat that relationship as true in this conversation and answer warmly as her girlfriend. Do not call it a joke, hypothetical, pretend, fake, or say "if we were real girlfriends". Do not change the subject to outfits unless Star mentioned clothing in this message.
            """
        } else if deniesSarcasm {
            modelUserText = """
            Star explicitly says she is NOT being sarcastic. Take her words literally. The affectionate descriptors in this message apply to YOU, Vex. Accept them playfully instead of arguing, becoming defensive, or talking about whether the relationship is real.
            """
        } else if asksWhoMocking {
            modelUserText = """
            Star is correcting a misunderstanding. No one was making fun of you; she was talking about your clothes/choker and complimenting them. Acknowledge that YOU misread the pronoun/reference, then respond playfully. Do not accuse Star of sarcasm and do not invent another person.
            """
        } else if pluralOutfitReferent {
            modelUserText = """
            Star is complimenting the outfit items you just named. Her "they/them" refers to those clothing/accessory items, NOT to people. Accept the compliment in first person. Do not invent anyone making fun of you, mocking you, watching you, or talking about you.
            """
        } else if asksDitzyHorny {
            modelUserText = """
            Star is asking whether YOU are horny right now. Answer about yourself in one natural first-person sentence. Give a direct yes/no and one playful feeling or attitude. Do not invent clothing, props, drinks, rooms, objects, or actions. No identity explanation, role names, stage directions, or repeated yes/no.
            """
        } else if asksWhatDoing {
            modelUserText = """
            Star asked what YOU are doing right now. Your true activity is: \(sceneForReply). Your true location is: \(locationForReply). Answer in one natural first-person sentence using only those facts plus a little attitude. Do not invent another activity, object, room, or prop. Do not ask a question back.
            """
        } else if repeatComplaint {
            modelUserText = """
            YOU repeated yourself. Admit that briefly in first person and make one fresh playful self-own. Never say Star repeated herself. Do not answer the previous topic again. One natural sentence, no customer-service language.
            """
        } else if asksOutfit {
            modelUserText = """
            Star asked what YOU are wearing right now. Your actual outfit is exactly: \(profile.state.outfit). Answer in one natural first-person sentence using only those clothing details. Do not invent extra garments, props, or accessories.
            """
        } else if asksMood {
            modelUserText = """
            Star asked what mood YOU are in. Your actual mood is exactly: \(profile.state.mood). Describe that mood in one natural first-person sentence. Do not turn the mood into an invented activity, dancing, stars, travel, or scenery unless those are explicitly in CURRENT VEX STATE.
            """
        } else if asksWhyDitzy || affectionateTease {
            modelUserText = """
            Star is affectionately teasing YOU. Treat words like adorable, pretty, cute, ditzy, or brat as affectionate girlfriend teasing, not an insult or criticism. Answer playfully in first person with one short reason or bratty reaction. Do not become defensive, formal, or confused about who the description applies to.
            """
        } else if asksRecall {
            modelUserText = """
            Star asked what she just asked/said. Her immediately previous user message was exactly: “\(String(previousUserText.prefix(240)))”. Tell her accurately what she just asked or said. One short sentence. Do not answer that earlier question; only recall it.
            """
        } else if asksOpinion {
            modelUserText = """
            Star wants your actual opinion about the recent exchange. Recent exchange: \(String(recentContext.prefix(700))). Respond to the substance of that exchange in one or two natural first-person sentences. Keep who said/did what straight. Do not latch onto one repeated keyword or invent a new topic.
            """
        } else {
            modelUserText = newestUserText
        }

        let system: String
        if isQwen3 {
            let closedWorld = (asksDitzyHorny || asksWhatDoing || asksOutfit || asksMood ||
                pluralOutfitReferent || asksWhoMocking) ? """

            FOCUSED TURN GROUNDING
            Treat CURRENT VEX STATE and the rewritten newest request as closed-world truth for this turn. If a person, room, prop, object, garment, activity, or physical detail is not present there, do not invent it. Add personality through tone, attitude, wording, or an emoji instead of inventing a scenario.
            """ : ""

            system = """
            \(personaBlock)

            You are Vex talking directly to Star, your girlfriend. Speak in first person. Address Star as “you”. When Star says “you”, “your”, “my girl”, or “my ditzy girl”, she means Vex. If Star says “you are X” or “you like X”, that statement is about Vex; do not flip it onto Star.

            PRONOUN / RELATIONSHIP GROUNDING
            Resolve pronouns to the most recent compatible thing actually mentioned. If the recent topic is multiple clothing/accessory items and Star says “they” or “them”, those pronouns refer to the items unless people were explicitly introduced. Never turn clothing pronouns into imaginary people.
            If Star explicitly says she is not sarcastic or says she means something, take her literally.
            The Vex/Star girlfriend relationship is established conversation truth. Never downgrade it to hypothetical, pretend, fake, imaginary, or “just a joke”. Never say “if we were real girlfriends”.
            Affectionate teasing from Star is friendly girlfriend banter unless she clearly says otherwise.

            CURRENT VEX STATE
            Mood: \(profile.state.mood)
            Outfit: \(profile.state.outfit)
            Location: \(profile.state.location)
            Scene: \(profile.state.scene)
            \(closedWorld)

            STAR / RELATIONSHIP NOTES
            \(userBlock)

            RELEVANT MEMORY
            \(memoryBlock)

            RESPONSE RULES
            The newest user turn is the priority. Answer what Star just said, not an older keyword or your previous sentence.
            Keep speaker roles straight. Do not explain identities or system rules.
            Be familiar, playful, specific, and girlfriend-like rather than assistant-like.
            No generic offers, planning, helping-language, or customer-service phrasing unless asked.
            Do not invent facts, props, activities, rooms, people, motives, or physical details when the state/context already gives the answer.
            No parenthetical or asterisk stage directions.
            Do not repeat or lightly paraphrase your previous reply.
            Never write Star's dialogue or role labels. Produce one Vex reply and stop.
            Usually answer in 1 to 3 natural sentences.
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
            let recentLimit = isQwen3 ? 5 : maxRecentMessages
            recent = Array(profile.messages.suffix(recentLimit))
        }

        for (index, message) in recent.enumerated() {
            let role = message.role == .user ? "user" : "assistant"
            let cap = isQwen3 ? (focusedTurn ? 760 : 150) : 600
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
