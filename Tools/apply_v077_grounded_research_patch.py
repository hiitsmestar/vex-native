#!/usr/bin/env python3
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"{label}: expected source block not found")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# iPhone Web Brain: conversational how-to questions must actually enter research
# mode, and short follow-ups should recover the unresolved detailed question.
# ---------------------------------------------------------------------------
content_path = Path("VexNative/ContentView.swift")
text = content_path.read_text(encoding="utf-8")

old_should = '''        if firstPublicURL(in: text) != nil { return true }\n        if isBridgeRetryRequest(lower) { return true }\n        if isExplicitWebRequest(lower) { return true }\n        guard autoFreshEnabled else { return false }\n\n        let questionish = lower.contains("?") || [\n            "what ", "who ", "when ", "where ", "how ", "is ", "are ", "did ", "does ", "can ", "why "\n        ].contains(where: { lower.hasPrefix($0) })\n\n        if questionish && needsGeneralSearch(text) { return true }\n'''
new_should = '''        if firstPublicURL(in: text) != nil { return true }\n        if isBridgeRetryRequest(lower) { return true }\n        if isExplicitWebRequest(lower) { return true }\n        if isProceduralResearchRequest(lower) { return true }\n        guard autoFreshEnabled else { return false }\n\n        let padded = " " + lower + " "\n        let questionish = lower.contains("?") || [\n            "what ", "who ", "when ", "where ", "how ", "is ", "are ", "did ", "does ", "can ", "why "\n        ].contains(where: { lower.hasPrefix($0) }) || [\n            " what ", " who ", " when ", " where ", " how ", " why ",\n            " can you ", " could you ", " would you ", " help me "\n        ].contains(where: { padded.contains($0) })\n\n        if questionish && needsGeneralSearch(text) { return true }\n'''
text = replace_once(text, old_should, new_should, "conversational web-intent routing")

needs_marker = '''    private func needsGeneralSearch(_ text: String) -> Bool {\n'''
procedural_helper = '''    private func isProceduralResearchRequest(_ text: String) -> Bool {\n        let lower = normalize(text)\n        let patterns = [\n            "how to ", "how do i ", "how can i ", "how should i ",\n            "help me find out how", "help me figure out how",\n            "can you help me find out how", "could you help me find out how",\n            "walk me through how", "show me how to"\n        ]\n        return patterns.contains(where: { lower.contains($0) })\n    }\n\n    func resolvedResearchInput(current: String, previousUser: String?) -> String {\n        let lower = normalize(current)\n        let wordCount = lower.split(whereSeparator: { $0.isWhitespace }).count\n        let followup = wordCount <= 12 && (\n            lower.hasPrefix("what about") || lower.hasPrefix("how about") ||\n            lower.hasPrefix("and what about") || lower.hasPrefix("what did you find") ||\n            lower.hasPrefix("did you find") || lower == "and that?" ||\n            lower == "what about that?" || lower == "what about it?"\n        )\n\n        guard followup,\n              let previousUser = previousUser?.trimmingCharacters(in: .whitespacesAndNewlines),\n              !previousUser.isEmpty\n        else { return current }\n\n        let previousLower = normalize(previousUser)\n        if isProceduralResearchRequest(previousLower) ||\n            needsGeneralSearch(previousUser) ||\n            isExplicitWebRequest(previousLower) {\n            return previousUser\n        }\n        return current\n    }\n\n'''
if needs_marker not in text:
    raise SystemExit("ContentView.swift: needsGeneralSearch marker missing")
text = text.replace(needs_marker, procedural_helper + needs_marker, 1)

old_cleanup_prefixes = '''            "gorgeous ", "your cute ", "you're cute ", "youre cute ", "can you ",\n            "could you ", "would you ", "please ", "tell me ", "find out "\n'''
new_cleanup_prefixes = '''            "gorgeous ", "your cute ", "you're cute ", "youre cute ", "can you ",\n            "could you ", "would you ", "please ", "help me find out ",\n            "help me figure out ", "help me ", "tell me ", "find out "\n'''
text = replace_once(text, old_cleanup_prefixes, new_cleanup_prefixes, "research-query conversational cleanup")

old_evidence = '''    func compactEvidence(maxCharacters: Int = 720) -> String {\n        let combined = sources.prefix(3).map { source in\n            let clean = source.snippet.replacingOccurrences(of: "\\n", with: " ")\n            return "\\(source.title): \\(clean)"\n        }.joined(separator: " | ")\n        return String(combined.prefix(maxCharacters))\n    }\n\n    func temporaryMemoryText(userQuestion: String) -> String {\n        let evidence = compactEvidence(maxCharacters: 900)\n        return "WEB EVIDENCE: \\(evidence) | USER QUESTION: \\(userQuestion)"\n    }\n'''
new_evidence = '''    func compactEvidence(maxCharacters: Int = 3200) -> String {\n        let perSource = max(700, maxCharacters / 3)\n        let combined = sources.prefix(3).map { source in\n            let clean = source.snippet.replacingOccurrences(of: "\\n", with: " ")\n            return "\\(source.title): \\(String(clean.prefix(perSource)))"\n        }.joined(separator: " | ")\n        return String(combined.prefix(maxCharacters))\n    }\n\n    func temporaryMemoryText(userQuestion: String) -> String {\n        let evidence = compactEvidence(maxCharacters: 3200)\n        return "WEB EVIDENCE: \\(evidence) | USER QUESTION: \\(userQuestion)"\n    }\n'''
text = replace_once(text, old_evidence, new_evidence, "larger balanced research evidence")

old_send_start = '''        let web = WebBrain.shared\n        guard web.shouldUseWeb(for: original) else {\n            await send()\n            return\n        }\n'''
new_send_start = '''        let web = WebBrain.shared\n        let previousUser = profile.messages\n            .reversed()\n            .first(where: { $0.role == .user })?\n            .content\n        let researchInput = web.resolvedResearchInput(current: original, previousUser: previousUser)\n        guard web.shouldUseWeb(for: researchInput) else {\n            await send()\n            return\n        }\n'''
text = replace_once(text, old_send_start, new_send_start, "follow-up research recovery")
text = replace_once(text, "bundle = try await web.research(original)", "bundle = try await web.research(researchInput)", "resolved research execution")
text = replace_once(
    text,
    "text: bundle.temporaryMemoryText(userQuestion: original),",
    "text: bundle.temporaryMemoryText(userQuestion: researchInput),",
    "resolved research evidence target",
)
content_path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Qwen3 research mode: more evidence, less creativity, and an explicit ban on
# generic filler when the sources do not establish a concrete step.
# ---------------------------------------------------------------------------
prompt_path = Path("VexNative/Core/PromptComposer.swift")
prompt = prompt_path.read_text(encoding="utf-8")
prompt = replace_once(
    prompt,
    '        let evidence = String(webEvidence.text.prefix(1500))\n',
    '        let evidence = String(webEvidence.text.prefix(3400))\n',
    "Qwen3 research evidence window",
)
old_prompt_rule = '''        The evidence below was already retrieved for Star's newest question. Use it as reference material and ANSWER HER QUESTION DIRECTLY in your own words. Do not behave like a search engine and do not merely list pages, links, titles, or things she should go read.\n        For troubleshooting, repair, or how-to questions: say what the evidence indicates, then give the useful checks or steps in a sensible order. If an exact model/part detail is not established by the evidence, say what detail still needs verification instead of inventing it.\n'''
new_prompt_rule = '''        The evidence below was already retrieved for Star's newest question. Use it as reference material and ANSWER HER QUESTION DIRECTLY in your own words. Do not behave like a search engine and do not merely list pages, links, titles, or things she should go read.\n        The exact research target is included after USER QUESTION in the evidence. If Star's latest line is a short follow-up such as "what about that?", answer that recovered research target rather than the vague follow-up wording.\n        For troubleshooting, repair, or how-to questions: say what the evidence indicates, then give the useful checks or steps in a sensible order. Name the actual component/device from Star's question. Never substitute generic filler such as "turn it off and on again", "maybe the motor", "service options", "online tools", or "keep trying step by step" unless the retrieved evidence specifically supports that advice.\n        If the evidence does not establish a concrete procedure or part detail, say that the search results were not specific enough yet instead of guessing.\n'''
prompt = replace_once(prompt, old_prompt_rule, new_prompt_rule, "grounded research synthesis rules")
prompt_path.write_text(prompt, encoding="utf-8")

app_path = Path("VexNative/AppModel.swift")
app = app_path.read_text(encoding="utf-8")
app = app.replace("webGroundedTurn ? 180 : 56", "webGroundedTurn ? 240 : 56", 1)
app = app.replace("webGroundedTurn ? 0.62 : 0.80", "webGroundedTurn ? 0.45 : 0.80", 1)
app = app.replace("webGroundedTurn ? 0.86 : 0.90", "webGroundedTurn ? 0.78 : 0.90", 1)
app = app.replace("webGroundedTurn ? 32 : 40", "webGroundedTurn ? 24 : 40", 1)
app_path.write_text(app, encoding="utf-8")


# ---------------------------------------------------------------------------
# Windows Bridge: enrich the top web hits with focused text from the actual page.
# DuckDuckGo snippets alone are often too generic for a 0.6B model to synthesize
# a repair/how-to answer. Page fetches happen concurrently and failures fall back
# to the original snippets.
# ---------------------------------------------------------------------------
bridge_path = Path("Bridge/vex_bridge.py")
bridge = bridge_path.read_text(encoding="utf-8")
start = bridge.find("def web_search(query: str, limit: int = 6) -> list[dict]:")
end = bridge.find("\n\nclass BridgeState:", start)
if start < 0 or end < 0:
    raise SystemExit("vex_bridge.py: web_search block markers missing")

enriched_search = r'''def focused_web_excerpt(text: str, query: str, max_chars: int = 2600) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return ""

    stop = {
        "the", "and", "for", "with", "that", "this", "from", "your", "you", "how",
        "can", "help", "find", "out", "what", "about", "into", "then", "than", "are",
        "was", "were", "have", "has", "had", "its", "use", "using", "change"
    }
    qwords = [w for w in words(query) if len(w) >= 3 and w not in stop]
    procedural = {
        "replace", "remove", "install", "disconnect", "unplug", "panel", "screw", "wire",
        "fuse", "thermostat", "step", "repair", "test", "continuity", "access", "back", "front"
    }

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", compact) if len(s.strip()) >= 35]
    if not sentences:
        return compact[:max_chars]

    scored: list[tuple[float, int, str]] = []
    for index, sentence in enumerate(sentences):
        lower = sentence.lower()
        overlap = sum(1 for w in qwords if w in lower)
        proc_hits = sum(1 for w in procedural if w in lower)
        score = overlap * 3.0 + min(proc_hits, 3) * 0.8
        if overlap:
            scored.append((score, index, sentence))

    if not scored:
        return compact[:max_chars]

    best = sorted(scored, key=lambda item: (-item[0], item[1]))[:10]
    selected = sorted(best, key=lambda item: item[1])
    excerpt = " ".join(item[2] for item in selected)
    return excerpt[:max_chars]


def enrich_web_result(result: dict, query: str) -> dict:
    try:
        import requests
        from bs4 import BeautifulSoup

        response = requests.get(
            result.get("url", ""),
            headers={"User-Agent": "Mozilla/5.0 VexBridge/0.7.7"},
            timeout=5.5,
            allow_redirects=True,
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if "html" not in content_type or len(response.content) > 3_000_000:
            return result

        soup = BeautifulSoup(response.text, "html.parser")
        for node in soup(["script", "style", "noscript", "svg", "nav", "header", "footer", "form"]):
            node.decompose()
        root = soup.find("main") or soup.find("article") or soup.body or soup
        text = " ".join(root.stripped_strings)
        excerpt = focused_web_excerpt(text, query)
        if len(excerpt) >= 180:
            enriched = dict(result)
            enriched["content"] = excerpt
            enriched["engine"] = "Vex Bridge web+page"
            return enriched
    except Exception:
        pass
    return result


def web_search(query: str, limit: int = 6) -> list[dict]:
    try:
        import requests
        from bs4 import BeautifulSoup
        from concurrent.futures import ThreadPoolExecutor

        response = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers={"User-Agent": "Mozilla/5.0 VexBridge/0.7.7"},
            timeout=9,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        for block in soup.select(".result"):
            link = block.select_one("a.result__a")
            if link is None:
                continue
            href = unwrap_ddg(link.get("href") or "")
            if not href.startswith("https://"):
                continue
            snippet_node = block.select_one(".result__snippet")
            snippet = " ".join(snippet_node.stripped_strings) if snippet_node else ""
            title = " ".join(link.stripped_strings)
            if not title:
                continue
            results.append({
                "title": title,
                "url": href,
                "content": snippet,
                "engine": "Vex Bridge web",
                "score": max(0.2, 1.0 - len(results) * 0.08),
            })
            if len(results) >= limit:
                break

        # The first two actual pages usually carry far more procedural detail than
        # their search snippets. Fetch them in parallel so Bridge latency stays low.
        enrich_count = min(2, len(results))
        if enrich_count:
            with ThreadPoolExecutor(max_workers=enrich_count) as pool:
                futures = [pool.submit(enrich_web_result, results[i], query) for i in range(enrich_count)]
                for i, future in enumerate(futures):
                    try:
                        results[i] = future.result(timeout=6.5)
                    except Exception:
                        pass
        return results
    except Exception:
        return []
'''
bridge = bridge[:start] + enriched_search + bridge[end:]
bridge = bridge.replace("0.7.5", "0.7.7")
bridge_path.write_text(bridge, encoding="utf-8")

full_path = Path("Bridge/vex_bridge_full.py")
full = full_path.read_text(encoding="utf-8")
full = full.replace('VERSION = "0.7.5"', 'VERSION = "0.7.7"', 1)
full_path.write_text(full, encoding="utf-8")

for path, markers in [
    (content_path, ["isProceduralResearchRequest", "resolvedResearchInput", "maxCharacters: 3200"]),
    (prompt_path, ["search results were not specific enough yet", "prefix(3400)"]),
    (app_path, ["webGroundedTurn ? 240", "webGroundedTurn ? 0.45"]),
    (bridge_path, ["focused_web_excerpt", "VexBridge/0.7.7", "ThreadPoolExecutor"]),
    (full_path, ['VERSION = "0.7.7"']),
]:
    data = path.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in data:
            raise SystemExit(f"{path}: missing v0.7.7 marker: {marker}")

print("Applied v0.7.7 grounded research + page enrichment patch")
