#!/usr/bin/env python3
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"{label}: expected source block not found")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# iPhone: intercept capability questions and simple PC actions before WebBrain
# or the tiny model can turn them into random file-search chatter.
# ---------------------------------------------------------------------------
content_path = Path("VexNative/ContentView.swift")
text = content_path.read_text(encoding="utf-8")

integration_marker = '''extension AppModel {\n    func sendWithWeb() async {\n        let original = draft.trimmingCharacters(in: .whitespacesAndNewlines)\n        guard !original.isEmpty, !isGenerating else { return }\n\n'''
integration_new = '''extension AppModel {\n    func sendWithWeb() async {\n        let original = draft.trimmingCharacters(in: .whitespacesAndNewlines)\n        guard !original.isEmpty, !isGenerating else { return }\n\n        if await PCBridgeToolRouter.tryHandle(original, app: self) {\n            return\n        }\n\n'''
text = replace_once(text, integration_marker, integration_new, "tool router interception")

insert_marker = '''// MARK: - App integration\n\nextension AppModel {\n'''
tool_router = r'''// MARK: - Grounded PC Bridge tools v0.8.2

@MainActor
private enum PCBridgeToolRouter {
    private enum NodeTarget {
        case primary
        case secondary
        case both
    }

    private struct NodeStatus: Decodable {
        let name: String?
        let version: String?
        let node_name: String?
        let indexed_files: Int?
        let music_assets: Int?
        let tool_actions: [String]?
    }

    private struct ToolReply: Decodable {
        let ok: Bool
        let action: String?
        let node_name: String?
        let message: String?
    }

    private struct EndpointNode {
        let label: String
        let endpoint: String
    }

    static func tryHandle(_ original: String, app: AppModel) async -> Bool {
        let lower = normalize(original)

        if isCapabilityQuestion(lower) {
            app.draft = ""
            app.isGenerating = true
            defer { app.isGenerating = false }

            let nodes = configuredNodes()
            var online: [(EndpointNode, NodeStatus)] = []
            for node in nodes {
                if let status = await fetchStatus(node.endpoint) {
                    online.append((node, status))
                }
            }

            app.pcBrainConnected = !online.isEmpty
            if online.isEmpty {
                app.pcBrainStatus = "Phone brain only"
            } else {
                app.pcBrainStatus = "PC mesh • \(online.count)/\(nodes.count) online"
            }

            let nodeNames = online.map { pair in
                let reported = pair.1.node_name?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                return reported.isEmpty ? pair.0.label : reported
            }

            let reply: String
            if online.count >= 2 {
                reply = "Yep, baby — both paired PCs are online through my Bridge mesh: \(naturalList(nodeNames)). I can use their long-term brain vaults, search/read indexed files, find music/project assets, and trigger the PC actions I've actually been given. On the phone I can use my own app data plus camera/photos you attach and other iOS permissions the app has — not the entire iPhone filesystem or arbitrary system control. 🧠📱🖥️🖥️"
            } else if online.count == 1 {
                reply = "I can reach \(nodeNames.first ?? "one paired PC") right now, baby. The other Bridge isn't answering this second. I can still use my local phone brain, app data, camera/photo attachments, and the connected PC's memory/file tools. 🧠🖤"
            } else {
                reply = "I'm running locally on your phone, but neither paired PC Bridge answered that check, baby. I still have my phone brain and app-local data; PC memory/file/actions come back automatically when a Bridge is reachable. 🖤"
            }

            appendExchange(user: original, assistant: reply, app: app)
            return true
        }

        guard let action = requestedAction(lower) else { return false }
        guard let target = requestedTarget(lower) else { return false }

        let nodes = configuredNodes()
        let selected: [EndpointNode]
        switch target {
        case .primary:
            selected = nodes.filter { $0.label == "upstairs/primary PC" }
        case .secondary:
            selected = nodes.filter { $0.label == "kitchen/downstairs PC" }
        case .both:
            selected = nodes
        }
        guard !selected.isEmpty else {
            appendExchange(
                user: original,
                assistant: target == .secondary
                    ? "I don't have a kitchen/downstairs Bridge endpoint saved yet, baby. 🖤"
                    : "I don't have that PC Bridge paired yet, baby. 🖤",
                app: app
            )
            return true
        }

        app.draft = ""
        app.isGenerating = true
        defer { app.isGenerating = false }

        var successes: [String] = []
        var failures: [String] = []
        for node in selected {
            if let result = await perform(action: action, endpoint: node.endpoint), result.ok {
                let reported = result.node_name?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                successes.append(reported.isEmpty ? node.label : reported)
            } else {
                failures.append(node.label)
            }
        }

        let reply: String
        if !successes.isEmpty && failures.isEmpty {
            reply = successMessage(action: action, nodes: successes)
        } else if !successes.isEmpty {
            reply = "I did it on \(naturalList(successes)), baby, but \(naturalList(failures)) didn't answer the command. 🖤"
        } else {
            reply = "That PC command didn't reach the Bridge, baby. The brain/file connection can still be online even when a tool action fails, so I'm not pretending it happened. 🖤"
        }
        appendExchange(user: original, assistant: reply, app: app)
        return true
    }

    private static func configuredNodes() -> [EndpointNode] {
        let defaults = UserDefaults.standard
        let primary = defaults.string(forKey: WebBrain.searxEndpointKey)?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let secondary = defaults.string(forKey: WebBrain.secondaryBridgeEndpointKey)?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""

        var result: [EndpointNode] = []
        if isBridgeEndpoint(primary) {
            result.append(EndpointNode(label: "upstairs/primary PC", endpoint: primary))
        }
        if secondary != primary, isBridgeEndpoint(secondary) {
            result.append(EndpointNode(label: "kitchen/downstairs PC", endpoint: secondary))
        }
        return result
    }

    private static func isBridgeEndpoint(_ endpoint: String) -> Bool {
        guard !endpoint.isEmpty, let url = URL(string: endpoint) else { return false }
        return VexBridgeNetworking.isBridgeURL(url)
    }

    private static func isCapabilityQuestion(_ lower: String) -> Bool {
        let hasDevice = lower.contains("computer") || lower.contains(" pc") || lower.hasPrefix("pc") ||
            lower.contains("phone") || lower.contains("bridge")
        let asksAccess = lower.contains("can you access") || lower.contains("do you have access") ||
            lower.contains("what can you access") || lower.contains("are both computers") ||
            lower.contains("are both pcs") || lower.contains("can you use both") ||
            lower.contains("connected to both")
        return hasDevice && asksAccess
    }

    private static func requestedTarget(_ lower: String) -> NodeTarget? {
        if lower.contains("both computers") || lower.contains("both pcs") || lower.contains("both pc") {
            return .both
        }
        if ["kitchen pc", "kitchen computer", "downstairs pc", "downstairs computer", "second pc"]
            .contains(where: { lower.contains($0) }) {
            return .secondary
        }
        if ["upstairs pc", "upstairs computer", "primary pc", "main pc"]
            .contains(where: { lower.contains($0) }) {
            return .primary
        }
        return nil
    }

    private static func requestedAction(_ lower: String) -> String? {
        let asksOpen = lower.contains("open ") || lower.hasPrefix("open") ||
            lower.contains("show ") || lower.hasPrefix("show") || lower.contains("go to ")
        guard asksOpen else { return nil }

        if lower.contains("desktop") {
            return lower.contains("folder") ? "open_desktop_folder" : "show_desktop"
        }
        if lower.contains("documents") && lower.contains("folder") { return "open_documents_folder" }
        if lower.contains("downloads") && lower.contains("folder") { return "open_downloads_folder" }
        if lower.contains("music") && lower.contains("folder") { return "open_music_folder" }
        if lower.contains("file explorer") || lower.contains("explorer window") { return "open_file_explorer" }
        return nil
    }

    private static func fetchStatus(_ endpoint: String) async -> NodeStatus? {
        guard let url = toolURL(endpoint: endpoint, path: "/status") else { return nil }
        var request = URLRequest(url: url)
        request.timeoutInterval = 3.0
        do {
            let (data, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else { return nil }
            return try JSONDecoder().decode(NodeStatus.self, from: data)
        } catch {
            return nil
        }
    }

    private static func perform(action: String, endpoint: String) async -> ToolReply? {
        guard let url = toolURL(endpoint: endpoint, path: "/tools/action") else { return nil }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 4.0
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: ["action": action])
        do {
            let (data, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...499).contains(http.statusCode) else { return nil }
            return try JSONDecoder().decode(ToolReply.self, from: data)
        } catch {
            return nil
        }
    }

    private static func toolURL(endpoint: String, path: String) -> URL? {
        guard let root = URL(string: endpoint),
              var components = URLComponents(url: root, resolvingAgainstBaseURL: false)
        else { return nil }
        components.path = path
        return components.url
    }

    private static func appendExchange(user: String, assistant: String, app: AppModel) {
        app.draft = ""
        app.profile.messages.append(ChatMessage(role: .user, content: user))
        app.profile.messages.append(ChatMessage(role: .assistant, content: assistant))
        app.persist()
    }

    private static func successMessage(action: String, nodes: [String]) -> String {
        let whereText = naturalList(nodes)
        switch action {
        case "show_desktop":
            return "Done, baby — I showed the desktop on \(whereText). 😈🖤"
        case "open_desktop_folder":
            return "Done — Desktop folder is open on \(whereText), baby. 🖤"
        case "open_documents_folder":
            return "Done — Documents is open on \(whereText), baby. 🖤"
        case "open_downloads_folder":
            return "Done — Downloads is open on \(whereText), baby. 🖤"
        case "open_music_folder":
            return "Done — Music is open on \(whereText), baby. 🎛️🖤"
        case "open_file_explorer":
            return "Done — File Explorer is open on \(whereText), baby. 🖤"
        default:
            return "Done on \(whereText), baby. 🖤"
        }
    }

    private static func naturalList(_ values: [String]) -> String {
        if values.isEmpty { return "the PC" }
        if values.count == 1 { return values[0] }
        if values.count == 2 { return "\(values[0]) and \(values[1])" }
        return values.dropLast().joined(separator: ", ") + ", and " + values.last!
    }

    private static func normalize(_ text: String) -> String {
        text.lowercased()
            .replacingOccurrences(of: "’", with: "'")
            .replacingOccurrences(of: "‘", with: "'")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

'''
if insert_marker not in text:
    raise SystemExit("ContentView.swift: app integration marker missing")
text = text.replace(insert_marker, tool_router + insert_marker, 1)
content_path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Prompt: teach the model what the Bridge actually means so generic model priors
# do not overwrite live app capabilities.
# ---------------------------------------------------------------------------
prompt_path = Path("VexNative/Core/PromptComposer.swift")
prompt = prompt_path.read_text(encoding="utf-8")

capability_note = '''\n            CONNECTED TOOL REALITY\n            VexNative can use paired Vex Bridge PCs for external memory retrieval and indexed-file/music-asset search when those nodes are online. A native tool router handles supported PC actions before this model is called. Never say “I can't access anything directly” as a blanket claim. Never claim an unsupported action succeeded; only native tool results can confirm actions. The iPhone side is sandboxed: app-local brain/chat, camera/photo attachments, and granted iOS permissions are available, not unrestricted whole-phone filesystem/control.\n'''

first_marker = '''            PC EXPANSION BRAIN\n            \\(expansionBlock)\n            Treat this as retrieved older evidence. The newest Star message and CURRENT VEX STATE always win conflicts.\n\n            RESPONSE RULES\n'''
first_new = '''            PC EXPANSION BRAIN\n            \\(expansionBlock)\n            Treat this as retrieved older evidence. The newest Star message and CURRENT VEX STATE always win conflicts.\n''' + capability_note + '''\n            RESPONSE RULES\n'''
if first_marker in prompt:
    prompt = prompt.replace(first_marker, first_new, 1)

second_marker = '''            PC EXPANSION BRAIN\n            \\(expansionBlock)\n            Treat this as retrieved older evidence. The newest Star message and CURRENT VEX STATE always win conflicts.\n\n            VOICE SHAPING\n'''
second_new = '''            PC EXPANSION BRAIN\n            \\(expansionBlock)\n            Treat this as retrieved older evidence. The newest Star message and CURRENT VEX STATE always win conflicts.\n''' + capability_note + '''\n            VOICE SHAPING\n'''
if second_marker in prompt:
    prompt = prompt.replace(second_marker, second_new, 1)

web_marker = '''        Older PC memory is supplemental only; newest user facts and retrieved web evidence win conflicts.\n        """\n'''
web_new = '''        Older PC memory is supplemental only; newest user facts and retrieved web evidence win conflicts.\n        Connected Vex Bridge PCs are real app tools for memory/file retrieval when online. Do not deny all access, and do not invent tool success.\n        """\n'''
if web_marker in prompt:
    prompt = prompt.replace(web_marker, web_new, 1)

if "CONNECTED TOOL REALITY" not in prompt:
    raise SystemExit("PromptComposer.swift: capability grounding marker missing")
prompt_path.write_text(prompt, encoding="utf-8")


# ---------------------------------------------------------------------------
# Windows Bridge: add a narrow allowlisted remote-action surface. No arbitrary
# shell execution. This is enough to prove actual machine control safely and to
# create the foundation for later music/DAW tools.
# ---------------------------------------------------------------------------
bridge_path = Path("Bridge/vex_bridge.py")
bridge = bridge_path.read_text(encoding="utf-8")

if "import ctypes\n" not in bridge:
    bridge = bridge.replace("import argparse\n", "import argparse\nimport ctypes\n", 1)

state_marker = "\n\nclass BridgeState:\n"
if state_marker not in bridge:
    raise SystemExit("vex_bridge.py: BridgeState marker missing")

tool_impl = r'''

PC_TOOL_ACTIONS = [
    "show_desktop",
    "open_desktop_folder",
    "open_documents_folder",
    "open_downloads_folder",
    "open_music_folder",
    "open_file_explorer",
]


def _existing_user_folder(name: str) -> Path:
    candidate = Path.home() / name
    return candidate if candidate.exists() else Path.home()


def run_pc_tool_action(action: str) -> dict:
    node = socket.gethostname() or "PC"
    if action not in PC_TOOL_ACTIONS:
        return {"ok": False, "action": action, "node_name": node, "message": "unsupported action"}
    if not sys.platform.startswith("win"):
        return {"ok": False, "action": action, "node_name": node, "message": "Windows action unavailable"}

    try:
        if action == "show_desktop":
            user32 = ctypes.windll.user32
            VK_LWIN = 0x5B
            VK_D = 0x44
            KEYEVENTF_KEYUP = 0x0002
            user32.keybd_event(VK_LWIN, 0, 0, 0)
            user32.keybd_event(VK_D, 0, 0, 0)
            user32.keybd_event(VK_D, 0, KEYEVENTF_KEYUP, 0)
            user32.keybd_event(VK_LWIN, 0, KEYEVENTF_KEYUP, 0)
            message = "desktop shown"
        elif action == "open_desktop_folder":
            os.startfile(str(_existing_user_folder("Desktop")))
            message = "Desktop folder opened"
        elif action == "open_documents_folder":
            os.startfile(str(_existing_user_folder("Documents")))
            message = "Documents folder opened"
        elif action == "open_downloads_folder":
            os.startfile(str(_existing_user_folder("Downloads")))
            message = "Downloads folder opened"
        elif action == "open_music_folder":
            os.startfile(str(_existing_user_folder("Music")))
            message = "Music folder opened"
        elif action == "open_file_explorer":
            os.startfile(str(Path.home()))
            message = "File Explorer opened"
        else:
            return {"ok": False, "action": action, "node_name": node, "message": "unsupported action"}
        print(f"[tool] node={node} action={action} ok=1", flush=True)
        return {"ok": True, "action": action, "node_name": node, "message": message}
    except Exception as exc:
        print(f"[tool] node={node} action={action} ok=0 error={exc}", flush=True)
        return {"ok": False, "action": action, "node_name": node, "message": str(exc)}

'''
bridge = bridge.replace(state_marker, tool_impl + state_marker, 1)

status_marker = '                "uptime_seconds": int(time.time() - STATE.started),\n'
status_new = '                "uptime_seconds": int(time.time() - STATE.started),\n                "node_name": socket.gethostname() or "PC",\n                "music_assets": len(getattr(STATE.index, "music_assets", [])),\n                "tool_actions": PC_TOOL_ACTIONS,\n'
bridge = replace_once(bridge, status_marker, status_new, "Bridge status capabilities")

post_gate = '''        if parsed.path not in ("/brain/context", "/brain/sync"):\n            self._json(404, {"error": "not found"})\n            return\n\n        try:\n'''
post_gate_new = '''        if parsed.path == "/tools/action":\n            try:\n                length = int(self.headers.get("Content-Length", "0"))\n                if length <= 0 or length > 32_000:\n                    self._json(413, {"error": "tool payload too large"})\n                    return\n                payload = json.loads(self.rfile.read(length).decode("utf-8"))\n                action = str(payload.get("action") or "").strip()\n                result = run_pc_tool_action(action)\n                self._json(200 if result.get("ok") else 400, result)\n            except Exception as exc:\n                self._json(400, {"ok": False, "error": f"invalid tool payload: {exc}"})\n            return\n\n        if parsed.path not in ("/brain/context", "/brain/sync"):\n            self._json(404, {"error": "not found"})\n            return\n\n        try:\n'''
bridge = replace_once(bridge, post_gate, post_gate_new, "Bridge tool POST route")

bridge_path.write_text(bridge, encoding="utf-8")

full_path = Path("Bridge/vex_bridge_full.py")
full = full_path.read_text(encoding="utf-8")
full = full.replace('VERSION = "0.8.1"', 'VERSION = "0.8.2"', 1)
full_path.write_text(full, encoding="utf-8")

for path, markers in [
    (content_path, ["PCBridgeToolRouter", "tryHandle(original", "open_music_folder", "PC mesh"]),
    (prompt_path, ["CONNECTED TOOL REALITY", "do not invent tool success"]),
    (bridge_path, ["PC_TOOL_ACTIONS", "run_pc_tool_action", 'parsed.path == "/tools/action"', '"tool_actions": PC_TOOL_ACTIONS']),
    (full_path, ['VERSION = "0.8.2"']),
]:
    data = path.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in data:
            raise SystemExit(f"{path}: missing v0.8.2 marker: {marker}")

print("Applied v0.8.2 grounded PC capability + allowlisted remote-action patch")
