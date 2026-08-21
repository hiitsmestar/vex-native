import Foundation
import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var app: AppModel
    @StateObject private var web = WebBrain.shared

    var body: some View {
        ZStack {
            LinearGradient(
                colors: [
                    VexTheme.ink,
                    Color(red: 0.12, green: 0.045, blue: 0.14),
                    VexTheme.ink
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()

            VStack(spacing: 0) {
                header
                statusStrip

                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(spacing: 10) {
                            ForEach(app.messages) { message in
                                ChatBubble(message: message)
                                    .id(message.id)
                            }

                            if app.isGenerating || web.isWorking {
                                HStack {
                                    ProgressView()
                                    Text(web.isWorking ? "web brain is looking…" : "three neurons are thinking…")
                                        .font(.caption)
                                        .foregroundStyle(VexTheme.muted)
                                    Spacer()
                                }
                                .padding(.horizontal, 8)
                            }
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 10)
                    }
                    .onChange(of: app.messages.count) { _, _ in
                        if let last = app.messages.last?.id {
                            withAnimation { proxy.scrollTo(last, anchor: .bottom) }
                        }
                    }
                }

                composer
            }
        }
        .dynamicTypeSize(.small ... .xLarge)
        .sheet(isPresented: $app.showBrain) {
            BrainView()
                .environmentObject(app)
                .dynamicTypeSize(.small ... .xLarge)
        }
        .task {
            await app.loadSavedModelIfPresent()
        }
        .alert(
            "Tiny brain error",
            isPresented: Binding(
                get: { app.lastError != nil },
                set: { if !$0 { app.lastError = nil } }
            )
        ) {
            Button("OK") { app.lastError = nil }
        } message: {
            Text(app.lastError ?? "")
        }
    }

    private var header: some View {
        HStack {
            VStack(alignment: .leading, spacing: 1) {
                Text("LOCAL GIRLFRIEND ENGINE")
                    .font(.caption2.weight(.black))
                    .tracking(1.6)
                    .foregroundStyle(VexTheme.muted)
                    .lineLimit(1)
                    .minimumScaleFactor(0.75)
                HStack(spacing: 6) {
                    Text("Vex")
                        .font(.largeTitle.bold())
                    Text("✦")
                        .font(.title2)
                        .foregroundStyle(VexTheme.hotPink)
                }
            }

            Spacer(minLength: 8)

            Button {
                app.showBrain = true
            } label: {
                Label("Brain", systemImage: "brain.head.profile")
                    .labelStyle(.titleAndIcon)
                    .font(.subheadline.weight(.bold))
                    .padding(.horizontal, 12)
                    .padding(.vertical, 9)
                    .background(.white.opacity(0.07))
                    .clipShape(Capsule())
            }
            .tint(.white)
        }
        .padding(.horizontal, 14)
        .padding(.top, 8)
        .padding(.bottom, 7)
    }

    private var statusStrip: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(app.modelStatus.hasPrefix("Loaded") ? Color.green : VexTheme.hotPink)
                .frame(width: 8, height: 8)

            Text(app.modelStatus)
                .font(.caption)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
                .foregroundStyle(VexTheme.muted)

            if web.isWorking {
                Text("• 🌐")
                    .font(.caption)
            }

            Spacer()
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .background(.black.opacity(0.18))
    }

    private var composer: some View {
        HStack(alignment: .center, spacing: 8) {
            TextField("Say something to Vex…", text: $app.draft)
                .padding(11)
                .background(VexTheme.panel)
                .clipShape(RoundedRectangle(cornerRadius: 16))
                .overlay {
                    RoundedRectangle(cornerRadius: 16)
                        .stroke(.white.opacity(0.08))
                }
                .submitLabel(.send)
                .disabled(web.isWorking)
                .onSubmit {
                    guard !app.isGenerating, !web.isWorking else { return }
                    Task { await app.sendWithWeb() }
                }

            Button {
                guard !app.isGenerating, !web.isWorking else { return }
                Task { await app.sendWithWeb() }
            } label: {
                Image(systemName: "arrow.up")
                    .font(.headline.bold())
                    .foregroundStyle(Color.black)
                    .frame(width: 44, height: 44)
                    .background(
                        LinearGradient(
                            colors: [VexTheme.hotPink, VexTheme.violet],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .clipShape(Circle())
            }
            .buttonStyle(.plain)
            .disabled(
                app.isGenerating || web.isWorking ||
                app.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            )
            .opacity((app.isGenerating || web.isWorking) ? 0.5 : 1)
        }
        .padding(.horizontal, 12)
        .padding(.top, 8)
        .padding(.bottom, 9)
        .background(.ultraThinMaterial)
    }
}

// MARK: - Web Brain v0.6

struct WebSource: Equatable, Sendable {
    let title: String
    let url: URL
    let snippet: String
    let provider: String
    let trust: Double

    var host: String {
        url.host?.replacingOccurrences(of: "www.", with: "") ?? provider
    }
}

struct WebResearchBundle: Sendable {
    let query: String
    let sources: [WebSource]
    let fetchedAt: Date

    var bestTrust: Double {
        sources.map(\.trust).max() ?? 0.60
    }

    func compactEvidence(maxCharacters: Int = 720) -> String {
        let combined = sources.prefix(3).map { source in
            let clean = source.snippet.replacingOccurrences(of: "\n", with: " ")
            return "\(source.title): \(clean)"
        }.joined(separator: " | ")
        return String(combined.prefix(maxCharacters))
    }

    func temporaryMemoryText(userQuestion: String) -> String {
        let evidence = compactEvidence(maxCharacters: 520)
        return "WEB FACTS: \(evidence) | Topic/question: \(userQuestion)"
    }

    var sourceFooter: String {
        let labels = sources.prefix(3).map { "\($0.host) — \($0.title)" }
        guard !labels.isEmpty else { return "" }
        return "🌐 Sources: " + labels.joined(separator: " • ")
    }

    func memoriesForDeliberateLearning() -> [BrainMemory] {
        sources.prefix(3).map { source in
            BrainMemory(
                text: "Web-learned source: \(source.title) — \(String(source.snippet.prefix(650)))",
                kind: .fact,
                importance: 0.74,
                confidence: source.trust,
                evidenceCount: 1,
                lastConfirmedAt: fetchedAt,
                source: "web:\(source.url.absoluteString)"
            )
        }
    }
}

enum WebBrainError: LocalizedError {
    case noSearchProvider
    case generalSearchNeedsSearXNG
    case invalidEndpoint
    case unsafeURL
    case badResponse(Int)
    case noResults

    var errorDescription: String? {
        switch self {
        case .noSearchProvider:
            return "No web search provider is enabled."
        case .generalSearchNeedsSearXNG:
            return "Live/current web search needs a SearXNG endpoint. Wikipedia is still available for encyclopedia-style research."
        case .invalidEndpoint:
            return "The SearXNG endpoint is not a valid HTTPS URL."
        case .unsafeURL:
            return "That URL is not a public HTTPS page I can safely read."
        case .badResponse(let code):
            return "The web source returned HTTP \(code)."
        case .noResults:
            return "The web search returned no usable results."
        }
    }
}

@MainActor
final class WebBrain: ObservableObject {
    static let shared = WebBrain()

    static let enabledKey = "vex.web.enabled"
    static let autoFreshKey = "vex.web.autoFresh"
    static let wikipediaKey = "vex.web.wikipedia"
    static let searxEndpointKey = "vex.web.searxngEndpoint"

    @Published var isWorking = false
    @Published var status = "Ready — Wikipedia + direct URLs"
    @Published var lastQuery = ""
    @Published var lastSourceCount = 0
    @Published var lastUsedAt: Date?
    @Published var cacheCount = 0

    private struct CacheEntry {
        let bundle: WebResearchBundle
        let expiresAt: Date
    }

    private var cache: [String: CacheEntry] = [:]
    private let defaults = UserDefaults.standard

    private init() {
        defaults.register(defaults: [
            Self.enabledKey: true,
            Self.autoFreshKey: true,
            Self.wikipediaKey: true,
            Self.searxEndpointKey: ""
        ])
    }

    var isEnabled: Bool { defaults.bool(forKey: Self.enabledKey) }
    var autoFreshEnabled: Bool { defaults.bool(forKey: Self.autoFreshKey) }
    var wikipediaEnabled: Bool { defaults.bool(forKey: Self.wikipediaKey) }
    var searxEndpoint: String { defaults.string(forKey: Self.searxEndpointKey) ?? "" }

    func shouldUseWeb(for text: String) -> Bool {
        guard isEnabled else { return false }
        let lower = normalize(text)
        if firstPublicURL(in: text) != nil { return true }
        if isExplicitWebRequest(lower) { return true }
        guard autoFreshEnabled else { return false }

        let questionish = lower.contains("?") || [
            "what ", "who ", "when ", "where ", "how ", "is ", "are ", "did ", "does ", "can "
        ].contains(where: { lower.hasPrefix($0) })

        let freshness = containsWholePhrase(lower, "latest") ||
            containsWholePhrase(lower, "current") ||
            containsWholePhrase(lower, "recent") ||
            containsWholePhrase(lower, "today") ||
            lower.contains("breaking news") || lower.contains("news about") ||
            lower.contains("weather in") || lower.contains("weather for") ||
            lower.contains("current price") || lower.contains("latest version") ||
            lower.contains("latest release") || lower.contains("outage")

        return questionish && freshness
    }

    func isExplicitWebRequest(_ text: String) -> Bool {
        let lower = normalize(text)
        let triggers = [
            "search the web", "search online", "web search", "look this up", "look up ",
            "find online", "find on the web", "check the internet", "search the internet",
            "research ", "learn about ", "study ", "read this url", "read this page"
        ]
        return triggers.contains(where: { lower.contains($0) })
    }

    func shouldLearnPermanently(from text: String) -> Bool {
        let lower = normalize(text)
        return lower.contains("learn about ") || lower.contains("study ") ||
            lower.contains("remember what you find") || lower.contains("remember this research") ||
            lower.contains("save what you learn") || lower.contains("learn this")
    }

    func research(_ text: String) async throws -> WebResearchBundle {
        let query = cleanedQuery(from: text)
        let cacheKey = query.lowercased()
        pruneCache()

        if let cached = cache[cacheKey], cached.expiresAt > Date() {
            status = "Cached web research"
            lastQuery = query
            lastSourceCount = cached.bundle.sources.count
            lastUsedAt = Date()
            return cached.bundle
        }

        isWorking = true
        status = "Searching…"
        lastQuery = query
        defer { isWorking = false }

        let sources: [WebSource]
        if let url = firstPublicURL(in: text) {
            status = "Reading page…"
            sources = [try await readPage(url)]
        } else {
            let endpoint = searxEndpoint.trimmingCharacters(in: .whitespacesAndNewlines)
            if !endpoint.isEmpty {
                status = "Searching the web…"
                let searxResults = try await searchSearXNG(query: query, endpoint: endpoint)
                if !searxResults.isEmpty {
                    sources = searxResults
                } else if wikipediaEnabled {
                    status = "Trying Wikipedia…"
                    sources = try await searchWikipedia(query: query)
                } else {
                    throw WebBrainError.noResults
                }
            } else if wikipediaEnabled {
                if needsLiveGeneralSearch(text) {
                    throw WebBrainError.generalSearchNeedsSearXNG
                }
                status = "Searching Wikipedia…"
                sources = try await searchWikipedia(query: query)
            } else {
                throw WebBrainError.noSearchProvider
            }
        }

        guard !sources.isEmpty else { throw WebBrainError.noResults }
        let bundle = WebResearchBundle(query: query, sources: Array(sources.prefix(5)), fetchedAt: Date())
        cache[cacheKey] = CacheEntry(bundle: bundle, expiresAt: Date().addingTimeInterval(15 * 60))
        cacheCount = cache.count
        lastSourceCount = bundle.sources.count
        lastUsedAt = Date()
        status = "Web ready — \(bundle.sources.count) source\(bundle.sources.count == 1 ? "" : "s")"
        return bundle
    }

    func testWikipedia() async {
        isWorking = true
        status = "Testing Wikipedia…"
        defer { isWorking = false }
        do {
            let results = try await searchWikipedia(query: "artificial intelligence")
            lastSourceCount = results.count
            lastUsedAt = Date()
            status = results.isEmpty ? "Wikipedia returned no results" : "Wikipedia connected ✓"
        } catch {
            status = "Wikipedia test failed: \(error.localizedDescription)"
        }
    }

    func clearCache() {
        cache.removeAll()
        cacheCount = 0
        status = "Web cache cleared"
    }

    private func searchSearXNG(query: String, endpoint: String) async throws -> [WebSource] {
        guard var base = URL(string: endpoint), base.scheme?.lowercased() == "https" else {
            throw WebBrainError.invalidEndpoint
        }

        if !base.path.hasSuffix("/search") {
            base.appendPathComponent("search")
        }

        guard var components = URLComponents(url: base, resolvingAgainstBaseURL: false) else {
            throw WebBrainError.invalidEndpoint
        }
        var items = components.queryItems ?? []
        items.append(contentsOf: [
            URLQueryItem(name: "q", value: query),
            URLQueryItem(name: "format", value: "json"),
            URLQueryItem(name: "language", value: "en-US"),
            URLQueryItem(name: "safesearch", value: "1")
        ])
        components.queryItems = items
        guard let url = components.url else { throw WebBrainError.invalidEndpoint }

        var request = URLRequest(url: url)
        request.timeoutInterval = 14
        request.setValue("VexNative/0.6", forHTTPHeaderField: "User-Agent")
        let (data, response) = try await URLSession.shared.data(for: request)
        try validate(response)

        struct Envelope: Decodable { let results: [Result] }
        struct Result: Decodable {
            let title: String?
            let url: String?
            let content: String?
            let engine: String?
            let score: Double?
        }

        let decoded = try JSONDecoder().decode(Envelope.self, from: data)
        return decoded.results.compactMap { result in
            guard let rawURL = result.url, let url = URL(string: rawURL), isSafePublicURL(url) else { return nil }
            let title = cleanText(result.title ?? url.host ?? "Web result")
            let snippet = cleanText(result.content ?? "")
            guard !title.isEmpty || !snippet.isEmpty else { return nil }
            return WebSource(
                title: title,
                url: url,
                snippet: snippet,
                provider: result.engine ?? "SearXNG",
                trust: trustScore(for: url)
            )
        }.prefix(5).map { $0 }
    }

    private func searchWikipedia(query: String) async throws -> [WebSource] {
        guard var components = URLComponents(string: "https://en.wikipedia.org/w/api.php") else {
            throw WebBrainError.invalidEndpoint
        }
        components.queryItems = [
            URLQueryItem(name: "action", value: "query"),
            URLQueryItem(name: "generator", value: "search"),
            URLQueryItem(name: "gsrsearch", value: query),
            URLQueryItem(name: "gsrlimit", value: "4"),
            URLQueryItem(name: "prop", value: "extracts"),
            URLQueryItem(name: "exintro", value: "1"),
            URLQueryItem(name: "explaintext", value: "1"),
            URLQueryItem(name: "exchars", value: "700"),
            URLQueryItem(name: "format", value: "json")
        ]
        guard let url = components.url else { throw WebBrainError.invalidEndpoint }

        var request = URLRequest(url: url)
        request.timeoutInterval = 12
        request.setValue("VexNative/0.6", forHTTPHeaderField: "User-Agent")
        let (data, response) = try await URLSession.shared.data(for: request)
        try validate(response)

        struct Envelope: Decodable { let query: Query? }
        struct Query: Decodable { let pages: [String: Page]? }
        struct Page: Decodable {
            let pageid: Int?
            let title: String
            let extract: String?
            let index: Int?
        }

        let decoded = try JSONDecoder().decode(Envelope.self, from: data)
        let pages = decoded.query?.pages?.values.sorted { ($0.index ?? 999) < ($1.index ?? 999) } ?? []
        return pages.compactMap { page in
            guard let pageID = page.pageid,
                  let pageURL = URL(string: "https://en.wikipedia.org/?curid=\(pageID)") else { return nil }
            let snippet = cleanText(page.extract ?? "")
            return WebSource(
                title: cleanText(page.title),
                url: pageURL,
                snippet: snippet,
                provider: "Wikipedia",
                trust: 0.82
            )
        }
    }

    private func readPage(_ url: URL) async throws -> WebSource {
        guard isSafePublicURL(url) else { throw WebBrainError.unsafeURL }
        var request = URLRequest(url: url)
        request.timeoutInterval = 14
        request.setValue("Mozilla/5.0 VexNative/0.6", forHTTPHeaderField: "User-Agent")
        let (data, response) = try await URLSession.shared.data(for: request)
        try validate(response)
        guard data.count <= 3_000_000 else { throw WebBrainError.noResults }

        let html = String(data: data, encoding: .utf8) ?? String(data: data, encoding: .isoLatin1) ?? ""
        let title = extractTitle(from: html) ?? url.host ?? "Web page"
        let text = htmlToText(html)
        guard !text.isEmpty else { throw WebBrainError.noResults }
        return WebSource(
            title: cleanText(title),
            url: url,
            snippet: String(text.prefix(1800)),
            provider: url.host ?? "Web page",
            trust: trustScore(for: url)
        )
    }

    private func validate(_ response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse else { return }
        guard (200...299).contains(http.statusCode) else {
            throw WebBrainError.badResponse(http.statusCode)
        }
    }

    private func cleanedQuery(from text: String) -> String {
        if firstPublicURL(in: text) != nil { return text }
        var query = normalize(text)
        let removable = [
            "search the web for", "search online for", "web search for", "look this up", "look up",
            "find online", "find on the web", "check the internet for", "search the internet for",
            "research", "learn about", "study"
        ]
        for phrase in removable {
            query = query.replacingOccurrences(of: phrase, with: " ")
        }
        query = query.replacingOccurrences(of: "?", with: " ")
        query = query.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
        return query.isEmpty ? text : query
    }

    private func needsLiveGeneralSearch(_ text: String) -> Bool {
        let lower = normalize(text)
        return containsWholePhrase(lower, "latest") || containsWholePhrase(lower, "current") ||
            containsWholePhrase(lower, "today") || lower.contains("news") || lower.contains("weather") ||
            lower.contains("price") || lower.contains("outage") || lower.contains("stock market") ||
            lower.contains("score") || lower.contains("election")
    }

    private func firstPublicURL(in text: String) -> URL? {
        guard let detector = try? NSDataDetector(types: NSTextCheckingResult.CheckingType.link.rawValue) else {
            return nil
        }
        let range = NSRange(text.startIndex..<text.endIndex, in: text)
        return detector.matches(in: text, options: [], range: range)
            .compactMap(\.url)
            .first(where: { isSafePublicURL($0) })
    }

    private func isSafePublicURL(_ url: URL) -> Bool {
        guard url.scheme?.lowercased() == "https", let host = url.host?.lowercased() else { return false }
        if host == "localhost" || host.hasSuffix(".local") || host == "::1" { return false }
        if host.hasPrefix("127.") || host.hasPrefix("10.") || host.hasPrefix("192.168.") || host.hasPrefix("169.254.") {
            return false
        }
        let parts = host.split(separator: ".").compactMap { Int($0) }
        if parts.count == 4, parts[0] == 172, (16...31).contains(parts[1]) { return false }
        return true
    }

    private func trustScore(for url: URL) -> Double {
        let host = url.host?.lowercased() ?? ""
        if host.hasSuffix(".gov") { return 0.95 }
        if host.hasSuffix(".edu") { return 0.90 }
        if host.contains("wikipedia.org") { return 0.82 }
        if host.contains("github.com") || host.hasPrefix("docs.") || host.contains("developer.apple.com") { return 0.84 }
        if host.contains("who.int") || host.contains("cdc.gov") || host.contains("nih.gov") { return 0.94 }
        return 0.62
    }

    private func extractTitle(from html: String) -> String? {
        guard let regex = try? NSRegularExpression(pattern: "<title[^>]*>(.*?)</title>", options: [.caseInsensitive, .dotMatchesLineSeparators]) else {
            return nil
        }
        let range = NSRange(html.startIndex..<html.endIndex, in: html)
        guard let match = regex.firstMatch(in: html, range: range), match.numberOfRanges > 1,
              let titleRange = Range(match.range(at: 1), in: html) else { return nil }
        return htmlToText(String(html[titleRange]))
    }

    private func htmlToText(_ html: String) -> String {
        var text = html
        let patterns = [
            "<script[^>]*>[\\s\\S]*?</script>",
            "<style[^>]*>[\\s\\S]*?</style>",
            "<noscript[^>]*>[\\s\\S]*?</noscript>",
            "<[^>]+>"
        ]
        for pattern in patterns {
            if let regex = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) {
                let range = NSRange(text.startIndex..<text.endIndex, in: text)
                text = regex.stringByReplacingMatches(in: text, options: [], range: range, withTemplate: " ")
            }
        }
        return cleanText(text)
    }

    private func cleanText(_ text: String) -> String {
        var value = text
        let entities: [(String, String)] = [
            ("&amp;", "&"), ("&quot;", "\""), ("&#39;", "'"), ("&apos;", "'"),
            ("&lt;", "<"), ("&gt;", ">"), ("&nbsp;", " ")
        ]
        for (from, to) in entities { value = value.replacingOccurrences(of: from, with: to) }
        return value.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
    }

    private func normalize(_ text: String) -> String {
        text.lowercased()
            .replacingOccurrences(of: "’", with: "'")
            .replacingOccurrences(of: "‘", with: "'")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func containsWholePhrase(_ text: String, _ phrase: String) -> Bool {
        let padded = " " + text + " "
        return padded.contains(" \(phrase) ") || padded.contains(" \(phrase)?") || padded.contains(" \(phrase),")
    }

    private func pruneCache() {
        let now = Date()
        cache = cache.filter { $0.value.expiresAt > now }
        cacheCount = cache.count
    }
}

// MARK: - App integration

extension AppModel {
    func sendWithWeb() async {
        let original = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !original.isEmpty, !isGenerating else { return }

        let web = WebBrain.shared
        guard web.shouldUseWeb(for: original) else {
            await send()
            return
        }

        // Clean up any transient evidence left by an interrupted prior lookup.
        profile.memories.removeAll { $0.source == "web-temporary" }

        let bundle: WebResearchBundle
        do {
            bundle = try await web.research(original)
        } catch {
            // Explicit/current web questions should fail honestly rather than letting a tiny
            // local model confidently invent live information.
            draft = ""
            profile.messages.append(ChatMessage(role: .user, content: original))
            profile.messages.append(ChatMessage(
                role: .assistant,
                content: "My Web Brain couldn't verify that one yet 😭🖤 \(error.localizedDescription)"
            ))
            persist()
            return
        }

        let transient = BrainMemory(
            text: bundle.temporaryMemoryText(userQuestion: original),
            kind: .fact,
            importance: 1.0,
            confidence: max(0.88, bundle.bestTrust),
            evidenceCount: 8,
            lastConfirmedAt: bundle.fetchedAt,
            source: "web-temporary"
        )
        profile.memories.append(transient)

        await send()

        profile.memories.removeAll { $0.id == transient.id || $0.source == "web-temporary" }

        if let index = profile.messages.lastIndex(where: { $0.role == .assistant }),
           !bundle.sourceFooter.isEmpty {
            profile.messages[index].content += "\n\n\(bundle.sourceFooter)"
        }

        if web.shouldLearnPermanently(from: original) {
            for learned in bundle.memoriesForDeliberateLearning() {
                profile.memories = MemoryEngine.deduplicatedAppend(learned, to: profile.memories)
            }
            profile.lastConsolidatedAt = Date()
        }

        persist()
    }
}
