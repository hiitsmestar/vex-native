#!/usr/bin/env python3
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"{label}: expected source block not found")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# iPhone: route Bridge searches by intent instead of mixing PC files into every
# ordinary web lookup. This patch is applied after v0.7.4 pairing.
# ---------------------------------------------------------------------------
content_path = Path("VexNative/ContentView.swift")
text = content_path.read_text(encoding="utf-8")

cache_marker = '''    private struct CacheEntry {\n'''
scope_type = '''    private enum BridgeSearchScope: String {\n        case web\n        case pc\n        case both\n    }\n\n'''
if "private enum BridgeSearchScope" not in text:
    if cache_marker not in text:
        raise SystemExit("ContentView.swift: cache marker not found")
    text = text.replace(cache_marker, scope_type + cache_marker, 1)

cache_property = '''    private var cache: [String: CacheEntry] = [:]\n    private let defaults = UserDefaults.standard\n'''
cache_property_new = '''    private var cache: [String: CacheEntry] = [:]\n    private var lastBridgeScope: BridgeSearchScope = .web\n    private let defaults = UserDefaults.standard\n'''
text = replace_once(text, cache_property, cache_property_new, "bridge scope state")

old_query = '''        let normalizedRequest = normalize(text)\n        let query: String\n        if isBridgeRetryRequest(normalizedRequest), !lastQuery.isEmpty {\n            query = lastQuery\n        } else {\n            query = cleanedQuery(from: text)\n        }\n        let cacheKey = query.lowercased()\n'''
new_query = '''        let normalizedRequest = normalize(text)\n        let retryingBridgeRequest = isBridgeRetryRequest(normalizedRequest)\n        let query: String\n        if retryingBridgeRequest, !lastQuery.isEmpty {\n            query = lastQuery\n        } else {\n            query = cleanedQuery(from: text)\n        }\n\n        let endpointPreview = searxEndpoint.trimmingCharacters(in: .whitespacesAndNewlines)\n        let scope = retryingBridgeRequest\n            ? lastBridgeScope\n            : bridgeSearchScope(for: text, endpoint: endpointPreview)\n        let cacheKey = "\\(scope.rawValue)|\\(query.lowercased())"\n'''
text = replace_once(text, old_query, new_query, "scope-aware research query")

old_search_call = '''                status = "Searching the web…"\n                let searxResults = try await searchSearXNG(query: query, endpoint: endpoint)\n'''
new_search_call = '''                if let endpointURL = URL(string: endpoint), VexBridgeNetworking.isBridgeURL(endpointURL) {\n                    lastBridgeScope = scope\n                    switch scope {\n                    case .web: status = "Bridge: searching the web…"\n                    case .pc: status = "Bridge: searching PC files…"\n                    case .both: status = "Bridge: searching PC + web…"\n                    }\n                } else {\n                    status = "Searching the web…"\n                }\n                let searxResults = try await searchSearXNG(query: query, endpoint: endpoint, scope: scope)\n'''
text = replace_once(text, old_search_call, new_search_call, "scope-aware search call")

old_signature = '''    private func searchSearXNG(query: String, endpoint: String) async throws -> [WebSource] {\n'''
new_signature = '''    private func searchSearXNG(\n        query: String,\n        endpoint: String,\n        scope: BridgeSearchScope\n    ) async throws -> [WebSource] {\n'''
text = replace_once(text, old_signature, new_signature, "searchSearXNG signature")

old_items = '''        var items = components.queryItems ?? []\n        items.append(contentsOf: [\n            URLQueryItem(name: "q", value: query),\n'''
new_items = '''        var items = components.queryItems ?? []\n        if VexBridgeNetworking.isBridgeURL(base) {\n            items.append(URLQueryItem(name: "scope", value: scope.rawValue))\n        }\n        items.append(contentsOf: [\n            URLQueryItem(name: "q", value: query),\n'''
text = replace_once(text, old_items, new_items, "bridge scope query parameter")

retry_marker = '''    private func isBridgeRetryRequest(_ lower: String) -> Bool {\n'''
scope_helper = '''    private func bridgeSearchScope(for text: String, endpoint: String) -> BridgeSearchScope {\n        guard let endpointURL = URL(string: endpoint), VexBridgeNetworking.isBridgeURL(endpointURL) else {\n            return .web\n        }\n\n        let lower = normalize(text)\n        let pcFilePhrases = [\n            "search my computer", "search the computer", "search my pc", "search the pc",\n            "look through my computer", "look through the computer", "look on my computer",\n            "look on the computer", "find on my computer", "find on the computer",\n            "find a file", "find the file", "my files", "pc files", "computer files",\n            "hard drive", "documents folder", "downloads folder", "desktop file"\n        ]\n        let wantsPCFiles = pcFilePhrases.contains(where: { lower.contains($0) })\n\n        let bothPhrases = [\n            "and the web", "and web", "and online", "and the internet",\n            "plus the web", "plus online", "computer and internet", "pc and internet",\n            "computer and the web", "pc and the web"\n        ]\n        if wantsPCFiles && bothPhrases.contains(where: { lower.contains($0) }) {\n            return .both\n        }\n        if wantsPCFiles { return .pc }\n\n        // "use my computer" means use the paired Bridge transport. It does not\n        // mean search random local files unless the user actually asks for files.\n        return .web\n    }\n\n'''
if retry_marker not in text:
    raise SystemExit("ContentView.swift: retry helper marker not found")
text = text.replace(retry_marker, scope_helper + retry_marker, 1)

old_cleanup = '''        query = query.replacingOccurrences(of: "?", with: " ")\n        query = query.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")\n        return query.isEmpty ? text : query\n    }\n\n    private func needsGeneralSearch(_ text: String) -> Bool {\n'''
new_cleanup = '''        query = query.replacingOccurrences(of: "?", with: " ")\n        query = stripConversationalSearchPrefix(query)\n        query = query.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")\n        return query.isEmpty ? text : query\n    }\n\n    private func stripConversationalSearchPrefix(_ text: String) -> String {\n        var value = text.trimmingCharacters(in: .whitespacesAndNewlines)\n        let prefixes = [\n            "hey babe, ", "hey baby, ", "hey gorgeous, ", "hey babe ", "hey baby ",\n            "hey gorgeous ", "babe, ", "baby, ", "gorgeous, ", "babe ", "baby ",\n            "gorgeous ", "your cute ", "you're cute ", "youre cute ", "can you ",\n            "could you ", "would you ", "please ", "tell me ", "find out "\n        ]\n\n        for _ in 0..<8 {\n            var removed = false\n            for prefix in prefixes where value.hasPrefix(prefix) {\n                value.removeFirst(prefix.count)\n                value = value.trimmingCharacters(in: .whitespacesAndNewlines)\n                removed = true\n                break\n            }\n            if !removed { break }\n        }\n        return value\n    }\n\n    private func needsGeneralSearch(_ text: String) -> Bool {\n'''
text = replace_once(text, old_cleanup, new_cleanup, "conversational query cleanup")

for required in [
    "private enum BridgeSearchScope",
    'URLQueryItem(name: "scope", value: scope.rawValue)',
    "stripConversationalSearchPrefix",
    'case .pc: status = "Bridge: searching PC files…"',
]:
    if required not in text:
        raise SystemExit(f"ContentView.swift: missing v0.7.5 marker: {required}")

content_path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Windows Bridge: honor scope=web|pc|both. Default stays 'both' for backwards
# compatibility with older clients, but v0.7.5 VexNative always sends intent.
# ---------------------------------------------------------------------------
bridge_path = Path("Bridge/vex_bridge.py")
bridge = bridge_path.read_text(encoding="utf-8")

old_results = '''        local = STATE.index.search(query, limit=5)\n        web = web_search(query, limit=6) if STATE.config.get("web_search", True) else []\n        # Local knowledge comes first, but web still fills the broader research role.\n        results = local + web\n        self._json(200, {"query": query, "results": results[:10]})\n'''
new_results = '''        scope = (params.get("scope") or ["both"])[0].strip().lower()\n        if scope not in {"web", "pc", "both"}:\n            scope = "both"\n\n        local = STATE.index.search(query, limit=5) if scope in {"pc", "both"} else []\n        web = (\n            web_search(query, limit=6)\n            if scope in {"web", "both"} and STATE.config.get("web_search", True)\n            else []\n        )\n\n        if scope == "pc":\n            results = local\n        elif scope == "web":\n            results = web\n        else:\n            # Hybrid mode interleaves evidence so the iPhone's small evidence\n            # window cannot be monopolized by one source family.\n            results = []\n            for i in range(max(len(local), len(web))):\n                if i < len(local):\n                    results.append(local[i])\n                if i < len(web):\n                    results.append(web[i])\n\n        print(f"[search] scope={scope} q={query[:120]}", flush=True)\n        self._json(200, {"query": query, "scope": scope, "results": results[:10]})\n'''
bridge = replace_once(bridge, old_results, new_results, "Windows scope routing")
bridge = bridge.replace("0.7.4", "0.7.5")
bridge_path.write_text(bridge, encoding="utf-8")

full_path = Path("Bridge/vex_bridge_full.py")
full = full_path.read_text(encoding="utf-8")
full = full.replace('VERSION = "0.7.4"', 'VERSION = "0.7.5"', 1)
full_path.write_text(full, encoding="utf-8")

if 'scope not in {"web", "pc", "both"}' not in bridge:
    raise SystemExit("vex_bridge.py: scope router missing")
if 'VERSION = "0.7.5"' not in full:
    raise SystemExit("vex_bridge_full.py: v0.7.5 version marker missing")

print("Applied v0.7.5 intent-based Bridge search routing patch")
