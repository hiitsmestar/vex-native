#!/usr/bin/env python3
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"{label}: expected source block not found")
    return text.replace(old, new, 1)


# iPhone router: recognize browser/site commands before Web Brain/file search.
content_path = Path("VexNative/ContentView.swift")
text = content_path.read_text(encoding="utf-8")

text = replace_once(
    text,
    '''        guard let action = requestedAction(lower) else { return false }\n        guard let target = requestedTarget(lower) else { return false }\n''',
    '''        guard let action = requestedAction(lower, original: original) else { return false }\n        guard let target = requestedTarget(lower) else { return false }\n        let requestedURL = requestedURL(lower: lower, original: original)\n''',
    "browser tool request routing",
)

text = replace_once(
    text,
    '''            if let result = await perform(action: action, endpoint: node.endpoint), result.ok {\n''',
    '''            if let result = await perform(action: action, url: requestedURL, endpoint: node.endpoint), result.ok {\n''',
    "browser tool perform call",
)

start = text.find('    private static func requestedAction(_ lower: String) -> String? {')
end = text.find('    private static func fetchStatus(_ endpoint: String) async -> NodeStatus? {', start)
if start < 0 or end < 0:
    raise SystemExit("ContentView.swift: requestedAction markers missing")

new_parser = r'''    private static func requestedAction(_ lower: String, original: String) -> String? {
        let asksOpen = lower.contains("open ") || lower.hasPrefix("open") ||
            lower.contains("show ") || lower.hasPrefix("show") || lower.contains("go to ") ||
            lower.contains("launch ") || lower.hasPrefix("launch")
        guard asksOpen else { return nil }

        if lower.contains("desktop") {
            return lower.contains("folder") ? "open_desktop_folder" : "show_desktop"
        }
        if lower.contains("documents") && lower.contains("folder") { return "open_documents_folder" }
        if lower.contains("downloads") && lower.contains("folder") { return "open_downloads_folder" }
        if lower.contains("music") && lower.contains("folder") { return "open_music_folder" }
        if lower.contains("file explorer") || lower.contains("explorer window") { return "open_file_explorer" }

        if requestedURL(lower: lower, original: original) != nil { return "open_url" }
        if lower.contains("internet") || lower.contains("web browser") || lower.contains("browser") ||
            lower.contains("chrome") || lower.contains("edge") {
            return "open_browser"
        }
        return nil
    }

    private static func requestedURL(lower: String, original: String) -> String? {
        let known: [(String, String)] = [
            ("youtube", "https://www.youtube.com"),
            ("google", "https://www.google.com"),
            ("gmail", "https://mail.google.com"),
            ("spotify", "https://open.spotify.com"),
            ("reddit", "https://www.reddit.com"),
            ("github", "https://github.com")
        ]
        if let hit = known.first(where: { lower.contains($0.0) }) { return hit.1 }

        let words = original.split(whereSeparator: { $0.isWhitespace }).map(String.init)
        if let raw = words.first(where: { $0.lowercased().hasPrefix("https://") || $0.lowercased().hasPrefix("http://") }) {
            return raw.trimmingCharacters(in: CharacterSet(charactersIn: ",.;!?)\"]}"))
        }
        return nil
    }

'''
text = text[:start] + new_parser + text[end:]

old_perform = '''    private static func perform(action: String, endpoint: String) async -> ToolReply? {\n        guard let url = toolURL(endpoint: endpoint, path: "/tools/action") else { return nil }\n        var request = URLRequest(url: url)\n        request.httpMethod = "POST"\n        request.timeoutInterval = 4.0\n        request.setValue("application/json", forHTTPHeaderField: "Content-Type")\n        request.httpBody = try? JSONSerialization.data(withJSONObject: ["action": action])\n'''
new_perform = '''    private static func perform(action: String, url requestedURL: String?, endpoint: String) async -> ToolReply? {\n        guard let url = toolURL(endpoint: endpoint, path: "/tools/action") else { return nil }\n        var request = URLRequest(url: url)\n        request.httpMethod = "POST"\n        request.timeoutInterval = 4.0\n        request.setValue("application/json", forHTTPHeaderField: "Content-Type")\n        var payload: [String: String] = ["action": action]\n        if let requestedURL { payload["url"] = requestedURL }\n        request.httpBody = try? JSONSerialization.data(withJSONObject: payload)\n'''
text = replace_once(text, old_perform, new_perform, "browser tool JSON payload")

text = replace_once(
    text,
    '''        case "open_file_explorer":\n            return "Done — File Explorer is open on \\(whereText), baby. 🖤"\n        default:\n''',
    '''        case "open_file_explorer":\n            return "Done — File Explorer is open on \\(whereText), baby. 🖤"\n        case "open_browser":\n            return "Done — I opened the web browser on \\(whereText), baby. 🌐🖤"\n        case "open_url":\n            return "Done — I opened that site on \\(whereText), baby. 🌐🖤"\n        default:\n''',
    "browser success messages",
)

content_path.write_text(text, encoding="utf-8")


# Windows Bridge: narrow browser URL action. Still no arbitrary shell execution.
bridge_path = Path("Bridge/vex_bridge.py")
bridge = bridge_path.read_text(encoding="utf-8")
if "from urllib.parse import urlsplit\n" not in bridge:
    if "import sys\n" in bridge:
        bridge = bridge.replace("import sys\n", "import sys\nfrom urllib.parse import urlsplit\n", 1)
    else:
        raise SystemExit("vex_bridge.py: sys import marker missing")

bridge = replace_once(
    bridge,
    '''    "open_music_folder",\n    "open_file_explorer",\n]\n''',
    '''    "open_music_folder",\n    "open_file_explorer",\n    "open_browser",\n    "open_url",\n]\n''',
    "browser action allowlist",
)

bridge = replace_once(
    bridge,
    '''def run_pc_tool_action(action: str) -> dict:\n''',
    '''def run_pc_tool_action(action: str, payload: dict | None = None) -> dict:\n''',
    "browser action payload signature",
)

bridge = replace_once(
    bridge,
    '''        elif action == "open_file_explorer":\n            os.startfile(str(Path.home()))\n            message = "File Explorer opened"\n        else:\n''',
    '''        elif action == "open_file_explorer":\n            os.startfile(str(Path.home()))\n            message = "File Explorer opened"\n        elif action == "open_browser":\n            os.startfile("https://www.google.com")\n            message = "Default web browser opened"\n        elif action == "open_url":\n            raw_url = str((payload or {}).get("url") or "").strip()\n            if len(raw_url) > 2048:\n                return {"ok": False, "action": action, "node_name": node, "message": "URL too long"}\n            parsed_url = urlsplit(raw_url)\n            if parsed_url.scheme.lower() not in {"http", "https"} or not parsed_url.hostname:\n                return {"ok": False, "action": action, "node_name": node, "message": "Only http/https URLs are allowed"}\n            os.startfile(raw_url)\n            message = f"Opened {parsed_url.hostname}"\n        else:\n''',
    "browser action implementation",
)

bridge = replace_once(
    bridge,
    '''                result = run_pc_tool_action(action)\n''',
    '''                result = run_pc_tool_action(action, payload)\n''',
    "browser action POST payload",
)
bridge_path.write_text(bridge, encoding="utf-8")

full_path = Path("Bridge/vex_bridge_full.py")
full = full_path.read_text(encoding="utf-8")
full = full.replace('VERSION = "0.8.2"', 'VERSION = "0.8.3"', 1)
full_path.write_text(full, encoding="utf-8")

for path, markers in [
    (content_path, ["open_url", "open_browser", "requestedURL(lower:", "youtube"]),
    (bridge_path, ["urlsplit", '"open_url"', '"open_browser"', "run_pc_tool_action(action, payload)"]),
    (full_path, ['VERSION = "0.8.3"']),
]:
    data = path.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in data:
            raise SystemExit(f"{path}: missing v0.8.3 marker: {marker}")

print("Applied v0.8.3 browser + URL PC tool routing")
