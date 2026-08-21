#!/usr/bin/env python3
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"{label}: expected source block not found")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# Brain model: optional attachment filename stays backward-compatible with old
# saved chat JSON because it is optional.
# ---------------------------------------------------------------------------
models_path = Path("VexNative/Core/BrainModels.swift")
models = models_path.read_text(encoding="utf-8")
models = replace_once(
    models,
    '''struct ChatMessage: Identifiable, Codable, Equatable, Sendable {\n    var id: UUID = UUID()\n    var role: ChatRole\n    var content: String\n    var createdAt: Date = Date()\n}\n''',
    '''struct ChatMessage: Identifiable, Codable, Equatable, Sendable {\n    var id: UUID = UUID()\n    var role: ChatRole\n    var content: String\n    var imageFilename: String? = nil\n    var createdAt: Date = Date()\n}\n''',
    "ChatMessage photo attachment field",
)
models_path.write_text(models, encoding="utf-8")


# ---------------------------------------------------------------------------
# Private on-device attachment storage. Images never enter the Brain JSON or
# public repo; chat stores only a random local filename.
# ---------------------------------------------------------------------------
store_path = Path("VexNative/Storage/LocalStore.swift")
store = store_path.read_text(encoding="utf-8")
models_dir = '''    var modelsDirectory: URL {\n        let url = appSupport.appendingPathComponent("Models", isDirectory: true)\n        if !fileManager.fileExists(atPath: url.path) {\n            try? fileManager.createDirectory(at: url, withIntermediateDirectories: true)\n        }\n        return url\n    }\n\n'''
attachment_store = models_dir + '''    private var attachmentsDirectory: URL {\n        let url = appSupport.appendingPathComponent("Attachments", isDirectory: true)\n        if !fileManager.fileExists(atPath: url.path) {\n            try? fileManager.createDirectory(at: url, withIntermediateDirectories: true)\n        }\n        return url\n    }\n\n    func saveAttachment(_ data: Data) throws -> String {\n        let filename = UUID().uuidString + ".image"\n        let url = attachmentsDirectory.appendingPathComponent(filename)\n        try data.write(to: url, options: [.atomic, .completeFileProtection])\n        return filename\n    }\n\n    func attachmentData(named filename: String) -> Data? {\n        guard !filename.contains("/"), !filename.contains("\\\\") else { return nil }\n        return try? Data(contentsOf: attachmentsDirectory.appendingPathComponent(filename))\n    }\n\n'''
store = replace_once(store, models_dir, attachment_store, "private attachment storage")
store_path.write_text(store, encoding="utf-8")


# ---------------------------------------------------------------------------
# AppModel: allow photo-only sends, persist the selected image locally, and add
# on-device Vision output only to the model prompt (not the visible user text).
# ---------------------------------------------------------------------------
app_path = Path("VexNative/AppModel.swift")
app = app_path.read_text(encoding="utf-8")
app = replace_once(
    app,
    '''    @Published var exportURL: URL?\n\n    private let store = LocalStore.shared\n''',
    '''    @Published var exportURL: URL?\n    @Published var pendingPhotoData: Data?\n    @Published var pendingPhotoContext: String?\n\n    private let store = LocalStore.shared\n''',
    "pending photo state",
)

old_send_start = '''    func send() async {\n        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)\n        guard !text.isEmpty, !isGenerating else { return }\n\n        draft = ""\n        lastError = nil\n\n        profile.messages.append(ChatMessage(role: .user, content: text))\n        if let learned = MemoryEngine.learnCandidate(from: text) {\n'''
new_send_start = '''    func send() async {\n        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)\n        let photoData = pendingPhotoData\n        let photoContext = pendingPhotoContext?.trimmingCharacters(in: .whitespacesAndNewlines)\n        guard (!text.isEmpty || photoData != nil), !isGenerating else { return }\n\n        draft = ""\n        pendingPhotoData = nil\n        pendingPhotoContext = nil\n        lastError = nil\n\n        let attachmentFilename = photoData.flatMap { try? store.saveAttachment($0) }\n        profile.messages.append(ChatMessage(\n            role: .user,\n            content: text,\n            imageFilename: attachmentFilename\n        ))\n\n        let modelText: String\n        if let photoContext, !photoContext.isEmpty {\n            let visibleQuestion = text.isEmpty ? "What do you see in this photo?" : text\n            modelText = """\n            \\(visibleQuestion)\n\n            ATTACHED PHOTO ANALYSIS (generated locally by Apple Vision; this is not direct pixel vision):\n            \\(photoContext)\n            Use the photo analysis only as evidence. If it is not specific enough, say what closer photo, label, or model number would clarify it. Never invent unseen visual details.\n            """\n        } else {\n            modelText = text\n        }\n\n        if let learned = MemoryEngine.learnCandidate(from: text) {\n'''
app = replace_once(app, old_send_start, new_send_start, "photo-aware send start")

# The normal prompt and its retry need the hidden photo context; role/fact fast paths
# still deliberately use visible text only.
app = replace_once(
    app,
    '''            newestUserText: text,\n            isQwen3: isQwen3\n''',
    '''            newestUserText: modelText,\n            isQwen3: isQwen3\n''',
    "photo context main prompt",
)
app = replace_once(
    app,
    '''                    newestUserText: text,\n                    isQwen3: true,\n                    retryMode: true\n''',
    '''                    newestUserText: modelText,\n                    isQwen3: true,\n                    retryMode: true\n''',
    "photo context retry prompt",
)
app_path.write_text(app, encoding="utf-8")


# ---------------------------------------------------------------------------
# Chat bubble: show persisted local image attachments above the user text.
# ---------------------------------------------------------------------------
chat_path = Path("VexNative/Views/ChatBubble.swift")
chat = chat_path.read_text(encoding="utf-8")
if "import UIKit" not in chat:
    chat = chat.replace("import SwiftUI\n", "import SwiftUI\nimport UIKit\n", 1)

old_render = '''                Text(renderedContent)\n                    .font(.body)\n                    .textSelection(.enabled)\n                    .foregroundStyle(.white)\n                    .tint(VexTheme.hotPink)\n'''
new_render = '''                if let attachedImage {\n                    Image(uiImage: attachedImage)\n                        .resizable()\n                        .scaledToFit()\n                        .frame(maxHeight: 260)\n                        .clipShape(RoundedRectangle(cornerRadius: 12))\n                }\n\n                if !message.content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {\n                    Text(renderedContent)\n                        .font(.body)\n                        .textSelection(.enabled)\n                        .foregroundStyle(.white)\n                        .tint(VexTheme.hotPink)\n                }\n'''
chat = replace_once(chat, old_render, new_render, "chat photo rendering")

helper_marker = '''    private var renderedContent: AttributedString {\n'''
photo_helper = '''    private var attachedImage: UIImage? {\n        guard let filename = message.imageFilename,\n              let data = LocalStore.shared.attachmentData(named: filename)\n        else { return nil }\n        return UIImage(data: data)\n    }\n\n'''
if helper_marker not in chat:
    raise SystemExit("ChatBubble.swift: renderedContent marker missing")
chat = chat.replace(helper_marker, photo_helper + helper_marker, 1)
chat_path.write_text(chat, encoding="utf-8")


# ---------------------------------------------------------------------------
# ContentView: native Photos picker + local Apple Vision OCR/classification.
# The current Qwen GGUF is text-only, so the image is translated into grounded
# text context on-device rather than pretending Qwen can see pixels.
# ---------------------------------------------------------------------------
content_path = Path("VexNative/ContentView.swift")
text = content_path.read_text(encoding="utf-8")
text = text.replace(
    "import Foundation\nimport SwiftUI\n",
    "import Foundation\nimport SwiftUI\nimport PhotosUI\nimport Vision\nimport UIKit\n",
    1,
)
text = replace_once(
    text,
    '''    @StateObject private var web = WebBrain.shared\n\n    var body: some View {\n''',
    '''    @StateObject private var web = WebBrain.shared\n    @State private var selectedPhotoItem: PhotosPickerItem?\n    @State private var selectedPhotoData: Data?\n    @State private var isAnalyzingPhoto = false\n\n    var body: some View {\n''',
    "photo picker state",
)

start = text.find("    private var composer: some View {")
end = text.find("\n}\n\n// MARK: - Web Brain", start)
if start < 0 or end < 0:
    raise SystemExit("ContentView.swift: composer block markers missing")

new_composer = r'''    private var composer: some View {
        VStack(spacing: 7) {
            if let selectedPhotoData, let image = UIImage(data: selectedPhotoData) {
                HStack(spacing: 10) {
                    Image(uiImage: image)
                        .resizable()
                        .scaledToFill()
                        .frame(width: 58, height: 58)
                        .clipShape(RoundedRectangle(cornerRadius: 10))
                        .clipped()

                    VStack(alignment: .leading, spacing: 2) {
                        Text(isAnalyzingPhoto ? "Looking at photo…" : "Photo attached")
                            .font(.caption.weight(.bold))
                        Text(isAnalyzingPhoto ? "reading text + visual clues locally" : "Vex gets local photo context with your message")
                            .font(.caption2)
                            .foregroundStyle(VexTheme.muted)
                    }

                    Spacer()
                    Button {
                        clearPendingPhoto()
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .font(.title3)
                            .foregroundStyle(VexTheme.muted)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 4)
            }

            HStack(alignment: .center, spacing: 8) {
                PhotosPicker(selection: $selectedPhotoItem, matching: .images) {
                    Image(systemName: "photo")
                        .font(.headline)
                        .foregroundStyle(VexTheme.hotPink)
                        .frame(width: 40, height: 44)
                        .background(VexTheme.panel)
                        .clipShape(RoundedRectangle(cornerRadius: 13))
                }
                .buttonStyle(.plain)
                .disabled(app.isGenerating || web.isWorking || isAnalyzingPhoto)
                .onChange(of: selectedPhotoItem) { _, item in
                    Task { await loadPhoto(item) }
                }

                TextField("Say something to Vex…", text: $app.draft)
                    .padding(11)
                    .background(VexTheme.panel)
                    .clipShape(RoundedRectangle(cornerRadius: 16))
                    .overlay {
                        RoundedRectangle(cornerRadius: 16)
                            .stroke(.white.opacity(0.08))
                    }
                    .submitLabel(.send)
                    .disabled(web.isWorking || isAnalyzingPhoto)
                    .onSubmit { sendCurrentMessage() }

                Button {
                    sendCurrentMessage()
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
                    app.isGenerating || web.isWorking || isAnalyzingPhoto ||
                    (app.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && app.pendingPhotoData == nil)
                )
                .opacity((app.isGenerating || web.isWorking || isAnalyzingPhoto) ? 0.5 : 1)
            }
        }
        .padding(.horizontal, 12)
        .padding(.top, 8)
        .padding(.bottom, 9)
        .background(.ultraThinMaterial)
    }

    private func sendCurrentMessage() {
        guard !app.isGenerating, !web.isWorking, !isAnalyzingPhoto else { return }
        guard !app.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || app.pendingPhotoData != nil else { return }
        Task {
            await app.sendWithWeb()
            await MainActor.run {
                selectedPhotoData = nil
                selectedPhotoItem = nil
            }
        }
    }

    private func clearPendingPhoto() {
        selectedPhotoData = nil
        selectedPhotoItem = nil
        app.pendingPhotoData = nil
        app.pendingPhotoContext = nil
        isAnalyzingPhoto = false
    }

    private func loadPhoto(_ item: PhotosPickerItem?) async {
        guard let item else { return }
        isAnalyzingPhoto = true
        defer { isAnalyzingPhoto = false }

        do {
            guard let data = try await item.loadTransferable(type: Data.self) else {
                clearPendingPhoto()
                return
            }
            let context = await PhotoContextAnalyzer.analyze(data)
            selectedPhotoData = data
            app.pendingPhotoData = data
            app.pendingPhotoContext = context
        } catch {
            clearPendingPhoto()
            app.lastError = "I couldn't read that photo 😭🖤 \(error.localizedDescription)"
        }
    }
'''
text = text[:start] + new_composer + text[end:]

photo_analyzer = r'''

private enum PhotoContextAnalyzer {
    static func analyze(_ data: Data) async -> String {
        await Task.detached(priority: .userInitiated) {
            let textRequest = VNRecognizeTextRequest()
            textRequest.recognitionLevel = .accurate
            textRequest.usesLanguageCorrection = true

            let classifyRequest = VNClassifyImageRequest()
            let handler = VNImageRequestHandler(data: data, options: [:])
            try? handler.perform([textRequest, classifyRequest])

            let recognizedText = (textRequest.results ?? [])
                .compactMap { $0.topCandidates(1).first?.string }
                .joined(separator: " | ")

            var seen = Set<String>()
            let labels = (classifyRequest.results ?? [])
                .filter { $0.confidence >= 0.08 }
                .compactMap { observation -> String? in
                    let label = observation.identifier.trimmingCharacters(in: .whitespacesAndNewlines)
                    let key = label.lowercased()
                    guard !label.isEmpty, seen.insert(key).inserted else { return nil }
                    return label
                }
                .prefix(6)
                .map { $0 }

            var parts: [String] = []
            if !recognizedText.isEmpty {
                parts.append("PHOTO TEXT: \(String(recognizedText.prefix(1400)))")
            }
            if !labels.isEmpty {
                parts.append("PHOTO LABELS: \(labels.joined(separator: ", "))")
            }
            if parts.isEmpty {
                return "A photo is attached, but local Vision did not extract reliable text or classification labels."
            }
            return parts.joined(separator: " | ")
        }.value
    }
}
'''
web_marker = "\n// MARK: - Web Brain v0.6\n"
if web_marker not in text:
    raise SystemExit("ContentView.swift: Web Brain marker missing")
text = text.replace(web_marker, photo_analyzer + web_marker, 1)

# Allow a photo-only turn to reach AppModel.send(). For researched photo turns,
# append local OCR/classification to the resolved visible query.
text = replace_once(
    text,
    '''        let original = draft.trimmingCharacters(in: .whitespacesAndNewlines)\n        guard !original.isEmpty, !isGenerating else { return }\n\n        let web = WebBrain.shared\n''',
    '''        let original = draft.trimmingCharacters(in: .whitespacesAndNewlines)\n        guard (!original.isEmpty || pendingPhotoData != nil), !isGenerating else { return }\n\n        let web = WebBrain.shared\n''',
    "photo-only sendWithWeb guard",
)

old_research_resolution = '''        let researchInput = web.resolvedResearchInput(current: original, previousUser: previousUser)\n        guard web.shouldUseWeb(for: researchInput) else {\n            await send()\n            return\n        }\n'''
new_research_resolution = '''        let resolvedVisibleInput = web.resolvedResearchInput(current: original, previousUser: previousUser)\n        guard web.shouldUseWeb(for: resolvedVisibleInput) else {\n            await send()\n            return\n        }\n        let photoSearchContext = pendingPhotoContext?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""\n        let researchInput = photoSearchContext.isEmpty\n            ? resolvedVisibleInput\n            : resolvedVisibleInput + " " + photoSearchContext\n'''
text = replace_once(text, old_research_resolution, new_research_resolution, "photo-aware research query")

# Expose the procedural classifier to the same-file AppModel extension.
text = text.replace("    private func isProceduralResearchRequest(_ text: String) -> Bool {", "    func isProceduralResearchRequest(_ text: String) -> Bool {", 1)

# Deterministic extractive guard: do not let a 0.6B model replace actual repair
# evidence with invented switches, motors, phones, or future actions.
bundle_marker = '''    func memoriesForDeliberateLearning() -> [BrainMemory] {\n'''
grounded_method = r'''    func groundedProceduralAnswer(userQuestion: String) -> String? {
        let stopwords: Set<String> = [
            "the", "and", "for", "with", "that", "this", "from", "your", "you", "how",
            "can", "help", "find", "out", "what", "about", "into", "then", "than", "are",
            "was", "were", "have", "has", "had", "its", "use", "using", "change", "photo",
            "text", "labels", "attached", "analysis"
        ]
        let terms = Set(userQuestion.lowercased()
            .split(whereSeparator: { !$0.isLetter && !$0.isNumber })
            .map(String.init)
            .filter { $0.count >= 3 && !stopwords.contains($0) })

        let actionWords = [
            "remove", "removed", "removing", "replace", "replacement", "replacing",
            "disconnect", "unplug", "unscrew", "screw", "panel", "access", "locate", "located",
            "fuse", "thermostat", "wire", "connector", "test", "continuity", "multimeter",
            "install", "housing", "vent", "blower", "rear", "front", "step"
        ]

        var candidates: [(score: Int, text: String)] = []
        var seen = Set<String>()

        for source in sources.prefix(3) {
            let normalized = source.snippet
                .replacingOccurrences(of: "\n", with: " ")
                .replacingOccurrences(of: "  ", with: " ")
            let sentences = normalized.components(separatedBy: CharacterSet(charactersIn: ".!?"))

            for raw in sentences {
                let sentence = raw.trimmingCharacters(in: .whitespacesAndNewlines)
                guard sentence.count >= 38, sentence.count <= 360 else { continue }
                let lower = sentence.lowercased()
                let overlap = terms.reduce(0) { $0 + (lower.contains($1) ? 1 : 0) }
                let actionHits = actionWords.reduce(0) { $0 + (lower.contains($1) ? 1 : 0) }
                guard overlap >= 1, actionHits >= 1 else { continue }
                let key = lower.filter { $0.isLetter || $0.isNumber || $0 == " " }
                guard seen.insert(key).inserted else { continue }
                candidates.append((overlap * 4 + actionHits, sentence))
            }
        }

        let chosen = candidates
            .sorted { lhs, rhs in
                if lhs.score != rhs.score { return lhs.score > rhs.score }
                return lhs.text.count < rhs.text.count
            }
            .prefix(5)
            .map(\.text)

        guard !chosen.isEmpty else { return nil }
        let steps = chosen.enumerated().map { "\($0.offset + 1). \($0.element)" }.joined(separator: "\n")
        return """
        Baby, I found concrete repair details, so I'm sticking to what the sources actually say instead of guessing 😭🖤

        \(steps)

        GE changes the layout between models, so a photo of the model-number label or the opened panel can narrow this to your exact dryer.
        """
    }

'''
if bundle_marker not in text:
    raise SystemExit("ContentView.swift: memoriesForDeliberateLearning marker missing")
text = text.replace(bundle_marker, grounded_method + bundle_marker, 1)

old_after_send = '''        await send()\n\n        profile.memories.removeAll { $0.id == transient.id || $0.source == "web-temporary" }\n'''
new_after_send = '''        await send()\n\n        if web.isProceduralResearchRequest(researchInput),\n           let grounded = bundle.groundedProceduralAnswer(userQuestion: researchInput),\n           let index = profile.messages.lastIndex(where: { $0.role == .assistant }) {\n            profile.messages[index].content = grounded\n        }\n\n        profile.memories.removeAll { $0.id == transient.id || $0.source == "web-temporary" }\n'''
text = replace_once(text, old_after_send, new_after_send, "grounded procedural response override")
content_path.write_text(text, encoding="utf-8")


for path, markers in [
    (models_path, ["imageFilename: String?"]),
    (store_path, ["saveAttachment", "attachmentData(named"]),
    (app_path, ["pendingPhotoData", "ATTACHED PHOTO ANALYSIS", "newestUserText: modelText"]),
    (chat_path, ["attachedImage", "UIImage(data: data)"]),
    (content_path, ["PhotosPicker", "PhotoContextAnalyzer", "groundedProceduralAnswer", "photoSearchContext"]),
]:
    data = path.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in data:
            raise SystemExit(f"{path}: missing v0.7.8 marker: {marker}")

print("Applied v0.7.8 photo-context + grounded procedural-answer patch")
