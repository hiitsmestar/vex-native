#!/usr/bin/env python3
from pathlib import Path

# v0.7.10 device-test patch: robust visual intent and contextual picture follow-ups.
path = Path("VexNative/ContentView.swift")
text = path.read_text(encoding="utf-8")

# v0.7.9 correctly added the visual pipeline, but it cleaned the visual wording
# out of the query before asking shouldUseWeb(). That meant a recognized request
# could immediately stop looking like a visual request. Keep visual intent as an
# explicit routing decision instead of rediscovering it from the cleaned query.
old_guard = '''        guard web.shouldUseWeb(for: resolvedVisibleInput) else {\n            await send()\n            return\n        }\n'''
new_guard = '''        guard visualRequest || web.shouldUseWeb(for: resolvedVisibleInput) else {\n            await send()\n            return\n        }\n'''
if old_guard not in text:
    raise SystemExit("visual routing guard not found")
text = text.replace(old_guard, new_guard, 1)

# Replace brittle exact-phrase visual detection with category detection. This
# catches natural language such as "get me a pic", "part picture I asked for",
# "grab an image", and "I want to see what it looks like".
start = text.find("    func wantsVisualReply(_ text: String) -> Bool {")
end = text.find("    func wantsGeneratedVisual(_ text: String) -> Bool {", start)
if start < 0 or end < 0:
    raise SystemExit("wantsVisualReply function markers not found")
new_wants = r'''    func wantsVisualReply(_ text: String) -> Bool {
        let lower = normalize(text)
        let tokens = Set(lower
            .split(whereSeparator: { !$0.isLetter && !$0.isNumber })
            .map(String.init))

        let imageWords: Set<String> = [
            "pic", "pics", "picture", "pictures", "photo", "photos",
            "image", "images", "diagram", "diagrams", "visual", "visuals"
        ]
        let requestWords: Set<String> = [
            "show", "get", "send", "find", "give", "grab", "fetch", "pull",
            "make", "draw", "generate", "see", "look", "want", "need"
        ]
        let followupWords: Set<String> = [
            "asked", "request", "requested", "about", "where", "still", "part"
        ]

        let hasImageWord = !tokens.isDisjoint(with: imageWords)
        let hasRequestWord = !tokens.isDisjoint(with: requestWords)
        let hasFollowupWord = !tokens.isDisjoint(with: followupWords)
        let asksAppearance = lower.contains("look like") || lower.contains("looks like") ||
            lower.contains("what it looks like") || lower.contains("what that looks like") ||
            lower.contains("what this looks like") ||
            (lower.contains("see what") && lower.contains("look"))
        let contextualShow = lower.contains("show me where") ||
            lower.contains("can you show me") || lower.contains("could you show me")

        return (hasImageWord && (hasRequestWord || hasFollowupWord)) || asksAppearance || contextualShow
    }

'''
text = text[:start] + new_wants + text[end:]

# Make visual follow-ups inherit the prior user subject and aggressively remove
# conversational/image-request filler from the search query.
start = text.find("    func resolvedVisualQuery(current: String, previousUser: String?) -> String {")
end = text.find("    func fetchVisualImage(query: String) async throws", start)
if start < 0 or end < 0:
    raise SystemExit("resolvedVisualQuery function markers not found")
new_resolver = r'''    func resolvedVisualQuery(current: String, previousUser: String?) -> String {
        let currentLower = normalize(current)
        let currentTokens = currentLower.split(whereSeparator: { !$0.isLetter && !$0.isNumber }).map(String.init)
        let imageWords: Set<String> = ["pic", "pics", "picture", "pictures", "photo", "photos", "image", "images", "diagram", "diagrams"]
        let currentTokenSet = Set(currentTokens)

        let referentialFollowup = currentTokens.count <= 14 && (
            currentLower.contains("what about") ||
            currentLower.contains("asked you for") ||
            currentLower.contains("i asked for") ||
            currentLower.contains("the picture") ||
            currentLower.contains("that picture") ||
            currentLower.contains("the pic") ||
            currentLower.contains("that pic") ||
            currentLower.contains("part picture") ||
            currentLower.contains("show me where") ||
            currentLower.contains("what does that look like") ||
            currentLower.contains("what does it look like") ||
            (!currentTokenSet.isDisjoint(with: imageWords) && currentLower.contains("about"))
        )

        var query: String
        if referentialFollowup,
           let previousUser,
           !previousUser.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            query = normalize(previousUser)
        } else {
            query = currentLower
        }

        let removable = [
            "hey babe", "hey baby", "babe", "baby", "please",
            "can you get me", "could you get me", "can you grab me", "could you grab me",
            "can you show me", "could you show me", "can you find me", "could you find me",
            "get me a picture of", "get me a picture", "get me a pic of", "get me a pic",
            "get me a photo of", "get me a photo", "get me an image of", "get me an image",
            "grab me a picture of", "grab me a pic of", "grab me an image of",
            "show me a picture of", "show me a picture", "show me a pic of", "show me a pic",
            "show me a photo of", "show me a photo", "show me an image of", "show me an image",
            "show me a diagram of", "show me a diagram", "send me a picture of", "send me a picture",
            "send me a pic of", "send me a pic", "send me a photo of", "send me an image of",
            "find me a picture of", "find me a picture", "find me a pic of", "find me a pic",
            "find me a photo of", "find me an image of", "make me a picture of", "make me a picture",
            "make me an image of", "make me an image", "draw me a picture of", "draw me a picture",
            "generate a picture of", "generate a picture", "generate an image of", "generate an image",
            "so i can see what it looks like", "so i can see what that looks like",
            "so i can see what this looks like", "what it looks like", "what that looks like",
            "what this looks like", "what does it look like", "what does that look like",
            "what does this look like", "for me"
        ]
        for phrase in removable {
            query = query.replacingOccurrences(of: phrase, with: " ")
        }

        query = query
            .replacingOccurrences(of: "what a ", with: " ")
            .replacingOccurrences(of: "what an ", with: " ")
            .replacingOccurrences(of: "what the ", with: " ")
            .split(whereSeparator: { $0.isWhitespace })
            .joined(separator: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)

        return query.isEmpty ? (previousUser ?? current) : query
    }

'''
text = text[:start] + new_resolver + text[end:]

for marker in [
    "visualRequest || web.shouldUseWeb",
    '"pic", "pics", "picture", "pictures"',
    "referentialFollowup",
    '"get me a pic of"',
]:
    if marker not in text:
        raise SystemExit(f"missing v0.7.10 marker: {marker}")

path.write_text(text, encoding="utf-8")
print("Applied v0.7.10 robust visual-intent and follow-up routing fix")
