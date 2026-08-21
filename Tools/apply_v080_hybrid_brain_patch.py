#!/usr/bin/env python3
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"{label}: expected source block not found")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# iPhone: PC expansion-brain state + one-round-trip context retrieval.
# The phone remains authoritative for live state/persona; the PC is an external
# long-term conversation/memory vault and retrieval processor.
# ---------------------------------------------------------------------------
app_path = Path("VexNative/AppModel.swift")
app = app_path.read_text(encoding="utf-8")

app = replace_once(
    app,
    '''    @Published var exportURL: URL?\n    @Published var pendingPhotoData: Data?\n    @Published var pendingPhotoContext: String?\n\n    private let store = LocalStore.shared\n''',
    '''    @Published var exportURL: URL?\n    @Published var pendingPhotoData: Data?\n    @Published var pendingPhotoContext: String?\n    @Published var pcBrainConnected = false\n    @Published var pcBrainStatus = "Phone brain only"\n\n    private let store = LocalStore.shared\n''',
    "PC brain published state",
)

app = replace_once(
    app,
    '''        let focusedQwen3Turn = isQwen3 && isFocusedQwen3Turn(text)\n''',
    '''        let expansionQuery = text.isEmpty ? modelText : text\n        let expansion = await PCBrainExpansion.shared.context(\n            for: expansionQuery,\n            profile: profile\n        )\n        pcBrainConnected = expansion.connected\n        pcBrainStatus = expansion.status\n        let pcBrainContext = expansion.text\n\n        let focusedQwen3Turn = isQwen3 && isFocusedQwen3Turn(text)\n''',
    "PC brain retrieval before prompt",
)

app = replace_once(
    app,
    '''            newestUserText: modelText,\n            isQwen3: isQwen3\n''',
    '''            newestUserText: modelText,\n            isQwen3: isQwen3,\n            pcBrainContext: pcBrainContext\n''',
    "PC context main prompt",
)

app = replace_once(
    app,
    '''                    newestUserText: modelText,\n                    isQwen3: true,\n                    retryMode: true\n''',
    '''                    newestUserText: modelText,\n                    isQwen3: true,\n                    retryMode: true,\n                    pcBrainContext: pcBrainContext\n''',
    "PC context retry prompt",
)

pc_client = r'''

private struct PCBrainExpansionResult: Sendable {
    let text: String
    let connected: Bool
    let status: String
}

private actor PCBrainExpansion {
    static let shared = PCBrainExpansion()
    private let endpointKey = "vex.web.searxngEndpoint"

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
    }

    func context(for query: String, profile: BrainProfile) async -> PCBrainExpansionResult {
        let endpoint = UserDefaults.standard.string(forKey: endpointKey)?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !endpoint.isEmpty,
              let root = URL(string: endpoint),
              VexBridgeNetworking.isBridgeURL(root),
              let url = brainURL(root: root, path: "/brain/context")
        else {
            return PCBrainExpansionResult(text: "", connected: false, status: "Phone brain only")
        }

        let memories = profile.memories
            .filter { memory in
                let source = memory.source ?? ""
                return source != "web-temporary" && source != "pc-brain-temporary"
            }
            .suffix(300)
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

        let turns = profile.messages.suffix(160).map { turn in
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

        do {
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.timeoutInterval = 4.5
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(payload)

            let (data, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
                return PCBrainExpansionResult(text: "", connected: false, status: "PC brain unavailable")
            }
            let decoded = try JSONDecoder().decode(ResponseBody.self, from: data)
            let status = "PC brain • \(decoded.stats.memories) memories • \(decoded.stats.turns) turns"
            return PCBrainExpansionResult(
                text: String(decoded.context.prefix(4200)),
                connected: true,
                status: status
            )
        } catch {
            return PCBrainExpansionResult(text: "", connected: false, status: "Phone brain only")
        }
    }

    private func brainURL(root: URL, path: String) -> URL? {
        guard var components = URLComponents(url: root, resolvingAgainstBaseURL: false) else { return nil }
        components.path = path
        return components.url
    }
}
'''
app += pc_client
app_path.write_text(app, encoding="utf-8")


# ---------------------------------------------------------------------------
# Prompt: external PC context supplements, but never overrides, phone state or
# Star's newest correction. Qwen3 gets a compact block that fits its small context.
# ---------------------------------------------------------------------------
prompt_path = Path("VexNative/Core/PromptComposer.swift")
prompt = prompt_path.read_text(encoding="utf-8")

prompt = replace_once(
    prompt,
    '''        maxRecentMessages: Int = 6,\n        retryMode: Bool = false\n    ) -> String {\n''',
    '''        maxRecentMessages: Int = 6,\n        retryMode: Bool = false,\n        pcBrainContext: String? = nil\n    ) -> String {\n''',
    "PromptComposer PC context parameter",
)

prompt = replace_once(
    prompt,
    '''                newestUserText: newestUserText,\n                webEvidence: webEvidence\n            )\n''',
    '''                newestUserText: newestUserText,\n                webEvidence: webEvidence,\n                pcBrainContext: pcBrainContext\n            )\n''',
    "web prompt receives PC context",
)

memory_block = '''        let memoryBlock: String\n        if relevant.isEmpty {\n            memoryBlock = "(none)"\n        } else {\n            memoryBlock = relevant.map { memory in\n                let text = isQwen3 ? String(memory.text.prefix(100)) : memory.text\n                return "- [\\(memory.kind.rawValue)] \\(text)"\n            }.joined(separator: "\\n")\n        }\n'''
expanded_memory_block = memory_block + '''\n        let expansionBlock: String\n        if let pcBrainContext, !pcBrainContext.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {\n            expansionBlock = isQwen3\n                ? String(pcBrainContext.prefix(1000))\n                : String(pcBrainContext.prefix(3000))\n        } else {\n            expansionBlock = "(PC expansion brain unavailable for this turn)"\n        }\n'''
prompt = replace_once(prompt, memory_block, expanded_memory_block, "PC expansion prompt block")

prompt = prompt.replace(
    '''            RELEVANT MEMORY\n            \\(memoryBlock)\n\n            RESPONSE RULES\n''',
    '''            RELEVANT MEMORY\n            \\(memoryBlock)\n\n            PC EXPANSION BRAIN\n            \\(expansionBlock)\n            Treat this as retrieved older evidence. The newest Star message and CURRENT VEX STATE always win conflicts.\n\n            RESPONSE RULES\n''',
)
prompt = prompt.replace(
    '''            RELEVANT LONG-TERM MEMORY\n            \\(memoryBlock)\n\n            VOICE SHAPING\n''',
    '''            RELEVANT LONG-TERM MEMORY\n            \\(memoryBlock)\n\n            PC EXPANSION BRAIN\n            \\(expansionBlock)\n            Treat this as retrieved older evidence. The newest Star message and CURRENT VEX STATE always win conflicts.\n\n            VOICE SHAPING\n''',
)

prompt = replace_once(
    prompt,
    '''        newestUserText: String,\n        webEvidence: BrainMemory\n    ) -> String {\n''',
    '''        newestUserText: String,\n        webEvidence: BrainMemory,\n        pcBrainContext: String?\n    ) -> String {\n''',
    "web helper PC parameter",
)

prompt = replace_once(
    prompt,
    '''        let evidence = String(webEvidence.text.prefix(1500))\n        let user = String(newestUserText.prefix(700))\n''',
    '''        let evidence = String(webEvidence.text.prefix(1500))\n        let user = String(newestUserText.prefix(700))\n        let pcContext = String((pcBrainContext ?? "(none)").prefix(800))\n''',
    "web helper PC block value",
)

prompt = replace_once(
    prompt,
    '''        RETRIEVED EVIDENCE\n        \\(evidence)\n        """\n''',
    '''        RETRIEVED EVIDENCE\n        \\(evidence)\n\n        PC EXPANSION BRAIN\n        \\(pcContext)\n        Older PC memory is supplemental only; newest user facts and retrieved web evidence win conflicts.\n        """\n''',
    "web helper PC context text",
)

for marker in ["PC EXPANSION BRAIN", "pcBrainContext: String? = nil", "expansionBlock"]:
    if marker not in prompt:
        raise SystemExit(f"PromptComposer missing v0.8.0 marker: {marker}")
prompt_path.write_text(prompt, encoding="utf-8")


# ---------------------------------------------------------------------------
# UI: tiny always-visible signal that both phone + PC brains are participating.
# ---------------------------------------------------------------------------
content_path = Path("VexNative/ContentView.swift")
content = content_path.read_text(encoding="utf-8")
content = replace_once(
    content,
    '''            if web.isWorking {\n                Text("• 🌐")\n                    .font(.caption)\n            }\n\n            Spacer()\n''',
    '''            if web.isWorking {\n                Text("• 🌐")\n                    .font(.caption)\n            }\n\n            if app.pcBrainConnected {\n                Text("• 🧠 PC")\n                    .font(.caption)\n                    .foregroundStyle(VexTheme.muted)\n            }\n\n            Spacer()\n''',
    "PC brain status strip",
)
content_path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Windows Bridge: persistent SQLite autobiographical vault + retrieval processor.
# ---------------------------------------------------------------------------
bridge_path = Path("Bridge/vex_bridge.py")
bridge = bridge_path.read_text(encoding="utf-8")

if "import sqlite3\n" not in bridge:
    bridge = bridge.replace("import secrets\n", "import secrets\nimport sqlite3\n", 1)

state_marker = "\n\nclass BridgeState:\n"
brain_vault = r'''

_BRAIN_STOP_WORDS = {
    "the", "and", "for", "that", "this", "with", "from", "have", "has", "was", "were",
    "are", "you", "your", "but", "not", "its", "into", "then", "than", "just", "they",
    "them", "she", "her", "his", "our", "out", "all", "star", "vex"
}


def _brain_normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower()).strip()


def _brain_terms(text: str) -> set[str]:
    return {
        word for word in re.findall(r"[a-z0-9']+", _brain_normalize(text))
        if len(word) > 2 and word not in _BRAIN_STOP_WORDS
    }


class BrainVault:
    """Persistent external autobiographical memory for Vex.

    The iPhone remains the authority for persona/current state. This vault stores
    trusted phone memories plus a large deduplicated conversation archive and
    performs CPU-side retrieval so the tiny phone model sees only relevant history.
    """

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self._initialize()

    def _connect(self):
        conn = sqlite3.connect(str(self.path), timeout=8)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS brain_memories (
                    memory_key TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    importance REAL NOT NULL,
                    confidence REAL NOT NULL,
                    evidence_count INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    last_seen_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS brain_turns (
                    turn_id TEXT PRIMARY KEY,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_brain_turns_created ON brain_turns(created_at DESC)")
            conn.commit()

    def sync(self, memories: list[dict], turns: list[dict]) -> None:
        now = time.time()
        with self.lock, self._connect() as conn:
            for item in memories[:1000]:
                text = str(item.get("text") or "").strip()
                if not text:
                    continue
                key = hashlib.sha256(_brain_normalize(text).encode("utf-8")).hexdigest()
                kind = str(item.get("kind") or "note")[:40]
                importance = max(0.0, min(1.0, float(item.get("importance") or 0.65)))
                confidence = max(0.0, min(1.0, float(item.get("confidence") or 0.70)))
                evidence = max(1, int(item.get("evidenceCount") or 1))
                source = str(item.get("source") or "iphone")[:500]
                created = float(item.get("createdAt") or now)
                conn.execute("""
                    INSERT INTO brain_memories
                        (memory_key, text, kind, importance, confidence, evidence_count, source, created_at, last_seen_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(memory_key) DO UPDATE SET
                        text=excluded.text,
                        kind=excluded.kind,
                        importance=MAX(brain_memories.importance, excluded.importance),
                        confidence=MAX(brain_memories.confidence, excluded.confidence),
                        evidence_count=MAX(brain_memories.evidence_count, excluded.evidence_count),
                        source=excluded.source,
                        last_seen_at=excluded.last_seen_at
                """, (key, text, kind, importance, confidence, evidence, source, created, now))

            for item in turns[:500]:
                uid = str(item.get("id") or "").strip()
                content = str(item.get("content") or "").strip()
                role = str(item.get("role") or "user")[:20]
                if not uid or not content:
                    continue
                created = float(item.get("createdAt") or now)
                conn.execute(
                    "INSERT OR IGNORE INTO brain_turns(turn_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                    (uid, role, content, created),
                )

            # Keep a very large history without letting a runaway log grow forever.
            conn.execute("""
                DELETE FROM brain_turns
                WHERE turn_id IN (
                    SELECT turn_id FROM brain_turns
                    ORDER BY created_at DESC
                    LIMIT -1 OFFSET 50000
                )
            """)
            conn.commit()

    def stats(self) -> dict:
        with self.lock, self._connect() as conn:
            memories = int(conn.execute("SELECT COUNT(*) FROM brain_memories").fetchone()[0])
            turns = int(conn.execute("SELECT COUNT(*) FROM brain_turns").fetchone()[0])
        return {"memories": memories, "turns": turns}

    def context(self, query: str, max_chars: int = 3800) -> str:
        qterms = _brain_terms(query)
        now = time.time()
        with self.lock, self._connect() as conn:
            memory_rows = conn.execute("""
                SELECT text, kind, importance, confidence, evidence_count, source, created_at
                FROM brain_memories
                ORDER BY last_seen_at DESC
                LIMIT 5000
            """).fetchall()
            turn_rows = conn.execute("""
                SELECT role, content, created_at
                FROM brain_turns
                ORDER BY created_at DESC
                LIMIT 4000
            """).fetchall()

        ranked_memories = []
        anchor_memories = []
        for row in memory_rows:
            text, kind, importance, confidence, evidence, source, created = row
            terms = _brain_terms(text)
            overlap = len(qterms & terms)
            union = max(1, len(qterms | terms))
            lexical = overlap / union
            authority = float(importance) * 0.9 + float(confidence) * 0.8 + min(0.35, int(evidence) * 0.025)
            if kind in {"rule", "lesson"}:
                authority += 0.55
            if str(source).startswith("user-"):
                authority += 0.30
            score = lexical * 4.2 + overlap * 0.55 + authority
            ranked_memories.append((score, text, kind))
            if kind in {"rule", "lesson"} and float(importance) >= 0.90 and float(confidence) >= 0.88:
                anchor_memories.append((authority, text, kind))

        ranked_memories.sort(key=lambda item: item[0], reverse=True)
        anchor_memories.sort(key=lambda item: item[0], reverse=True)

        chosen_memories = []
        seen_memory = set()
        for _, text, kind in anchor_memories[:3] + ranked_memories[:12]:
            key = _brain_normalize(text)
            if key in seen_memory:
                continue
            seen_memory.add(key)
            chosen_memories.append((text, kind))
            if len(chosen_memories) >= 12:
                break

        ranked_turns = []
        recent_turns = []
        for idx, (role, content, created) in enumerate(turn_rows):
            terms = _brain_terms(content)
            overlap = len(qterms & terms)
            lexical = overlap / max(1, len(qterms | terms))
            age_days = max(0.0, (now - float(created)) / 86400.0)
            recency = 1.0 / (1.0 + age_days / 30.0)
            score = lexical * 5.0 + overlap * 0.60 + recency * 0.35
            if overlap > 0:
                ranked_turns.append((score, role, content, created))
            if idx < 6:
                recent_turns.append((role, content, created))

        ranked_turns.sort(key=lambda item: item[0], reverse=True)
        chosen_turns = []
        seen_turn = set()
        for _, role, content, created in ranked_turns[:10]:
            key = (role, _brain_normalize(content))
            if key in seen_turn:
                continue
            seen_turn.add(key)
            chosen_turns.append((role, content, created))
        for role, content, created in reversed(recent_turns):
            key = (role, _brain_normalize(content))
            if key in seen_turn:
                continue
            seen_turn.add(key)
            chosen_turns.append((role, content, created))
            if len(chosen_turns) >= 12:
                break

        chunks = []
        if chosen_memories:
            chunks.append("PC LONG-TERM MEMORY:")
            for text, kind in chosen_memories:
                chunks.append(f"- [{kind}] {text[:700]}")
        if chosen_turns:
            chunks.append("RELEVANT / RECENT PAST CHAT:")
            for role, content, _ in chosen_turns:
                label = "Star" if role == "user" else "Vex"
                clean = re.sub(r"\s+", " ", content).strip()
                chunks.append(f"- {label}: {clean[:650]}")

        return "\n".join(chunks)[:max_chars]


# v0.8.0 image selection: prefer images from actually relevant result pages.
def web_image_search(query: str, limit: int = 6) -> list[dict]:
    try:
        import requests
        from bs4 import BeautifulSoup

        qterms = _brain_terms(query)
        pages = web_search(query, limit=8)
        candidates = []
        bad_tokens = {"logo", "icon", "avatar", "sprite", "banner", "favicon", "emoji", "advert", "tracking"}

        for rank, page in enumerate(pages):
            page_url = str(page.get("url") or "")
            page_title = str(page.get("title") or "")
            if not page_url.startswith("https://"):
                continue
            try:
                response = requests.get(
                    page_url,
                    headers={"User-Agent": "Mozilla/5.0 VexBridge/0.8"},
                    timeout=8,
                    allow_redirects=True,
                )
                response.raise_for_status()
                ctype = response.headers.get("Content-Type", "").lower()
                if "html" not in ctype:
                    continue
                soup = BeautifulSoup(response.text[:1_500_000], "html.parser")
            except Exception:
                continue

            page_terms = _brain_terms(page_title + " " + page_url)
            page_overlap = len(qterms & page_terms)

            raw_candidates = []
            for meta in soup.select('meta[property="og:image"], meta[name="twitter:image"], meta[property="twitter:image"]'):
                raw_candidates.append((meta.get("content") or "", "", 3.0))
            for img in soup.find_all("img")[:120]:
                src = img.get("src") or img.get("data-src") or img.get("data-lazy-src") or ""
                alt = " ".join(filter(None, [img.get("alt"), img.get("title")]))
                bonus = 0.0
                try:
                    width = int(str(img.get("width") or "0").replace("px", ""))
                    height = int(str(img.get("height") or "0").replace("px", ""))
                    if width >= 240 and height >= 180:
                        bonus += 1.2
                except Exception:
                    pass
                raw_candidates.append((src, alt, bonus))

            for raw_url, alt, type_bonus in raw_candidates:
                if not raw_url:
                    continue
                image_url = urllib.parse.urljoin(response.url, raw_url)
                if not _safe_public_https_url(image_url):
                    continue
                haystack = f"{page_title} {alt} {image_url}"
                terms = _brain_terms(haystack)
                overlap = len(qterms & terms)
                lowered = haystack.lower()
                penalty = 7.0 if any(token in lowered for token in bad_tokens) else 0.0
                score = overlap * 3.6 + page_overlap * 1.8 + type_bonus + max(0.0, 1.5 - rank * 0.20) - penalty
                # Multi-term visual requests must match more than one meaningful term.
                required = 2 if len(qterms) >= 3 else 1
                if overlap < required and page_overlap < required:
                    continue
                if score < 4.5:
                    continue
                candidates.append({
                    "title": alt.strip() or page_title or query,
                    "image_url": image_url,
                    "source_url": response.url,
                    "score": score,
                })

        candidates.sort(key=lambda item: item.get("score", 0), reverse=True)
        results = []
        seen = set()
        for item in candidates:
            key = item["image_url"].split("?")[0]
            if key in seen:
                continue
            seen.add(key)
            results.append({
                "title": item["title"],
                "image_url": item["image_url"],
                "source_url": item["source_url"],
            })
            if len(results) >= limit:
                break
        return results
    except Exception as exc:
        print(f"[image-search] relevance search failed: {exc}", flush=True)
        return []
'''
if state_marker not in bridge:
    raise SystemExit("vex_bridge.py: BridgeState marker missing for PC brain")
bridge = bridge.replace(state_marker, brain_vault + state_marker, 1)

bridge = replace_once(
    bridge,
    '''class BridgeState:\n    def __init__(self, config: dict):\n        self.config = config\n        self.index = LocalIndex(config.get("folders", []))\n        self.started = time.time()\n''',
    '''class BridgeState:\n    def __init__(self, config: dict):\n        self.config = config\n        self.index = LocalIndex(config.get("folders", []))\n        self.brain = BrainVault(app_dir() / "brain_vault.sqlite3")\n        self.started = time.time()\n''',
    "BridgeState BrainVault",
)

# Add brain stats/context to authenticated GET endpoints before the normal search gate.
search_gate = '''        if parsed.path != "/search":\n            self._json(404, {"error": "not found"})\n            return\n\n        query = (params.get("q") or [""])[0].strip()\n'''
brain_get = '''        if parsed.path == "/brain/status":\n            self._json(200, {"ok": True, "stats": STATE.brain.stats()})\n            return\n\n        if parsed.path == "/brain/context":\n            query = (params.get("q") or [""])[0].strip()\n            self._json(200, {\n                "context": STATE.brain.context(query),\n                "stats": STATE.brain.stats(),\n            })\n            return\n\n''' + search_gate
bridge = replace_once(bridge, search_gate, brain_get, "Bridge brain GET endpoints")

# POST /brain/context performs sync + retrieval in one LAN round trip.
post_method = r'''
    def do_POST(self) -> None:
        assert STATE is not None
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if not self._authorized(params):
            self._json(401, {"error": "invalid bridge token"})
            return

        if parsed.path not in ("/brain/context", "/brain/sync"):
            self._json(404, {"error": "not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 2_500_000:
                self._json(413, {"error": "brain payload too large"})
                return
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            memories = payload.get("memories") or []
            turns = payload.get("turns") or []
            if not isinstance(memories, list) or not isinstance(turns, list):
                raise ValueError("invalid memories/turns")
            STATE.brain.sync(memories, turns)
            stats = STATE.brain.stats()
            if parsed.path == "/brain/sync":
                self._json(200, {"ok": True, "stats": stats})
                return
            query = str(payload.get("query") or "").strip()
            self._json(200, {
                "context": STATE.brain.context(query),
                "stats": stats,
            })
        except Exception as exc:
            self._json(400, {"error": f"invalid brain payload: {exc}"})

'''
start_marker = "\n\ndef start_background_reindex(state: BridgeState) -> None:\n"
if start_marker not in bridge:
    raise SystemExit("vex_bridge.py: background reindex marker missing")
bridge = bridge.replace(start_marker, "\n" + post_method + start_marker, 1)

bridge = bridge.replace('"version": "0.7.9"', '"version": "0.8.0"')
bridge = bridge.replace('server_version = "VexBridge/0.7.9"', 'server_version = "VexBridge/0.8.0"')
bridge = bridge.replace("VexBridge/0.7.9", "VexBridge/0.8.0")
bridge_path.write_text(bridge, encoding="utf-8")

full_path = Path("Bridge/vex_bridge_full.py")
full = full_path.read_text(encoding="utf-8")
full = full.replace('VERSION = "0.7.9"', 'VERSION = "0.8.0"')
full_path.write_text(full, encoding="utf-8")


for path, markers in [
    (app_path, ["PCBrainExpansion", "pcBrainConnected", "pcBrainContext: pcBrainContext"]),
    (prompt_path, ["PC EXPANSION BRAIN", "pcBrainContext: String? = nil"]),
    (content_path, ["🧠 PC"]),
    (bridge_path, ["class BrainVault", "/brain/context", "brain_vault.sqlite3", "relevance search failed"]),
    (full_path, ['VERSION = "0.8.0"']),
]:
    data = path.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in data:
            raise SystemExit(f"{path}: missing v0.8.0 marker: {marker}")

print("Applied v0.8.0 hybrid phone + PC expansion brain patch")
