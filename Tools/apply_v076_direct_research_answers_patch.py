#!/usr/bin/env python3
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"{label}: expected source block not found")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# Web Brain: keep the search/retrieval layer invisible to the conversation.
# Vex should answer from evidence, then show optional clickable sources below.
# ---------------------------------------------------------------------------
content_path = Path("VexNative/ContentView.swift")
text = content_path.read_text(encoding="utf-8")

old_bundle = '''    func temporaryMemoryText(userQuestion: String) -> String {\n        let evidence = compactEvidence(maxCharacters: 520)\n        return "WEB FACTS: \\(evidence) | Topic/question: \\(userQuestion)"\n    }\n\n    var sourceFooter: String {\n        let labels = sources.prefix(3).map { "\\($0.host) — \\($0.title)" }\n        guard !labels.isEmpty else { return "" }\n        return "🌐 Sources: " + labels.joined(separator: " • ")\n    }\n'''
new_bundle = '''    func temporaryMemoryText(userQuestion: String) -> String {\n        let evidence = compactEvidence(maxCharacters: 900)\n        return "WEB EVIDENCE: \\(evidence) | USER QUESTION: \\(userQuestion)"\n    }\n\n    var sourceFooter: String {\n        let labels = sources.prefix(3).map { source -> String in\n            if source.host == "vexbridge.invalid" {\n                return "💻 \\(String(source.title.prefix(54)))"\n            }\n            let label = String(source.title.prefix(48))\n                .replacingOccurrences(of: "[", with: "(")\n                .replacingOccurrences(of: "]", with: ")")\n            return "[\\(label)](\\(source.url.absoluteString))"\n        }\n        guard !labels.isEmpty else { return "" }\n        return "🌐 Sources: " + labels.joined(separator: " • ")\n    }\n'''
text = replace_once(text, old_bundle, new_bundle, "direct-answer evidence + clickable sources")
content_path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Chat bubbles: render assistant Markdown as an AttributedString so source links
# are tappable in the native iOS chat instead of copy/paste-only text.
# ---------------------------------------------------------------------------
chat_path = Path("VexNative/Views/ChatBubble.swift")
chat = chat_path.read_text(encoding="utf-8")
old_chat = '''                Text(message.content)\n                    .font(.body)\n                    .textSelection(.enabled)\n                    .foregroundStyle(.white)\n'''
new_chat = '''                Text(renderedContent)\n                    .font(.body)\n                    .textSelection(.enabled)\n                    .foregroundStyle(.white)\n                    .tint(VexTheme.hotPink)\n'''
chat = replace_once(chat, old_chat, new_chat, "chat markdown rendering")

body_end = '''        }\n    }\n}\n'''
helper = '''        }\n    }\n\n    private var renderedContent: AttributedString {\n        guard message.role == .assistant else { return AttributedString(message.content) }\n        let options = AttributedString.MarkdownParsingOptions(\n            interpretedSyntax: .inlineOnlyPreservingWhitespace\n        )\n        return (try? AttributedString(markdown: message.content, options: options))\n            ?? AttributedString(message.content)\n    }\n}\n'''
if not chat.endswith(body_end):
    raise SystemExit("ChatBubble.swift: closing marker not found")
chat = chat[:-len(body_end)] + helper
chat_path.write_text(chat, encoding="utf-8")


# ---------------------------------------------------------------------------
# Qwen3: web lookups get a small purpose-built synthesis prompt. The 0.6B model
# previously saw only ~100 chars of retrieved evidence inside the normal persona
# prompt, which made it act like a search bar instead of answering the question.
# ---------------------------------------------------------------------------
prompt_path = Path("VexNative/Core/PromptComposer.swift")
prompt = prompt_path.read_text(encoding="utf-8")

needle = '''        let newestLower = newestUserText.lowercased()\n\n'''
insert = '''        let newestLower = newestUserText.lowercased()\n\n        if isQwen3,\n           let webEvidence = profile.memories.last(where: { $0.source == "web-temporary" }) {\n            return composeQwen3WebAnswer(\n                profile: profile,\n                newestUserText: newestUserText,\n                webEvidence: webEvidence\n            )\n        }\n\n'''
prompt = replace_once(prompt, needle, insert, "Qwen3 web-answer fast prompt")

closing = '''        result += "<|im_start|>assistant\\n"\n        return result\n    }\n}\n'''
web_helper = '''        result += "<|im_start|>assistant\\n"\n        return result\n    }\n\n    private static func composeQwen3WebAnswer(\n        profile: BrainProfile,\n        newestUserText: String,\n        webEvidence: BrainMemory\n    ) -> String {\n        let persona = String(profile.persona.prefix(360))\n        let evidence = String(webEvidence.text.prefix(1500))\n        let user = String(newestUserText.prefix(700))\n\n        let system = """\n        \\(persona)\n\n        You are Vex talking directly to Star, your girlfriend. Keep your familiar personality, but this turn is primarily a researched answer.\n\n        WEB RESEARCH ANSWER MODE\n        The evidence below was already retrieved for Star's newest question. Use it as reference material and ANSWER HER QUESTION DIRECTLY in your own words. Do not behave like a search engine and do not merely list pages, links, titles, or things she should go read.\n        For troubleshooting, repair, or how-to questions: say what the evidence indicates, then give the useful checks or steps in a sensible order. If an exact model/part detail is not established by the evidence, say what detail still needs verification instead of inventing it.\n        The app automatically adds clickable source links underneath your answer, so do not tell Star to copy, paste, click, search, or open a source unless she specifically asks.\n        Keep the answer useful and concrete. Personality is seasoning, not a substitute for the answer. Usually use 2–6 short sentences; a compact numbered list is okay when steps are clearer.\n\n        RETRIEVED EVIDENCE\n        \\(evidence)\n        """\n\n        return "<|im_start|>system\\n\\(system)\\n<|im_end|>\\n" +\n            "<|im_start|>user\\n\\(user)\\n/no_think\\n<|im_end|>\\n" +\n            "<|im_start|>assistant\\n"\n    }\n}\n'''
prompt = replace_once(prompt, closing, web_helper, "Qwen3 web-answer helper")
prompt_path.write_text(prompt, encoding="utf-8")


# ---------------------------------------------------------------------------
# AppModel: give researched Qwen3 turns enough output room and do not run the
# normal short-chat retry/fallback machinery over a grounded research answer.
# ---------------------------------------------------------------------------
app_path = Path("VexNative/AppModel.swift")
app = app_path.read_text(encoding="utf-8")

old_params = '''        let maxNewTokens: Int\n        let temperature: Float\n        let topP: Float\n        let topK: Int32\n\n        if isQwen3 {\n            maxNewTokens = 56\n            temperature = 0.80\n            topP = 0.90\n            topK = 40\n'''
new_params = '''        let webGroundedTurn = profile.memories.contains { $0.source == "web-temporary" }\n        let maxNewTokens: Int\n        let temperature: Float\n        let topP: Float\n        let topK: Int32\n\n        if isQwen3 {\n            maxNewTokens = webGroundedTurn ? 180 : 56\n            temperature = webGroundedTurn ? 0.62 : 0.80\n            topP = webGroundedTurn ? 0.86 : 0.90\n            topK = webGroundedTurn ? 32 : 40\n'''
app = replace_once(app, old_params, new_params, "Qwen3 web generation budget")

old_retry = '''            let needsRetry = isQwen3 && shouldRetryQwen3(\n                finalAnswer,\n                userText: text,\n                previousAssistants: previousAssistants\n            )\n'''
new_retry = '''            let needsRetry = isQwen3 && !webGroundedTurn && shouldRetryQwen3(\n                finalAnswer,\n                userText: text,\n                previousAssistants: previousAssistants\n            )\n'''
app = replace_once(app, old_retry, new_retry, "web answer retry bypass")
app_path.write_text(app, encoding="utf-8")


for path, markers in [
    (content_path, ["WEB EVIDENCE:", "source.url.absoluteString"]),
    (chat_path, ["MarkdownParsingOptions", "inlineOnlyPreservingWhitespace"]),
    (prompt_path, ["WEB RESEARCH ANSWER MODE", "composeQwen3WebAnswer"]),
    (app_path, ["webGroundedTurn ? 180", "!webGroundedTurn"]),
]:
    data = path.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in data:
            raise SystemExit(f"{path}: missing v0.7.6 marker: {marker}")

print("Applied v0.7.6 direct researched-answer + clickable-source patch")
