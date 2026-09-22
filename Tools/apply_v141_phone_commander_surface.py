#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "VexNative" / "ContentView.swift"

text = CONTENT.read_text(encoding="utf-8")
if "V141_PHONE_COMMANDER_SURFACE" in text:
    print("PASS v0.14.1 phone commander surface already applied")
    raise SystemExit(0)

text = text.replace(
    'private let V132_PHONE_COMMAND_RELAY = "v0.13.2-phone-command-relay-v1"',
    'private let V132_PHONE_COMMAND_RELAY = "v0.13.2-phone-command-relay-v1"\nprivate let V141_PHONE_COMMANDER_SURFACE = "v0.14.1-phone-commander-surface-v1"',
    1
)

anchor = '''        if lower.contains("clipboard") && (lower.contains("copy ") || lower.contains("put ")) {
            if let payload = clipboardPayload(original) {
                UIPasteboard.general.string = payload
                appendExchange(user: original, assistant: "Done — I put that on the iPhone clipboard, baby. 📋🖤", app: app)
            } else {
                appendExchange(user: original, assistant: "Tell me what you want copied to the iPhone clipboard, baby. 🖤", app: app)
            }
            return true
        }

        if wantsOpen(lower), let url = knownURL(lower: lower, original: original) {'''
insert = '''        if lower.contains("clipboard") && (lower.contains("copy ") || lower.contains("put ")) {
            if let payload = clipboardPayload(original) {
                UIPasteboard.general.string = payload
                appendExchange(user: original, assistant: "Done — I put that on the iPhone clipboard, baby. 📋🖤", app: app)
            } else {
                appendExchange(user: original, assistant: "Tell me what you want copied to the iPhone clipboard, baby. 🖤", app: app)
            }
            return true
        }

        if lower.contains("read clipboard") || lower.contains("what's on the clipboard") || lower.contains("whats on the clipboard") {
            let value = UIPasteboard.general.string ?? ""
            appendExchange(
                user: original,
                assistant: value.isEmpty ? "The iPhone clipboard is empty." : String(value.prefix(3500)),
                app: app
            )
            return true
        }

        if let query = browserSearchQuery(original: original, lower: lower) {
            var parts = URLComponents(string: "https://www.google.com/search")!
            parts.queryItems = [URLQueryItem(name: "q", value: query)]
            let ok = parts.url.map { await openURL($0) } ?? false
            appendExchange(user: original, assistant: ok ? "Done — I opened that search on the iPhone." : "The iPhone did not open that browser search.", app: app)
            return true
        }

        if wantsFetchPage(lower), let url = firstPublicURL(in: original) {
            let result = await fetchPageText(url)
            appendExchange(user: original, assistant: result, app: app)
            return true
        }

        if wantsDownload(lower), let url = firstPublicURL(in: original) {
            let result = await downloadToDocuments(url)
            appendExchange(user: original, assistant: result, app: app)
            return true
        }

        if lower.contains("list files") || lower.contains("list vex documents") || lower.contains("show files in vex documents") {
            appendExchange(user: original, assistant: listDocuments(), app: app)
            return true
        }

        if lower.contains("read file "), let name = requestedFileName(original) {
            appendExchange(user: original, assistant: readDocument(named: name), app: app)
            return true
        }

        if wantsOpen(lower), let url = knownURL(lower: lower, original: original) {'''
if anchor not in text:
    raise SystemExit("v0.14.1 command insertion anchor missing")
text = text.replace(anchor, insert, 1)

helper_anchor = '''    private static func openURL(_ url: URL) async -> Bool {
        await withCheckedContinuation { continuation in
            UIApplication.shared.open(url, options: [:]) { opened in
                continuation.resume(returning: opened)
            }
        }
    }

    private static func firstNumber(in text: String) -> Double? {'''
helpers = '''    private static func openURL(_ url: URL) async -> Bool {
        await withCheckedContinuation { continuation in
            UIApplication.shared.open(url, options: [:]) { opened in
                continuation.resume(returning: opened)
            }
        }
    }

    private static func firstPublicURL(in text: String) -> URL? {
        for word in text.split(whereSeparator: { $0.isWhitespace }) {
            let raw = String(word).trimmingCharacters(in: CharacterSet(charactersIn: ",.;!?)\"]}"))
            guard let url = URL(string: raw),
                  let scheme = url.scheme?.lowercased(),
                  ["http", "https"].contains(scheme)
            else { continue }
            return url
        }
        return nil
    }

    private static func browserSearchQuery(original: String, lower: String) -> String? {
        let markers = ["search the web for ", "search google for ", "search safari for ", "search browser for "]
        for marker in markers {
            if let range = lower.range(of: marker) {
                let value = String(original[range.upperBound...])
                    .replacingOccurrences(of: " on my phone", with: "", options: .caseInsensitive)
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                if !value.isEmpty { return value }
            }
        }
        return nil
    }

    private static func wantsFetchPage(_ lower: String) -> Bool {
        ["fetch page", "fetch webpage", "read webpage", "read page", "grab page", "get page text"]
            .contains(where: { lower.contains($0) })
    }

    private static func wantsDownload(_ lower: String) -> Bool {
        lower.contains("download ") || lower.contains("save url ") || lower.contains("save file from ")
    }

    private static func fetchPageText(_ url: URL) async -> String {
        do {
            var request = URLRequest(url: url)
            request.timeoutInterval = 18
            request.setValue("VexNative/0.14.1", forHTTPHeaderField: "User-Agent")
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
                return "The page request failed."
            }
            guard data.count <= 2_000_000 else { return "That page is too large to pull through the phone relay." }
            let html = String(data: data, encoding: .utf8) ?? ""
            let stripped = html
                .replacingOccurrences(of: "<[^>]+>", with: " ", options: .regularExpression)
                .replacingOccurrences(of: "&nbsp;", with: " ")
                .replacingOccurrences(of: "&amp;", with: "&")
                .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
                .trimmingCharacters(in: .whitespacesAndNewlines)
            return stripped.isEmpty ? "The page loaded but contained no readable text." : String(stripped.prefix(3500))
        } catch {
            return "Page fetch failed: \(error.localizedDescription)"
        }
    }

    private static func downloadToDocuments(_ url: URL) async -> String {
        do {
            var request = URLRequest(url: url)
            request.timeoutInterval = 30
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
                return "The download request failed."
            }
            guard data.count <= 20_000_000 else { return "That file is too large for this phone-agent download path." }
            let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
            let folder = docs.appendingPathComponent("PhoneDownloads", isDirectory: true)
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            let fallback = "download-\(Int(Date().timeIntervalSince1970))"
            let name = url.lastPathComponent.isEmpty ? fallback : url.lastPathComponent
            let target = folder.appendingPathComponent(name)
            try data.write(to: target, options: .atomic)
            return "Saved to Vex Documents/PhoneDownloads/\(name) (\(data.count) bytes)."
        } catch {
            return "Download failed: \(error.localizedDescription)"
        }
    }

    private static func listDocuments() -> String {
        do {
            let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
            let items = try FileManager.default.contentsOfDirectory(
                at: docs,
                includingPropertiesForKeys: [.isDirectoryKey, .fileSizeKey],
                options: [.skipsHiddenFiles]
            )
            if items.isEmpty { return "Vex Documents is empty." }
            let names = items.prefix(80).map { $0.lastPathComponent }
            return names.joined(separator: "\n")
        } catch {
            return "Could not list Vex Documents: \(error.localizedDescription)"
        }
    }

    private static func requestedFileName(_ original: String) -> String? {
        let lower = original.lowercased()
        guard let range = lower.range(of: "read file ") else { return nil }
        var value = String(original[range.upperBound...])
            .replacingOccurrences(of: " on my phone", with: "", options: .caseInsensitive)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        if value.hasPrefix("\"") && value.hasSuffix("\"") && value.count >= 2 {
            value.removeFirst()
            value.removeLast()
        }
        return value.isEmpty ? nil : value
    }

    private static func readDocument(named name: String) -> String {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        let candidate = docs.appendingPathComponent(name).standardizedFileURL
        guard candidate.path.hasPrefix(docs.standardizedFileURL.path + "/") else {
            return "That path is outside Vex Documents."
        }
        do {
            let data = try Data(contentsOf: candidate)
            guard data.count <= 1_000_000 else { return "That file is too large to return through the phone relay." }
            guard let text = String(data: data, encoding: .utf8) else { return "That file is not UTF-8 text." }
            return String(text.prefix(3500))
        } catch {
            return "Could not read that file: \(error.localizedDescription)"
        }
    }

    private static func firstNumber(in text: String) -> Double? {'''
if helper_anchor not in text:
    raise SystemExit("v0.14.1 helper anchor missing")
text = text.replace(helper_anchor, helpers, 1)

CONTENT.write_text(text, encoding="utf-8")

final = CONTENT.read_text(encoding="utf-8")
for marker in [
    'V141_PHONE_COMMANDER_SURFACE = "v0.14.1-phone-commander-surface-v1"',
    "browserSearchQuery",
    "fetchPageText",
    "downloadToDocuments",
    "listDocuments",
    "readDocument",
    "read clipboard",
]:
    if marker not in final:
        raise SystemExit(f"v0.14.1 marker missing: {marker}")

print("PASS v0.14.1 phone commander surface patch")
