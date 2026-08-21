#!/usr/bin/env python3
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"{label}: expected source block not found")
    return text.replace(old, new, 1)


content_path = Path("VexNative/ContentView.swift")
text = content_path.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# Camera + attachment menu.
# ---------------------------------------------------------------------------
text = replace_once(
    text,
    '''    @State private var selectedPhotoItem: PhotosPickerItem?\n    @State private var selectedPhotoData: Data?\n    @State private var isAnalyzingPhoto = false\n''',
    '''    @State private var selectedPhotoItem: PhotosPickerItem?\n    @State private var selectedPhotoData: Data?\n    @State private var isAnalyzingPhoto = false\n    @State private var isShowingCamera = false\n''',
    "camera state",
)

old_picker = '''                PhotosPicker(selection: $selectedPhotoItem, matching: .images) {\n                    Image(systemName: "photo")\n                        .font(.headline)\n                        .foregroundStyle(VexTheme.hotPink)\n                        .frame(width: 40, height: 44)\n                        .background(VexTheme.panel)\n                        .clipShape(RoundedRectangle(cornerRadius: 13))\n                }\n                .buttonStyle(.plain)\n                .disabled(app.isGenerating || web.isWorking || isAnalyzingPhoto)\n                .onChange(of: selectedPhotoItem) { _, item in\n                    Task { await loadPhoto(item) }\n                }\n'''
new_picker = '''                Menu {\n                    Button {\n                        guard UIImagePickerController.isSourceTypeAvailable(.camera) else {\n                            app.lastError = "This device doesn't have an available camera."\n                            return\n                        }\n                        isShowingCamera = true\n                    } label: {\n                        Label("Take Photo", systemImage: "camera")\n                    }\n\n                    PhotosPicker(selection: $selectedPhotoItem, matching: .images) {\n                        Label("Choose from Library", systemImage: "photo.on.rectangle")\n                    }\n                } label: {\n                    Image(systemName: "photo")\n                        .font(.headline)\n                        .foregroundStyle(VexTheme.hotPink)\n                        .frame(width: 40, height: 44)\n                        .background(VexTheme.panel)\n                        .clipShape(RoundedRectangle(cornerRadius: 13))\n                }\n                .buttonStyle(.plain)\n                .disabled(app.isGenerating || web.isWorking || isAnalyzingPhoto)\n                .onChange(of: selectedPhotoItem) { _, item in\n                    Task { await loadPhoto(item) }\n                }\n                .sheet(isPresented: $isShowingCamera) {\n                    CameraCaptureView { data in\n                        Task { await loadPhotoData(data) }\n                    }\n                    .ignoresSafeArea()\n                }\n'''
text = replace_once(text, old_picker, new_picker, "camera/library attachment menu")

old_load = '''    private func loadPhoto(_ item: PhotosPickerItem?) async {\n        guard let item else { return }\n        isAnalyzingPhoto = true\n        defer { isAnalyzingPhoto = false }\n\n        do {\n            guard let data = try await item.loadTransferable(type: Data.self) else {\n                clearPendingPhoto()\n                return\n            }\n            let context = await PhotoContextAnalyzer.analyze(data)\n            selectedPhotoData = data\n            app.pendingPhotoData = data\n            app.pendingPhotoContext = context\n        } catch {\n            clearPendingPhoto()\n            app.lastError = "I couldn't read that photo 😭🖤 \\(error.localizedDescription)"\n        }\n    }\n'''
new_load = '''    private func loadPhoto(_ item: PhotosPickerItem?) async {\n        guard let item else { return }\n        do {\n            guard let data = try await item.loadTransferable(type: Data.self) else {\n                clearPendingPhoto()\n                return\n            }\n            await loadPhotoData(data)\n        } catch {\n            clearPendingPhoto()\n            app.lastError = "I couldn't read that photo 😭🖤 \\(error.localizedDescription)"\n        }\n    }\n\n    private func loadPhotoData(_ data: Data) async {\n        isAnalyzingPhoto = true\n        defer { isAnalyzingPhoto = false }\n        let context = await PhotoContextAnalyzer.analyze(data)\n        selectedPhotoData = data\n        app.pendingPhotoData = data\n        app.pendingPhotoContext = context\n    }\n'''
text = replace_once(text, old_load, new_load, "shared camera/library analyzer")

photo_marker = '''private enum PhotoContextAnalyzer {\n'''
camera_wrapper = r'''private struct CameraCaptureView: UIViewControllerRepresentable {
    let onCapture: (Data) -> Void
    @Environment(\.dismiss) private var dismiss

    func makeCoordinator() -> Coordinator {
        Coordinator(parent: self)
    }

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.cameraCaptureMode = .photo
        picker.allowsEditing = false
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}

    final class Coordinator: NSObject, UINavigationControllerDelegate, UIImagePickerControllerDelegate {
        let parent: CameraCaptureView

        init(parent: CameraCaptureView) {
            self.parent = parent
        }

        func imagePickerController(
            _ picker: UIImagePickerController,
            didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]
        ) {
            defer { parent.dismiss() }
            guard let image = info[.originalImage] as? UIImage,
                  let data = image.jpegData(compressionQuality: 0.90)
            else { return }
            parent.onCapture(data)
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            parent.dismiss()
        }
    }
}

'''
if photo_marker not in text:
    raise SystemExit("ContentView.swift: PhotoContextAnalyzer marker missing")
text = text.replace(photo_marker, camera_wrapper + photo_marker, 1)


# ---------------------------------------------------------------------------
# Visual reply data types and local explainer-card generation.
# ---------------------------------------------------------------------------
websource_marker = '''struct WebSource: Equatable, Sendable {\n'''
visual_types = r'''struct WebVisualResult: Sendable {
    let title: String
    let imageURL: URL
    let sourceURL: URL?
}

private enum VisualReplyRenderer {
    static func makeExplainerCard(title: String, body: String) -> Data? {
        let size = CGSize(width: 900, height: 1100)
        let renderer = UIGraphicsImageRenderer(size: size)
        let image = renderer.image { context in
            let rect = CGRect(origin: .zero, size: size)
            UIColor(red: 0.08, green: 0.03, blue: 0.09, alpha: 1).setFill()
            context.fill(rect)

            let titleStyle = NSMutableParagraphStyle()
            titleStyle.alignment = .left
            let titleAttrs: [NSAttributedString.Key: Any] = [
                .font: UIFont.systemFont(ofSize: 46, weight: .bold),
                .foregroundColor: UIColor(red: 1.0, green: 0.26, blue: 0.72, alpha: 1),
                .paragraphStyle: titleStyle,
            ]
            let bodyAttrs: [NSAttributedString.Key: Any] = [
                .font: UIFont.systemFont(ofSize: 30, weight: .regular),
                .foregroundColor: UIColor.white,
            ]

            NSString(string: title).draw(
                with: CGRect(x: 54, y: 54, width: 792, height: 160),
                options: [.usesLineFragmentOrigin, .usesFontLeading],
                attributes: titleAttrs,
                context: nil
            )

            let trimmed = String(body.prefix(3000))
            NSString(string: trimmed).draw(
                with: CGRect(x: 54, y: 220, width: 792, height: 810),
                options: [.usesLineFragmentOrigin, .usesFontLeading],
                attributes: bodyAttrs,
                context: nil
            )
        }
        return image.jpegData(compressionQuality: 0.90)
    }
}

'''
if websource_marker not in text:
    raise SystemExit("ContentView.swift: WebSource marker missing")
text = text.replace(websource_marker, visual_types + websource_marker, 1)


# ---------------------------------------------------------------------------
# WebBrain visual intent + Bridge image lookup/proxy.
# ---------------------------------------------------------------------------
should_marker = '''    func shouldUseWeb(for text: String) -> Bool {\n        guard isEnabled else { return false }\n        let lower = normalize(text)\n'''
should_new = '''    func shouldUseWeb(for text: String) -> Bool {\n        guard isEnabled else { return false }\n        let lower = normalize(text)\n        if wantsVisualReply(text) { return true }\n'''
text = replace_once(text, should_marker, should_new, "visual web routing")

needs_marker = '''    private func needsGeneralSearch(_ text: String) -> Bool {\n'''
visual_helpers = r'''    func wantsVisualReply(_ text: String) -> Bool {
        let lower = normalize(text)
        let triggers = [
            "show me a picture", "show me a photo", "show me an image", "show me a diagram",
            "send me a picture", "send me a photo", "send me an image", "send me a diagram",
            "find me a picture", "find me a photo", "find me an image", "find me a diagram",
            "what does it look like", "what does that look like", "what does this look like",
            "can you show me", "could you show me", "show me where", "visual example",
            "make me a picture", "make a picture", "make me an image", "make an image",
            "draw me a picture", "draw a picture", "generate a picture", "generate an image"
        ]
        return triggers.contains(where: { lower.contains($0) })
    }

    func wantsGeneratedVisual(_ text: String) -> Bool {
        let lower = normalize(text)
        return [
            "make me a picture", "make a picture", "make me an image", "make an image",
            "draw me a picture", "draw a picture", "generate a picture", "generate an image",
            "make me a diagram", "draw me a diagram", "generate a diagram"
        ].contains(where: { lower.contains($0) })
    }

    func resolvedVisualQuery(current: String, previousUser: String?) -> String {
        var query = normalize(current)
        let generic = query.split(whereSeparator: { $0.isWhitespace }).count <= 12
        if generic, let previousUser, !previousUser.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            let visualOnly = [
                "show me a picture", "show me a photo", "show me an image", "show me a diagram",
                "can you show me", "could you show me", "show me where", "what does it look like",
                "what does that look like", "make me a picture", "draw me a picture"
            ].contains(where: { query.contains($0) })
            if visualOnly {
                query += " " + normalize(previousUser)
            }
        }

        let removable = [
            "show me a picture of", "show me a photo of", "show me an image of", "show me a diagram of",
            "show me a picture", "show me a photo", "show me an image", "show me a diagram",
            "send me a picture", "send me a photo", "send me an image", "send me a diagram",
            "find me a picture", "find me a photo", "find me an image", "find me a diagram",
            "can you show me", "could you show me", "make me a picture of", "make me a picture",
            "draw me a picture of", "draw me a picture", "generate an image of", "generate an image",
            "generate a picture of", "generate a picture", "what does it look like", "what does that look like"
        ]
        for phrase in removable {
            query = query.replacingOccurrences(of: phrase, with: " ")
        }
        query = query.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
        return query.isEmpty ? current : query
    }

    func fetchVisualImage(query: String) async throws -> (data: Data, result: WebVisualResult) {
        let endpoint = searxEndpoint.trimmingCharacters(in: .whitespacesAndNewlines)
        guard var base = URL(string: endpoint), VexBridgeNetworking.isBridgeURL(base) else {
            throw WebBrainError.noSearchProvider
        }

        base.appendPathComponent("image-search")
        guard var components = URLComponents(url: base, resolvingAgainstBaseURL: false) else {
            throw WebBrainError.invalidEndpoint
        }
        var items = components.queryItems ?? []
        items.append(URLQueryItem(name: "q", value: query))
        components.queryItems = items
        guard let searchURL = components.url else { throw WebBrainError.invalidEndpoint }

        var request = URLRequest(url: searchURL)
        request.timeoutInterval = 16
        let (payload, response) = try await VexBridgeNetworking.data(for: request)
        try validate(response)

        struct Envelope: Decodable {
            struct Item: Decodable {
                let title: String
                let image_url: String
                let source_url: String?
            }
            let results: [Item]
        }
        let decoded = try JSONDecoder().decode(Envelope.self, from: payload)
        guard let first = decoded.results.first,
              let imageURL = URL(string: first.image_url)
        else { throw WebBrainError.noResults }

        var proxy = URL(string: endpoint)!
        proxy.appendPathComponent("image-proxy")
        guard var proxyComponents = URLComponents(url: proxy, resolvingAgainstBaseURL: false) else {
            throw WebBrainError.invalidEndpoint
        }
        var proxyItems = proxyComponents.queryItems ?? []
        proxyItems.append(URLQueryItem(name: "url", value: imageURL.absoluteString))
        proxyComponents.queryItems = proxyItems
        guard let proxyURL = proxyComponents.url else { throw WebBrainError.invalidEndpoint }

        var imageRequest = URLRequest(url: proxyURL)
        imageRequest.timeoutInterval = 22
        let (imageData, imageResponse) = try await VexBridgeNetworking.data(for: imageRequest)
        try validate(imageResponse)
        guard imageData.count >= 200, imageData.count <= 8_000_000,
              UIImage(data: imageData) != nil
        else { throw WebBrainError.noResults }

        let result = WebVisualResult(
            title: cleanText(first.title),
            imageURL: imageURL,
            sourceURL: first.source_url.flatMap(URL.init(string:))
        )
        return (imageData, result)
    }

'''
if needs_marker not in text:
    raise SystemExit("ContentView.swift: needsGeneralSearch marker missing")
text = text.replace(needs_marker, visual_helpers + needs_marker, 1)


# ---------------------------------------------------------------------------
# Visual response integration: fetch a real web visual by default; explicit
# make/draw/generate requests create a private local explainer image from the
# grounded evidence, and web-image failure also falls back to that card.
# ---------------------------------------------------------------------------
old_resolution = '''        let resolvedVisibleInput = web.resolvedResearchInput(current: original, previousUser: previousUser)\n        guard web.shouldUseWeb(for: resolvedVisibleInput) else {\n            await send()\n            return\n        }\n        let photoSearchContext = pendingPhotoContext?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""\n'''
new_resolution = '''        let visualRequest = web.wantsVisualReply(original)\n        let visualQuery = visualRequest\n            ? web.resolvedVisualQuery(current: original, previousUser: previousUser)\n            : original\n        let resolvedVisibleInput = visualRequest\n            ? visualQuery\n            : web.resolvedResearchInput(current: original, previousUser: previousUser)\n        guard web.shouldUseWeb(for: resolvedVisibleInput) else {\n            await send()\n            return\n        }\n        let photoSearchContext = pendingPhotoContext?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""\n'''
text = replace_once(text, old_resolution, new_resolution, "visual request resolution")

old_after_grounding = '''        if web.isProceduralResearchRequest(researchInput),\n           let grounded = bundle.groundedProceduralAnswer(userQuestion: researchInput),\n           let index = profile.messages.lastIndex(where: { $0.role == .assistant }) {\n            profile.messages[index].content = grounded\n        }\n\n        profile.memories.removeAll { $0.id == transient.id || $0.source == "web-temporary" }\n'''
new_after_grounding = '''        if web.isProceduralResearchRequest(researchInput),\n           let grounded = bundle.groundedProceduralAnswer(userQuestion: researchInput),\n           let index = profile.messages.lastIndex(where: { $0.role == .assistant }) {\n            profile.messages[index].content = grounded\n        }\n\n        if visualRequest,\n           let index = profile.messages.lastIndex(where: { $0.role == .assistant }) {\n            let generated = web.wantsGeneratedVisual(original)\n            var visualData: Data?\n            var caption = ""\n\n            if generated {\n                let body = bundle.groundedProceduralAnswer(userQuestion: researchInput)\n                    ?? bundle.compactEvidence(maxCharacters: 2600)\n                visualData = VisualReplyRenderer.makeExplainerCard(\n                    title: "Vex visual: \\(visualQuery)",\n                    body: body\n                )\n                caption = "I made you a visual explainer from the grounded research, baby 🖤"\n            } else {\n                do {\n                    let visual = try await web.fetchVisualImage(query: visualQuery)\n                    visualData = visual.data\n                    if let source = visual.result.sourceURL {\n                        caption = "Here’s the clearest visual I found for \\(visualQuery). [Open original source](\\(source.absoluteString))"\n                    } else {\n                        caption = "Here’s the clearest visual I found for \\(visualQuery)."\n                    }\n                } catch {\n                    let body = bundle.groundedProceduralAnswer(userQuestion: researchInput)\n                        ?? bundle.compactEvidence(maxCharacters: 2600)\n                    visualData = VisualReplyRenderer.makeExplainerCard(\n                        title: "Vex visual: \\(visualQuery)",\n                        body: body\n                    )\n                    caption = "The web image fetch was being annoying, so I made you a local visual explainer instead 😭🖤"\n                }\n            }\n\n            if let visualData, let filename = try? LocalStore.shared.saveAttachment(visualData) {\n                profile.messages[index].imageFilename = filename\n                profile.messages[index].content = caption\n            }\n        }\n\n        profile.memories.removeAll { $0.id == transient.id || $0.source == "web-temporary" }\n'''
text = replace_once(text, old_after_grounding, new_after_grounding, "assistant visual reply integration")
content_path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Windows Bridge visual search + private image proxy.
# ---------------------------------------------------------------------------
bridge_path = Path("Bridge/vex_bridge.py")
bridge = bridge_path.read_text(encoding="utf-8")

state_marker = '''\n\nclass BridgeState:\n'''
visual_bridge = r'''

def _safe_public_https_url(raw: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(raw)
        if parsed.scheme.lower() != "https" or not parsed.hostname:
            return False
        host = parsed.hostname.lower()
        if host in {"localhost", "::1"} or host.endswith(".local"):
            return False
        try:
            import ipaddress
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
        except ValueError:
            pass
        return True
    except Exception:
        return False


def web_image_search(query: str, limit: int = 6) -> list[dict]:
    try:
        import requests
        from bs4 import BeautifulSoup

        response = requests.get(
            "https://www.bing.com/images/search",
            params={"q": query, "form": "HDRSC3"},
            headers={"User-Agent": "Mozilla/5.0 VexBridge/0.7.9"},
            timeout=12,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        seen = set()
        for node in soup.select("a.iusc"):
            raw = node.get("m") or ""
            try:
                meta = json.loads(raw)
            except Exception:
                continue
            image_url = (meta.get("murl") or "").strip()
            source_url = (meta.get("purl") or "").strip()
            title = (meta.get("t") or node.get("aria-label") or query).strip()
            if not _safe_public_https_url(image_url) or image_url in seen:
                continue
            seen.add(image_url)
            results.append({
                "title": title[:220],
                "image_url": image_url,
                "source_url": source_url if _safe_public_https_url(source_url) else None,
            })
            if len(results) >= limit:
                break
        print(f"[image-search] q={query[:120]} results={len(results)}", flush=True)
        return results
    except Exception as exc:
        print(f"[image-search] failed: {exc}", flush=True)
        return []


def proxy_image(raw_url: str) -> tuple[bytes, str] | None:
    if not _safe_public_https_url(raw_url):
        return None
    try:
        import requests
        response = requests.get(
            raw_url,
            headers={
                "User-Agent": "Mozilla/5.0 VexBridge/0.7.9",
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            },
            timeout=16,
            allow_redirects=True,
            stream=True,
        )
        response.raise_for_status()
        final_url = response.url
        if not _safe_public_https_url(final_url):
            return None
        content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
        if not content_type.startswith("image/"):
            return None
        chunks = []
        total = 0
        for chunk in response.iter_content(64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > 8_000_000:
                return None
            chunks.append(chunk)
        data = b"".join(chunks)
        if len(data) < 200:
            return None
        return data, content_type
    except Exception as exc:
        print(f"[image-proxy] failed: {exc}", flush=True)
        return None
'''
if state_marker not in bridge:
    raise SystemExit("vex_bridge.py: BridgeState marker missing")
bridge = bridge.replace(state_marker, visual_bridge + state_marker, 1)

old_path_gate = '''        if parsed.path != "/search":\n            self._json(404, {"error": "not found"})\n            return\n\n        query = (params.get("q") or [""])[0].strip()\n'''
new_path_gate = '''        if parsed.path == "/image-search":\n            query = (params.get("q") or [""])[0].strip()\n            if not query:\n                self._json(200, {"results": []})\n                return\n            results = web_image_search(query, limit=6)\n            self._json(200, {"query": query, "results": results})\n            return\n\n        if parsed.path == "/image-proxy":\n            raw_url = (params.get("url") or [""])[0].strip()\n            proxied = proxy_image(raw_url)\n            if proxied is None:\n                self._json(404, {"error": "image unavailable"})\n                return\n            body, content_type = proxied\n            self.send_response(200)\n            self.send_header("Content-Type", content_type)\n            self.send_header("Content-Length", str(len(body)))\n            self.send_header("Cache-Control", "private, max-age=300")\n            self.end_headers()\n            self.wfile.write(body)\n            return\n\n        if parsed.path != "/search":\n            self._json(404, {"error": "not found"})\n            return\n\n        query = (params.get("q") or [""])[0].strip()\n'''
bridge = replace_once(bridge, old_path_gate, new_path_gate, "bridge visual endpoints")
bridge = bridge.replace("0.7.7", "0.7.9")
bridge_path.write_text(bridge, encoding="utf-8")

full_path = Path("Bridge/vex_bridge_full.py")
full = full_path.read_text(encoding="utf-8")
full = full.replace('VERSION = "0.7.7"', 'VERSION = "0.7.9"', 1)
full_path.write_text(full, encoding="utf-8")


for path, markers in [
    (content_path, ["CameraCaptureView", "Take Photo", "fetchVisualImage", "VisualReplyRenderer", "wantsVisualReply"]),
    (bridge_path, ["web_image_search", 'parsed.path == "/image-search"', 'parsed.path == "/image-proxy"', "VexBridge/0.7.9"]),
    (full_path, ['VERSION = "0.7.9"']),
]:
    data = path.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in data:
            raise SystemExit(f"{path}: missing v0.7.9 marker: {marker}")

print("Applied v0.7.9 in-app camera + assistant visual reply patch")
