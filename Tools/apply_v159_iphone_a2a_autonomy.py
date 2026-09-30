#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "VexNative" / "ContentView.swift"
MARKER = 'V159_IPHONE_A2A_AUTONOMY = "v0.15.9-iphone-a2a-autonomy-v1"'

text = CONTENT.read_text(encoding="utf-8")
if MARKER in text:
    print("PASS v0.15.9 iPhone A2A autonomy already applied")
    raise SystemExit(0)

anchor = 'private let V158_IPHONE_A2A_CLIENT = "v0.15.8-iphone-a2a-client-v1"'
if anchor not in text:
    raise SystemExit("v0.15.9 requires v0.15.8 A2A client")
text = text.replace(anchor, anchor + '\nprivate let ' + MARKER, 1)

send_anchor = '''    func send(_ message: String) async {
        let clean = message.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty, !sending else { return }
        sending = true
        defer { sending = false }

        do {
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
    }
'''
if send_anchor not in text:
    raise SystemExit("v0.15.9 send method anchor missing")

methods = send_anchor + '''
    func setAutonomy(enabled: Bool) async {
        do {
            let object = try await request(
                path: "/vexnative/autonomy",
                method: "POST",
                body: ["action": enabled ? "enable" : "pause"],
                timeout: 20
            )
            guard (object["ok"] as? Bool) == true else { throw ClientError.badResponse }
            response = enabled ? "VexNative autonomy resumed." : "VexNative autonomy paused."
            error = ""
            await refresh()
        } catch {
            self.error = "Autonomy control: \(error.localizedDescription)"
        }
    }

    func createGoal(_ title: String) async {
        let clean = title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty else { return }
        do {
            let object = try await request(
                path: "/vexnative/autonomy",
                method: "POST",
                body: [
                    "action": "create_goal",
                    "title": clean,
                    "description": clean,
                    "priority": 50
                ],
                timeout: 20
            )
            guard (object["ok"] as? Bool) == true else { throw ClientError.badResponse }
            response = "Goal accepted by VexNative."
            error = ""
            await refresh()
        } catch {
            self.error = "Goal submission: \(error.localizedDescription)"
        }
    }
'''
text = text.replace(send_anchor, methods, 1)

view_state = '''private struct VexNativeA2APanel: View {
    @StateObject private var client = VexNativeA2AClient()
    @State private var prompt = ""'''
view_state_new = '''private struct VexNativeA2APanel: View {
    @StateObject private var client = VexNativeA2AClient()
    @State private var prompt = ""
    @State private var goalDraft = ""'''
if view_state not in text:
    raise SystemExit("v0.15.9 panel state anchor missing")
text = text.replace(view_state, view_state_new, 1)

latest_anchor = '''            VStack(alignment: .leading, spacing: 5) {
                Text("Latest goal")
                    .font(.caption.bold())
                    .foregroundStyle(VexTheme.hotPink)
                Text(client.latestGoal)
                    .font(.subheadline)
                    .foregroundStyle(.white.opacity(0.94))
            }
'''
controls = latest_anchor + '''
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Button {
                        Task { await client.setAutonomy(enabled: true) }
                    } label: {
                        Label("Resume", systemImage: "play.fill")
                    }
                    .buttonStyle(.bordered)
                    .disabled(!client.online || client.autonomyEnabled)

                    Button {
                        Task { await client.setAutonomy(enabled: false) }
                    } label: {
                        Label("Pause", systemImage: "pause.fill")
                    }
                    .buttonStyle(.bordered)
                    .disabled(!client.online || !client.autonomyEnabled)
                }

                TextField("Give VexNative a new goal", text: $goalDraft, axis: .vertical)
                    .textFieldStyle(.roundedBorder)

                Button {
                    let goal = goalDraft
                    goalDraft = ""
                    Task { await client.createGoal(goal) }
                } label: {
                    Label("Send goal", systemImage: "target")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .tint(VexTheme.hotPink)
                .disabled(!client.online || goalDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
'''
if latest_anchor not in text:
    raise SystemExit("v0.15.9 latest-goal anchor missing")
text = text.replace(latest_anchor, controls, 1)

CONTENT.write_text(text, encoding="utf-8")

final = CONTENT.read_text(encoding="utf-8")
for marker in [
    MARKER,
    'path: "/vexnative/autonomy"',
    '"action": "create_goal"',
    "setAutonomy(enabled:",
    "createGoal(_ title:",
    'TextField("Give VexNative a new goal"',
    'Label("Resume", systemImage: "play.fill")',
    'Label("Pause", systemImage: "pause.fill")',
    'V158_IPHONE_A2A_CLIENT',
]:
    if marker not in final:
        raise SystemExit(f"missing v0.15.9 marker: {marker}")

print("PASS v0.15.9 iPhone A2A autonomy patch")
