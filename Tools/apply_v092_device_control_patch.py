#!/usr/bin/env python3
from pathlib import Path


def once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"{label}: source block not found")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# iPhone: deterministic phone tools + more forgiving PC target parsing.
# Device commands are intercepted before WebBrain/Qwen so the tiny model never
# gets to decide whether a real tool exists.
# ---------------------------------------------------------------------------
content_path = Path("VexNative/ContentView.swift")
text = content_path.read_text(encoding="utf-8")

if "import UIKit\n" not in text:
    text = text.replace("import SwiftUI\n", "import SwiftUI\nimport UIKit\n", 1)

integration_old = '''        if await PCBridgeToolRouter.tryHandle(original, app: self) {
            return
        }
'''
integration_new = '''        if await PhoneToolRouter.tryHandle(original, app: self) {
            return
        }

        if await PCBridgeToolRouter.tryHandle(original, app: self) {
            return
        }
'''
text = once(text, integration_old, integration_new, "phone router interception")

pc_marker = "// MARK: - Grounded PC Bridge tools v0.8.2\n"
if pc_marker not in text:
    raise SystemExit("ContentView.swift: PC router marker missing")

phone_router = r'''// MARK: - Native iPhone tools v0.9.2

@MainActor
private enum PhoneToolRouter {
    static func tryHandle(_ original: String, app: AppModel) async -> Bool {
        let lower = normalize(original)
        guard explicitlyTargetsPhone(lower) else { return false }

        app.draft = ""
        app.isGenerating = true
        defer { app.isGenerating = false }

        if isCapabilityQuestion(lower) {
            appendExchange(
                user: original,
                assistant: "On this iPhone I can directly use the Vex app's granted iOS capabilities, open apps/sites through iOS, open Vex Settings, set screen brightness, control the flashlight, use camera/photos inside Vex, use mic/speech, speak replies, and use the clipboard. Apple still sandboxes third-party apps, so iOS does not expose arbitrary silent control of every system switch or every other app. For the paired Windows PCs my Bridge can do much more because the companion agent runs on those machines. 📱🖥️🖤",
                app: app
            )
            return true
        }

        if lower.contains("settings") {
            let ok = await openURL(URL(string: UIApplication.openSettingsURLString)!)
            appendExchange(user: original, assistant: ok ? "Done — I opened my iPhone settings, baby. 📱🖤" : "iOS didn't open Settings for me, baby. 🖤", app: app)
            return true
        }

        if lower.contains("brightness") {
            guard let percent = firstNumber(in: lower) else {
                appendExchange(user: original, assistant: "Give me a brightness percentage from 0 to 100, baby. 📱🖤", app: app)
                return true
            }
            let clamped = max(0, min(100, percent))
            UIScreen.main.brightness = CGFloat(clamped / 100.0)
            appendExchange(user: original, assistant: "Done — iPhone brightness is at \(Int(clamped.rounded()))%. 📱🖤", app: app)
            return true
        }

        if lower.contains("flashlight") || lower.contains("torch") {
            let result = setTorch(lower)
            appendExchange(user: original, assistant: result, app: app)
            return true
        }

        if lower.contains("clipboard") && (lower.contains("copy ") || lower.contains("put ")) {
            if let payload = clipboardPayload(original) {
                UIPasteboard.general.string = payload
                appendExchange(user: original, assistant: "Done — I put that on the iPhone clipboard, baby. 📋🖤", app: app)
            } else {
                appendExchange(user: original, assistant: "Tell me what you want copied to the iPhone clipboard, baby. 🖤", app: app)
            }
            return true
        }

        if wantsOpen(lower), let url = knownURL(lower: lower, original: original) {
            let ok = await openURL(url)
            appendExchange(
                user: original,
                assistant: ok ? "Done — I opened it on the iPhone, baby. 📱🖤" : "iOS wouldn't open that target for me, baby. 🖤",
                app: app
            )
            return true
        }

        return false
    }

    private static func explicitlyTargetsPhone(_ lower: String) -> Bool {
        [
            "iphone", "my phone", "the phone", "this phone", "on phone", "on the phone",
            "on my phone", "on this phone", "on the iphone", "on my iphone", "here on the phone"
        ].contains(where: { lower.contains($0) })
    }

    private static func isCapabilityQuestion(_ lower: String) -> Bool {
        lower.contains("what can you") || lower.contains("can you control") ||
            lower.contains("access to") || lower.contains("have access") ||
            lower.contains("full control") || lower.contains("what do you control")
    }

    private static func wantsOpen(_ lower: String) -> Bool {
        ["open ", "open up ", "launch ", "go to ", "bring up ", "show me "]
            .contains(where: { lower.contains($0) })
    }

    private static func knownURL(lower: String, original: String) -> URL? {
        let known: [(String, String)] = [
            ("youtube", "https://www.youtube.com"),
            ("google", "https://www.google.com"),
            ("gmail", "https://mail.google.com"),
            ("spotify", "https://open.spotify.com"),
            ("reddit", "https://www.reddit.com"),
            ("github", "https://github.com"),
            ("maps", "https://maps.apple.com")
        ]
        if let hit = known.first(where: { lower.contains($0.0) }) {
            return URL(string: hit.1)
        }

        let words = original.split(whereSeparator: { $0.isWhitespace }).map(String.init)
        if let raw = words.first(where: { $0.lowercased().hasPrefix("https://") || $0.lowercased().hasPrefix("http://") }) {
            let clean = raw.trimmingCharacters(in: CharacterSet(charactersIn: ",.;!?)\"]}"))
            return URL(string: clean)
        }
        return nil
    }

    private static func openURL(_ url: URL) async -> Bool {
        await withCheckedContinuation { continuation in
            UIApplication.shared.open(url, options: [:]) { opened in
                continuation.resume(returning: opened)
            }
        }
    }

    private static func firstNumber(in text: String) -> Double? {
        var current = ""
        var seenDigit = false
        for ch in text {
            if ch.isNumber || (ch == "." && seenDigit) {
                current.append(ch)
                seenDigit = seenDigit || ch.isNumber
            } else if seenDigit {
                break
            }
        }
        return Double(current)
    }

    private static func setTorch(_ lower: String) -> String {
        guard let device = AVCaptureDevice.default(for: .video), device.hasTorch else {
            return "This iPhone isn't exposing a flashlight device to Vex right now, baby. 🖤"
        }
        do {
            try device.lockForConfiguration()
            defer { device.unlockForConfiguration() }
            let wantsOff = lower.contains(" off") || lower.hasSuffix("off")
            let wantsOn = lower.contains(" on") || lower.hasSuffix("on")
            if wantsOff {
                device.torchMode = .off
                return "Done — flashlight off. 📱🖤"
            }
            if wantsOn {
                try device.setTorchModeOn(level: 1.0)
                return "Done — flashlight on. 🔦🖤"
            }
            if device.isTorchActive {
                device.torchMode = .off
                return "Done — flashlight off. 📱🖤"
            }
            try device.setTorchModeOn(level: 1.0)
            return "Done — flashlight on. 🔦🖤"
        } catch {
            return "The iPhone wouldn't change the flashlight: \(error.localizedDescription)"
        }
    }

    private static func clipboardPayload(_ original: String) -> String? {
        let lower = original.lowercased()
        for marker in ["copy ", "put "] {
            guard let range = lower.range(of: marker) else { continue }
            var value = String(original[range.upperBound...]).trimmingCharacters(in: .whitespacesAndNewlines)
            let suffixes = [" to the clipboard", " on the clipboard", " to clipboard", " on clipboard", " to my iphone clipboard"]
            for suffix in suffixes where value.lowercased().hasSuffix(suffix) {
                value = String(value.dropLast(suffix.count)).trimmingCharacters(in: .whitespacesAndNewlines)
                break
            }
            if !value.isEmpty { return value }
        }
        return nil
    }

    private static func appendExchange(user: String, assistant: String, app: AppModel) {
        app.draft = ""
        app.profile.messages.append(ChatMessage(role: .user, content: user))
        app.profile.messages.append(ChatMessage(role: .assistant, content: assistant))
        app.persist()
    }

    private static func normalize(_ text: String) -> String {
        text.lowercased()
            .replacingOccurrences(of: "’", with: "'")
            .replacingOccurrences(of: "‘", with: "'")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

'''
text = text.replace(pc_marker, phone_router + pc_marker, 1)

# Replace the complete v0.8.5 target resolver. This catches natural word order
# such as "PC in the kitchen", "downstairs kitchen computer", "the computer
# upstairs", and keeps the explicit/recent target behavior.
target_start = text.find("    private static func requestedTarget(_ lower: String) -> NodeTarget? {")
target_end = text.find("    private static func requestedAction", target_start)
if target_start < 0 or target_end < 0:
    raise SystemExit("ContentView.swift: PC target resolver bounds missing")
new_target = r'''    private static func requestedTarget(_ lower: String) -> NodeTarget? {
        func remember(_ value: String, _ target: NodeTarget) -> NodeTarget {
            UserDefaults.standard.set(value, forKey: lastTargetKey)
            return target
        }

        let bothAliases = [
            "both computers", "both pcs", "both pc", "both machines", "both windows pcs",
            "all computers", "all pcs"
        ]
        if bothAliases.contains(where: { lower.contains($0) }) {
            return remember("both", .both)
        }

        let secondaryAliases = [
            "kitchen pc", "kitchen computer", "pc in the kitchen", "computer in the kitchen",
            "pc downstairs", "computer downstairs", "downstairs pc", "downstairs computer",
            "downstairs kitchen", "kitchen downstairs", "second pc", "second computer",
            "secondary pc", "secondary computer", "in the kitchen", "to the kitchen",
            "downstairs", "hp computer", "hp pc"
        ]
        if secondaryAliases.contains(where: { lower.contains($0) }) {
            return remember("secondary", .secondary)
        }

        let primaryAliases = [
            "upstairs pc", "upstairs computer", "pc upstairs", "computer upstairs",
            "pc in the upstairs", "computer in the upstairs", "primary pc", "primary computer",
            "main pc", "main computer", "upstairs", "monte computer", "monte pc"
        ]
        if primaryAliases.contains(where: { lower.contains($0) }) {
            return remember("primary", .primary)
        }

        let refersToPC = lower.contains(" pc") || lower.hasPrefix("pc ") ||
            lower.contains("computer") || lower.contains("machine")
        let refersBack = lower == "open it" || lower == "launch it" || lower == "start it" ||
            lower.contains(" on it") || lower.contains(" on that") || lower.contains(" that computer") ||
            lower.contains(" that pc") || lower.hasSuffix(" there")

        if refersBack || refersToPC {
            switch UserDefaults.standard.string(forKey: lastTargetKey) {
            case "primary": return .primary
            case "secondary": return .secondary
            case "both": return .both
            default: break
            }
        }

        let nodes = configuredNodes()
        if refersToPC, nodes.count == 1 {
            return nodes[0].label == "kitchen/downstairs PC" ? .secondary : .primary
        }
        return nil
    }

'''
text = text[:target_start] + new_target + text[target_end:]

# Add deterministic Windows-system actions to the existing parser.
action_head = '''    private static func requestedAction(_ lower: String, original: String, mediaQuery: String?) -> String? {
        if mediaQuery != nil { return "play_named_media" }
'''
action_new = '''    private static func requestedAction(_ lower: String, original: String, mediaQuery: String?) -> String? {
        if mediaQuery != nil { return "play_named_media" }
        if lower.contains("lock the pc") || lower.contains("lock pc") || lower.contains("lock the computer") || lower.contains("lock computer") { return "lock_screen" }
        if lower.contains("windows settings") || lower.contains("pc settings") || lower.contains("computer settings") { return "open_windows_settings" }
        if lower.contains("task manager") { return "open_task_manager" }
        if lower.contains("start menu") { return "open_start_menu" }
        if lower.contains("task view") { return "open_task_view" }
        if lower.contains("run dialog") || lower.contains("windows run") { return "open_run_dialog" }
        if lower.contains("windows search") || lower.contains("pc search") { return "open_windows_search" }
        if lower.contains("minimize all") || lower.contains("minimise all") { return "minimize_all_windows" }
        if lower.contains("restore all windows") || lower.contains("bring all windows back") { return "restore_all_windows" }
        if lower.contains("close the active window") || lower.contains("close active window") || lower.contains("close the current window") { return "close_active_window" }
'''
text = once(text, action_head, action_new, "expanded PC action parser")

# If the direct /tools/action path is missing or stale, try the already-authenticated
# skill compiler for browser/folder actions before giving up. This fixes mixed
# Bridge versions much more gracefully and keeps truthfulness about actual success.
perform_line = '''            if let result = await perform(action: action, url: requestedURL, mediaQuery: mediaQuery, endpoint: node.endpoint), result.ok {
'''
perform_fallback = '''            var result = await perform(action: action, url: requestedURL, mediaQuery: mediaQuery, endpoint: node.endpoint)
            if result?.ok != true && ["open_url", "open_browser", "open_desktop_folder", "open_documents_folder", "open_downloads_folder", "open_music_folder", "open_file_explorer"].contains(action) {
                result = await performLearnedSkill(original: original, endpoint: node.endpoint)
            }
            if let result, result.ok {
'''
text = once(text, perform_line, perform_fallback, "Bridge action compatibility fallback")

success_default = '''        default:
            return "Done on \\(whereText), baby. 🖤"
'''
expanded_success = '''        case "lock_screen":
            return "Done — I locked \\(whereText), baby. 🔒🖤"
        case "open_windows_settings":
            return "Done — Windows Settings is open on \\(whereText), baby. 🖥️🖤"
        case "open_task_manager":
            return "Done — Task Manager is open on \\(whereText), baby. 🖥️🖤"
        case "open_start_menu":
            return "Done — Start is open on \\(whereText), baby. 🖥️🖤"
        case "open_task_view":
            return "Done — Task View is open on \\(whereText), baby. 🖥️🖤"
        case "open_run_dialog":
            return "Done — Run is open on \\(whereText), baby. 🖥️🖤"
        case "open_windows_search":
            return "Done — Windows Search is open on \\(whereText), baby. 🖥️🖤"
        case "minimize_all_windows":
            return "Done — I minimized the windows on \\(whereText), baby. 🖥️🖤"
        case "restore_all_windows":
            return "Done — I restored the windows on \\(whereText), baby. 🖥️🖤"
        case "close_active_window":
            return "Done — I closed the active window on \\(whereText), baby. 🖥️🖤"
        default:
            return "Done on \\(whereText), baby. 🖤"
'''
text = once(text, success_default, expanded_success, "expanded PC success messages")

content_path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Windows Bridge: expanded allowlisted desktop controls. Still intentionally no
# arbitrary shell/PowerShell command endpoint and no downloaded-code execution.
# ---------------------------------------------------------------------------
bridge_path = Path("Bridge/vex_bridge.py")
bridge = bridge_path.read_text(encoding="utf-8")

list_start = bridge.find("PC_TOOL_ACTIONS = [")
list_end = bridge.find("]\n", list_start)
if list_start < 0 or list_end < 0:
    raise SystemExit("vex_bridge.py: PC_TOOL_ACTIONS missing")
list_block = bridge[list_start:list_end]
new_actions = [
    "lock_screen",
    "open_windows_settings",
    "open_task_manager",
    "open_start_menu",
    "open_task_view",
    "open_run_dialog",
    "open_windows_search",
    "minimize_all_windows",
    "restore_all_windows",
    "close_active_window",
]
for action in new_actions:
    if f'"{action}"' not in list_block:
        list_block += f'    "{action}",\n'
bridge = bridge[:list_start] + list_block + bridge[list_end:]

run_marker = "def run_pc_tool_action(action: str, payload: dict | None = None) -> dict:\n"
if run_marker not in bridge:
    raise SystemExit("vex_bridge.py: action executor marker missing")
combo_helper = r'''def _press_windows_combo(keys: list[int]) -> None:
    user32 = ctypes.windll.user32
    KEYEVENTF_KEYUP = 0x0002
    for key in keys:
        user32.keybd_event(key, 0, 0, 0)
    for key in reversed(keys):
        user32.keybd_event(key, 0, KEYEVENTF_KEYUP, 0)


'''
if "def _press_windows_combo(" not in bridge:
    bridge = bridge.replace(run_marker, combo_helper + run_marker, 1)

executor_head = '''    try:
        if action == "play_named_media":
'''
executor_new = '''    try:
        if action == "lock_screen":
            if not ctypes.windll.user32.LockWorkStation():
                raise RuntimeError("Windows refused LockWorkStation")
            message = "workstation locked"
        elif action == "open_windows_settings":
            os.startfile("ms-settings:")
            message = "Windows Settings opened"
        elif action == "open_task_manager":
            taskmgr = Path(os.environ.get("WINDIR", r"C:\\Windows")) / "System32" / "Taskmgr.exe"
            os.startfile(str(taskmgr))
            message = "Task Manager opened"
        elif action == "open_start_menu":
            _press_windows_combo([0x5B])
            message = "Start menu opened"
        elif action == "open_task_view":
            _press_windows_combo([0x5B, 0x09])
            message = "Task View opened"
        elif action == "open_run_dialog":
            _press_windows_combo([0x5B, 0x52])
            message = "Run dialog opened"
        elif action == "open_windows_search":
            _press_windows_combo([0x5B, 0x53])
            message = "Windows Search opened"
        elif action == "minimize_all_windows":
            _press_windows_combo([0x5B, 0x4D])
            message = "windows minimized"
        elif action == "restore_all_windows":
            _press_windows_combo([0x5B, 0x10, 0x4D])
            message = "windows restored"
        elif action == "close_active_window":
            _press_windows_combo([0x12, 0x73])
            message = "active window close requested"
        elif action == "play_named_media":
'''
bridge = once(bridge, executor_head, executor_new, "expanded Windows action executor")

bridge_path.write_text(bridge, encoding="utf-8")

full_path = Path("Bridge/vex_bridge_full.py")
full = full_path.read_text(encoding="utf-8")
full = once(full, 'VERSION = "0.9.1"', 'VERSION = "0.9.2"', "Bridge version")
full_path.write_text(full, encoding="utf-8")

for path, markers in [
    (content_path, [
        "PhoneToolRouter", "pc in the kitchen", "downstairs kitchen", "Bridge action compatibility fallback" if False else "performLearnedSkill(original: original",
        'return "lock_screen"', "UIApplication.openSettingsURLString", "UIScreen.main.brightness"
    ]),
    (bridge_path, [
        '"lock_screen"', '"open_windows_settings"', "_press_windows_combo", "LockWorkStation", "Taskmgr.exe"
    ]),
    (full_path, ['VERSION = "0.9.2"']),
]:
    data = path.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in data:
            raise SystemExit(f"{path}: missing v0.9.2 marker: {marker}")

print("Applied v0.9.2 deterministic phone tools + reliable/expanded PC control")
