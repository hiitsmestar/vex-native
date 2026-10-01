#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] if "v161-unified-core-client" in str(Path(__file__)) else Path(__file__).resolve().parents[1]
CONTENT = ROOT / "VexNative" / "ContentView.swift"
MARKER = 'V161_UNIFIED_CORE_CLIENT = "v0.16.1-unified-core-client-v1"'

text = CONTENT.read_text(encoding="utf-8")
if MARKER in text:
    print("PASS v0.16.1 unified core client already applied")
    raise SystemExit(0)

anchor = 'private let V160_A2A_ROAMING_FALLBACK = "v0.16.0-a2a-roaming-fallback-v1"'
if anchor not in text:
    raise SystemExit("v0.16.1 requires v0.16.0 roaming fallback")
text = text.replace(anchor, anchor + '\nprivate let ' + MARKER, 1)

old = '''private final class VexNativeA2AClient: ObservableObject {
    @Published var online = false'''
new = '''private final class VexNativeA2AClient: ObservableObject {
    static let shared = VexNativeA2AClient()

    @Published var online = false'''
if old not in text:
    raise SystemExit("v0.16.1 client singleton anchor missing")
text = text.replace(old, new, 1)

old = '''    @Published var sending = false
    @Published var lastRefresh: Date?
'''
new = '''    @Published var sending = false
    @Published var lastRefresh: Date?
    @Published var activeNode = "—"
    @Published var activeModel = "—"
    @Published var brainMode = "—"
    @Published var memorySummary = "—"
    @Published var rendererSummary = "—"
'''
if old not in text:
    raise SystemExit("v0.16.1 client status anchor missing")
text = text.replace(old, new, 1)
refresh_anchor = '''            goalSummary = statusSummary(store["goals"])
            workSummary = statusSummary(store["work"])

            if let newest = goals.first {'''
refresh_new = '''            goalSummary = statusSummary(store["goals"])
            workSummary = statusSummary(store["work"])

            let core = object["core"] as? [String: Any] ?? [:]
            let models = object["models"] as? [String: Any] ?? [:]
            let configured = models["configured"] as? [String: Any] ?? [:]
            let renderer = object["renderer"] as? [String: Any] ?? [:]
            activeNode = (core["host"] as? String) ?? "—"
            brainMode = (core["brain_mode"] as? String) ?? "—"
            let modelKey = brainMode.lowercased() == "deep" ? "deep" : "fast"
            activeModel = (configured[modelKey] as? String) ?? "—"
            if let memory = core["memory"] as? [String: Any],
               let pressure = memory["pressure"] as? NSNumber {
                memorySummary = String(format: "%.0f%% used", pressure.doubleValue * 100)
            } else {
                memorySummary = "—"
            }
            rendererSummary = ((renderer["available"] as? Bool) ?? false) ? "Ready" : "Offline"

            if let newest = goals.first {'''
if refresh_anchor not in text:
    raise SystemExit("v0.16.1 refresh anchor missing")
text = text.replace(refresh_anchor, refresh_new, 1)

send_anchor = '''    func send(_ message: String) async {
'''
answer_method = '''    func answer(_ message: String, quiet: Bool = false) async -> String? {
        let clean = message.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty else { return nil }
        do {
            let object = try await request(
                path: "/vexnative/send",
                method: "POST",
                body: ["agent": "coordinator", "message": clean],
                timeout: 75
            )
            guard (object["ok"] as? Bool) == true else { throw ClientError.badResponse }
            let text = extractText(object["result"]) ?? compactJSON(object["result"]) ?? "VexNative completed the request."
            response = text
            error = ""
            online = true
            return text
        } catch {
            online = false
            if !quiet {
                self.error = "VexNative request: \(error.localizedDescription)"
            }
            return nil
        }
    }

    func send(_ message: String) async {
'''
if send_anchor not in text:
    raise SystemExit("v0.16.1 send anchor missing")
text = text.replace(send_anchor, answer_method, 1)
old_send_body = '''        do {
            let object = try await request(
                path: "/vexnative/send",
                method: "POST",
                body: ["agent": "coordinator", "message": clean],
                timeout: 75
            )
            guard (object["ok"] as? Bool) == true else { throw ClientError.badResponse }
            response = extractText(object["result"]) ?? compactJSON(object["result"]) ?? "VexNative completed the request."
            error = ""
            await refresh()
        } catch {
            self.error = "VexNative request: \(error.localizedDescription)"
        }
'''
new_send_body = '''        if await answer(clean, quiet: false) != nil {
            await refresh()
        }
'''
if old_send_body not in text:
    raise SystemExit("v0.16.1 send body anchor missing")
text = text.replace(old_send_body, new_send_body, 1)

panel_anchor = '''private struct VexNativeA2APanel: View {
    @StateObject private var client = VexNativeA2AClient()
'''
panel_new = '''private struct VexNativeA2APanel: View {
    @StateObject private var client = VexNativeA2AClient.shared
'''
if panel_anchor not in text:
    raise SystemExit("v0.16.1 panel shared-client anchor missing")
text = text.replace(panel_anchor, panel_new, 1)

content_state = '''struct VexChatView: View {
    @EnvironmentObject private var app: AppModel
    @StateObject private var web = WebBrain.shared
'''
content_state_new = '''struct VexChatView: View {
    @EnvironmentObject private var app: AppModel
    @StateObject private var web = WebBrain.shared
    @StateObject private var core = VexNativeA2AClient.shared
'''
if content_state not in text:
    raise SystemExit("v0.16.1 ContentView state anchor missing")
text = text.replace(content_state, content_state_new, 1)

task_anchor = '''        .task {
            // v0.9.4.1 startup-safe mode: onboard GGUF is manual-only.
            voice.onCommand = { command in
'''
task_new = '''        .task {
            await core.refresh()
            // v0.9.4.1 startup-safe mode: onboard GGUF is manual-only.
            voice.onCommand = { command in
'''
if task_anchor not in text:
    raise SystemExit("v0.16.1 startup task anchor missing")
text = text.replace(task_anchor, task_new, 1)
status_anchor = '''            Circle()
                .fill(app.modelStatus.hasPrefix("Loaded") ? Color.green : VexTheme.hotPink)
                .frame(width: 8, height: 8)

            Text(app.modelStatus)
                .font(.caption)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
                .foregroundStyle(VexTheme.muted)
'''
status_new = '''            Circle()
                .fill(core.online ? Color.green : (app.modelStatus.hasPrefix("Loaded") ? Color.green : VexTheme.hotPink))
                .frame(width: 8, height: 8)

            Text(core.online
                 ? "VexNative • \(core.activeNode) • \(core.brainMode) • \(core.activeModel)"
                 : "Offline core • \(app.modelStatus)")
                .font(.caption)
                .lineLimit(1)
                .minimumScaleFactor(0.62)
                .foregroundStyle(VexTheme.muted)
'''
if status_anchor not in text:
    raise SystemExit("v0.16.1 top status anchor missing")
text = text.replace(status_anchor, status_new, 1)

metric_anchor = '''            VStack(alignment: .leading, spacing: 5) {
                Text("Latest goal")
'''
metric_new = '''            HStack(spacing: 12) {
                VexMetricCard(
                    title: "Core",
                    value: client.brainMode,
                    detail: "\(client.activeNode)\n\(client.activeModel)",
                    active: client.online
                )
                VexMetricCard(
                    title: "State",
                    value: client.rendererSummary,
                    detail: "Memory \(client.memorySummary)",
                    active: client.rendererSummary == "Ready"
                )
            }

''' + metric_anchor
if metric_anchor not in text:
    raise SystemExit("v0.16.1 metrics anchor missing")
text = text.replace(metric_anchor, metric_new, 1)
chat_anchor = '''        if await PhoneToolRouter.tryHandle(original, app: self) {
            return
        }

        if await PCArtRouter.tryHandle(original, app: self) {
'''
chat_new = '''        if await PhoneToolRouter.tryHandle(original, app: self) {
            return
        }

        let core = VexNativeA2AClient.shared
        if !core.online {
            await core.refresh()
        }
        if core.online, pendingPhotoData == nil {
            isGenerating = true
            if let answer = await core.answer(original, quiet: true) {
                draft = ""
                profile.messages.append(ChatMessage(role: .user, content: original))
                if let learned = MemoryEngine.learnCandidate(from: original) {
                    profile.memories = MemoryEngine.deduplicatedAppend(learned, to: profile.memories)
                }
                profile.messages.append(ChatMessage(role: .assistant, content: answer))
                persist()
                isGenerating = false
                Task { await core.refresh() }
                return
            }
            isGenerating = false
        }

        if await PCArtRouter.tryHandle(original, app: self) {
'''
if chat_anchor not in text:
    raise SystemExit("v0.16.1 main-chat anchor missing")
text = text.replace(chat_anchor, chat_new, 1)

CONTENT.write_text(text, encoding="utf-8")
final = CONTENT.read_text(encoding="utf-8")
for marker in [
    MARKER,
    "static let shared = VexNativeA2AClient()",
    "func answer(_ message: String, quiet: Bool = false)",
    '@StateObject private var core = VexNativeA2AClient.shared',
    '"VexNative • \\(core.activeNode)',
    "await core.refresh()",
    "if core.online",
    "rendererSummary",
    "memorySummary",
    "V160_A2A_ROAMING_FALLBACK",
]:
    if marker not in final:
        raise SystemExit(f"missing v0.16.1 marker: {marker}")
print("PASS v0.16.1 unified core client patch")
