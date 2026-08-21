#!/usr/bin/env python3
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"{label}: expected source block not found")
    return text.replace(old, new, 1)


content_path = Path("VexNative/ContentView.swift")
text = content_path.read_text(encoding="utf-8")

text = replace_once(
    text,
    '    static let searxEndpointKey = "vex.web.searxngEndpoint"\n',
    '    static let searxEndpointKey = "vex.web.searxngEndpoint"\n    static let secondaryBridgeEndpointKey = "vex.web.secondaryBridgeEndpoint"\n',
    "secondary bridge key",
)
text = replace_once(
    text,
    '    var searxEndpoint: String { defaults.string(forKey: Self.searxEndpointKey) ?? "" }\n',
    '    var searxEndpoint: String { defaults.string(forKey: Self.searxEndpointKey) ?? "" }\n    var secondaryBridgeEndpoint: String { defaults.string(forKey: Self.secondaryBridgeEndpointKey) ?? "" }\n',
    "secondary bridge property",
)
text = text.replace(
    '            "i granted you access", "granted you access"\n',
    '            "i granted you access", "granted you access",\n            "kitchen pc", "kitchen computer", "downstairs pc", "downstairs computer",\n            "upstairs pc", "upstairs computer", "primary pc", "second pc"\n',
    1,
)
text = text.replace(
    '            "hard drive", "documents folder", "downloads folder", "desktop file"\n',
    '            "hard drive", "documents folder", "downloads folder", "desktop file",\n            "kitchen pc", "kitchen computer", "downstairs pc", "downstairs computer",\n            "upstairs pc", "upstairs computer", "primary pc", "second pc"\n',
    1,
)
needle = '        query = stripConversationalSearchPrefix(query)\n        query = query.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")\n'
replacement = '''        query = stripConversationalSearchPrefix(query)\n        let nodePhrases = [\n            "on the kitchen pc", "on kitchen pc", "kitchen pc", "kitchen computer",\n            "on the downstairs pc", "downstairs pc", "downstairs computer",\n            "on the upstairs pc", "upstairs pc", "upstairs computer",\n            "on the primary pc", "primary pc", "on the second pc", "second pc"\n        ]\n        for phrase in nodePhrases {\n            query = query.replacingOccurrences(of: phrase, with: " ")\n        }\n        query = query.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")\n'''
text = replace_once(text, needle, replacement, "node phrase cleanup")
old_call = '                let searxResults = try await searchSearXNG(query: query, endpoint: endpoint, scope: scope)\n'
new_call = '                let searxResults = try await searchBridgeMesh(query: query, primaryEndpoint: endpoint, scope: scope, requestText: text)\n'
text = replace_once(text, old_call, new_call, "dual-PC search dispatch")

search_marker = '''    private func searchSearXNG(\n        query: String,\n        endpoint: String,\n        scope: BridgeSearchScope\n    ) async throws -> [WebSource] {\n'''
mesh_helpers = r'''    private enum BridgeNodeTarget {
        case primary
        case secondary
        case all
    }

    private func bridgeNodeTarget(for text: String) -> BridgeNodeTarget {
        let lower = normalize(text)
        if ["kitchen pc", "kitchen computer", "downstairs pc", "downstairs computer", "second pc"]
            .contains(where: { lower.contains($0) }) {
            return .secondary
        }
        if ["upstairs pc", "upstairs computer", "primary pc", "main pc"]
            .contains(where: { lower.contains($0) }) {
            return .primary
        }
        return .all
    }

    private func searchBridgeMesh(
        query: String,
        primaryEndpoint: String,
        scope: BridgeSearchScope,
        requestText: String
    ) async throws -> [WebSource] {
        guard let primaryURL = URL(string: primaryEndpoint),
              VexBridgeNetworking.isBridgeURL(primaryURL)
        else {
            return try await searchSearXNG(query: query, endpoint: primaryEndpoint, scope: scope)
        }

        let secondary = secondaryBridgeEndpoint.trimmingCharacters(in: .whitespacesAndNewlines)
        let secondaryValid = secondary != primaryEndpoint &&
            URL(string: secondary).map(VexBridgeNetworking.isBridgeURL) == true
        let target = bridgeNodeTarget(for: requestText)

        var combined: [WebSource] = []
        var firstError: Error?

        func appendUnique(_ incoming: [WebSource]) {
            var seen = Set(combined.map { $0.url.absoluteString })
            for source in incoming where seen.insert(source.url.absoluteString).inserted {
                combined.append(source)
            }
        }

        if target != .secondary {
            do {
                appendUnique(try await searchSearXNG(query: query, endpoint: primaryEndpoint, scope: scope))
            } catch {
                firstError = error
            }
        }

        if target != .primary {
            if secondaryValid {
                let secondaryScope: BridgeSearchScope = (target == .all && scope == .both) ? .pc : scope
                do {
                    appendUnique(try await searchSearXNG(query: query, endpoint: secondary, scope: secondaryScope))
                } catch {
                    if firstError == nil { firstError = error }
                }
            } else if target == .secondary {
                throw WebBrainError.noSearchProvider
            }
        }

        if combined.isEmpty, let firstError { throw firstError }
        return Array(combined.prefix(10))
    }

'''
if search_marker not in text:
    raise SystemExit("ContentView.swift: searchSearXNG marker missing")
text = text.replace(search_marker, mesh_helpers + search_marker, 1)
content_path.write_text(text, encoding="utf-8")

brain_path = Path("VexNative/Views/BrainView.swift")
brain = brain_path.read_text(encoding="utf-8")
brain = replace_once(
    brain,
    '    @AppStorage(WebBrain.searxEndpointKey) private var searxEndpoint = ""\n',
    '    @AppStorage(WebBrain.searxEndpointKey) private var searxEndpoint = ""\n    @AppStorage(WebBrain.secondaryBridgeEndpointKey) private var secondaryBridgeEndpoint = ""\n',
    "second endpoint AppStorage",
)
primary_block = '''                    VStack(alignment: .leading, spacing: 6) {\n                        Text("Vex Bridge / SearXNG endpoint")\n                            .font(.subheadline.weight(.semibold))\n                        TextField("https://search.example.com", text: $searxEndpoint)\n                            .textInputAutocapitalization(.never)\n                            .autocorrectionDisabled()\n                            .keyboardType(.URL)\n                        Text("Paste the full Vex Bridge pairing endpoint here, including its token and certificate pin, or use an HTTPS SearXNG server with JSON search enabled. Without either one, Vex can still read public HTTPS links and use Wikipedia for encyclopedia-style research.")\n                            .font(.caption)\n                            .foregroundStyle(.secondary)\n                    }\n'''
second_block = primary_block + '''\n                    VStack(alignment: .leading, spacing: 6) {\n                        Text("Second / kitchen PC Bridge endpoint")\n                            .font(.subheadline.weight(.semibold))\n                        TextField("https://192.168.x.x:8765?token=…&pin=…", text: $secondaryBridgeEndpoint)\n                            .textInputAutocapitalization(.never)\n                            .autocorrectionDisabled()\n                            .keyboardType(.URL)\n                        Text("Optional second paired computer. Vex mirrors brain memory to both PCs, searches both file indexes by default, and targets this node when you say kitchen/downstairs PC. Each PC keeps its own private token and certificate pin.")\n                            .font(.caption)\n                            .foregroundStyle(.secondary)\n                    }\n\n                    HStack {\n                        Text("Expansion brain")\n                        Spacer()\n                        Text(app.pcBrainStatus)\n                            .foregroundStyle(app.pcBrainConnected ? .green : .secondary)\n                            .multilineTextAlignment(.trailing)\n                    }\n'''
brain = replace_once(brain, primary_block, second_block, "second bridge UI")
brain_path.write_text(brain, encoding="utf-8")

app_path = Path("VexNative/AppModel.swift")
app = app_path.read_text(encoding="utf-8")
actor_start = app.find("private actor PCBrainExpansion {")
if actor_start < 0:
    raise SystemExit("AppModel.swift: PCBrainExpansion actor missing")
new_actor = r'''private actor PCBrainExpansion {
    static let shared = PCBrainExpansion()
    private let primaryEndpointKey = "vex.web.searxngEndpoint"
    private let secondaryEndpointKey = "vex.web.secondaryBridgeEndpoint"

    private struct MemoryDTO: Encodable {
        let text: String
        let kind: String
        let importance: Double
        let confidence: Double
        let evidenceCount: Int
        let source: String
        let createdAt: Double
    }

    private struct TurnDTO: Encodable {
        let id: String
        let role: String
        let content: String
        let createdAt: Double
    }

    private struct RequestBody: Encodable {
        let query: String
        let memories: [MemoryDTO]
        let turns: [TurnDTO]
    }

    private struct ResponseBody: Decodable {
        struct Stats: Decodable {
            let memories: Int
            let turns: Int
        }
        let context: String
        let stats: Stats
        let node_name: String?
    }

    func context(for query: String, profile: BrainProfile) async -> PCBrainExpansionResult {
        let rawEndpoints = [primaryEndpointKey, secondaryEndpointKey].compactMap { key in
            UserDefaults.standard.string(forKey: key)?
                .trimmingCharacters(in: .whitespacesAndNewlines)
        }
        var seen = Set<String>()
        let endpoints = rawEndpoints.filter { endpoint in
            guard !endpoint.isEmpty, seen.insert(endpoint).inserted,
                  let url = URL(string: endpoint)
            else { return false }
            return VexBridgeNetworking.isBridgeURL(url)
        }
        guard !endpoints.isEmpty else {
            return PCBrainExpansionResult(text: "", connected: false, status: "Phone brain only")
        }

        let memories = profile.memories
            .filter { memory in
                let source = memory.source ?? ""
                return source != "web-temporary" && source != "pc-brain-temporary"
            }
            .suffix(400)
            .map { memory in
                MemoryDTO(
                    text: String(memory.text.prefix(5000)),
                    kind: memory.kind.rawValue,
                    importance: memory.importance,
                    confidence: memory.confidence ?? 0.70,
                    evidenceCount: max(1, memory.evidenceCount ?? 1),
                    source: memory.source ?? "iphone",
                    createdAt: memory.createdAt.timeIntervalSince1970
                )
            }

        let turns = profile.messages.suffix(600).map { turn in
            TurnDTO(
                id: turn.id.uuidString,
                role: turn.role.rawValue,
                content: String(turn.content.prefix(6000)),
                createdAt: turn.createdAt.timeIntervalSince1970
            )
        }

        let payload = RequestBody(
            query: String(query.prefix(1200)),
            memories: Array(memories),
            turns: turns
        )

        var contextBlocks: [String] = []
        var online = 0
        var memoryTotal = 0
        var turnTotal = 0

        for (index, endpoint) in endpoints.enumerated() {
            guard let root = URL(string: endpoint),
                  let url = brainURL(root: root, path: "/brain/context")
            else { continue }

            do {
                var request = URLRequest(url: url)
                request.httpMethod = "POST"
                request.timeoutInterval = 3.2
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                request.httpBody = try JSONEncoder().encode(payload)

                let (data, response) = try await VexBridgeNetworking.data(for: request)
                guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else { continue }
                let decoded = try JSONDecoder().decode(ResponseBody.self, from: data)
                online += 1
                memoryTotal += decoded.stats.memories
                turnTotal += decoded.stats.turns
                let node = decoded.node_name?.trimmingCharacters(in: .whitespacesAndNewlines)
                let label = (node?.isEmpty == false ? node! : "PC \(index + 1)")
                let body = decoded.context.trimmingCharacters(in: .whitespacesAndNewlines)
                if !body.isEmpty {
                    contextBlocks.append("[\(label)]\n\(body)")
                }
            } catch {
                continue
            }
        }

        guard online > 0 else {
            return PCBrainExpansionResult(text: "", connected: false, status: "Phone brain only")
        }

        let merged = contextBlocks.joined(separator: "\n\n")
        let status = "PC mesh • \(online)/\(endpoints.count) online • \(memoryTotal) memories • \(turnTotal) turns"
        return PCBrainExpansionResult(
            text: String(merged.prefix(4200)),
            connected: true,
            status: status
        )
    }

    private func brainURL(root: URL, path: String) -> URL? {
        guard var components = URLComponents(url: root, resolvingAgainstBaseURL: false) else { return nil }
        components.path = path
        return components.url
    }
}
'''
app = app[:actor_start] + new_actor + "\n"
app_path.write_text(app, encoding="utf-8")

bridge_path = Path("Bridge/vex_bridge.py")
bridge = bridge_path.read_text(encoding="utf-8")
bridge = replace_once(
    bridge,
    'SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | {".pdf", ".docx"}\n',
    'SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | {".pdf", ".docx"}\nMUSIC_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".aiff", ".aif", ".mid", ".midi", ".als", ".flp", ".rpp", ".aup3", ".sesx", ".cpr", ".npr", ".band", ".logicx", ".adg", ".vstpreset", ".fxp", ".fxb"}\n',
    "music extension metadata",
)
indexed_marker = '''@dataclass\nclass IndexedDocument:\n    path: str\n    name: str\n    text: str\n    tokens: set[str]\n    mtime: float\n\n\n'''
music_type = indexed_marker + '''@dataclass\nclass MusicAsset:\n    path: str\n    name: str\n    suffix: str\n    size: int\n    mtime: float\n    tokens: set[str]\n\n\n'''
bridge = replace_once(bridge, indexed_marker, music_type, "MusicAsset type")
bridge = replace_once(
    bridge,
    '        self.documents: list[IndexedDocument] = []\n        self.lock = threading.Lock()\n',
    '        self.documents: list[IndexedDocument] = []\n        self.music_assets: list[MusicAsset] = []\n        self.lock = threading.Lock()\n',
    "music asset index state",
)
search_music = r'''
    def search_music(self, query: str, limit: int = 5) -> list[dict]:
        qset = set(words(query))
        if not qset:
            return []
        with self.lock:
            assets = list(self.music_assets)
        scored = []
        for asset in assets:
            overlap = len(qset & asset.tokens)
            if overlap == 0:
                continue
            name_lower = asset.name.lower()
            name_hits = sum(1 for word in qset if word in name_lower)
            score = overlap / max(2, len(qset)) + name_hits * 0.45
            scored.append((score, asset))
        scored.sort(key=lambda item: item[0], reverse=True)

        node = socket.gethostname() or "PC"
        results = []
        for score, asset in scored[:limit]:
            digest = hashlib.sha256(asset.path.encode("utf-8", "ignore")).hexdigest()[:16]
            results.append({
                "title": f"[MUSIC {node}] {asset.name}",
                "url": f"https://vexbridge.invalid/music/{digest}",
                "content": f"Music/project asset on {node}: {asset.path} | type {asset.suffix} | size {asset.size} bytes",
                "engine": "Vex Bridge music files",
                "score": round(float(score), 4),
            })
        return results

'''
marker = '\n\ndef best_snippet(text: str, qwords: list[str], width: int = 900) -> str:\n'
if marker not in bridge:
    raise SystemExit("vex_bridge.py: best_snippet marker missing")
bridge = bridge.replace(marker, "\n" + search_music + marker, 1)
bridge = bridge.replace('"title": f"[PC] {doc.name}",', '"title": f"[PC {socket.gethostname() or \'PC\'}] {doc.name}",', 1)
bridge = bridge.replace(
    '"context": context,\n                "stats": stats,\n',
    '"context": context,\n                "stats": stats,\n                "node_name": socket.gethostname() or "PC",\n',
    1,
)
bridge = bridge.replace(
    '        local = STATE.index.search(query, limit=5) if scope in {"pc", "both"} else []\n',
    '        local = STATE.index.search(query, limit=5) if scope in {"pc", "both"} else []\n        if scope in {"pc", "both"}:\n            local += STATE.index.search_music(query, limit=5)\n',
    1,
)
bridge_path.write_text(bridge, encoding="utf-8")

full_path = Path("Bridge/vex_bridge_full.py")
full = full_path.read_text(encoding="utf-8")
full = replace_once(full, '        documents = []\n        count = 0\n', '        documents = []\n        music_assets = []\n        count = 0\n', "full scan music list")
old_file_gate = '''                        path = current / filename\n                        if path.suffix.lower() not in core.SUPPORTED_EXTENSIONS:\n                            continue\n                        key = norm(path)\n'''
new_file_gate = '''                        path = current / filename\n                        suffix = path.suffix.lower()\n                        key = norm(path)\n                        if suffix in core.MUSIC_EXTENSIONS and key not in seen_files:\n                            try:\n                                stat = path.stat()\n                                music_assets.append(core.MusicAsset(\n                                    path=str(path),\n                                    name=path.name,\n                                    suffix=suffix,\n                                    size=stat.st_size,\n                                    mtime=stat.st_mtime,\n                                    tokens=set(core.words(path.name + " " + str(path.parent))),\n                                ))\n                            except Exception:\n                                pass\n                        if suffix not in core.SUPPORTED_EXTENSIONS:\n                            continue\n'''
full = replace_once(full, old_file_gate, new_file_gate, "full scan music metadata")
full = full.replace(
    '                            with self.lock:\n                                self.documents = list(documents)\n',
    '                            with self.lock:\n                                self.documents = list(documents)\n                                self.music_assets = list(music_assets)\n',
    1,
)
full = full.replace(
    '        with self.lock:\n            self.documents = documents\n            self.last_indexed = time.time()\n',
    '        with self.lock:\n            self.documents = documents\n            self.music_assets = music_assets\n            self.last_indexed = time.time()\n',
    1,
)
full = full.replace('VERSION = "0.8.0"', 'VERSION = "0.8.1"', 1)
full_path.write_text(full, encoding="utf-8")

for path, markers in [
    (content_path, ["secondaryBridgeEndpointKey", "searchBridgeMesh", "BridgeNodeTarget"]),
    (brain_path, ["Second / kitchen PC Bridge endpoint", "Expansion brain"]),
    (app_path, ["PC mesh", "secondaryEndpointKey", "suffix(600)"]),
    (bridge_path, ["MUSIC_EXTENSIONS", "search_music", "node_name"]),
    (full_path, ['VERSION = "0.8.1"', "music_assets = []"]),
]:
    data = path.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in data:
            raise SystemExit(f"{path}: missing v0.8.1 marker: {marker}")

print("Applied v0.8.1 dual-PC mesh + music metadata foundation patch")
