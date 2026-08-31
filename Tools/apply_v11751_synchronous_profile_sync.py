#!/usr/bin/env python3
from pathlib import Path

path = Path("VexNative/ContentView.swift")
text = path.read_text(encoding="utf-8")

# v0.11.1 intentionally moved the full archive backfill into the background so
# conversation stayed responsive. Keep that behavior, but synchronously send the
# compact profile/persona/rules snapshot before each PC cognition request. This
# guarantees the Windows MemoryWorker can materialize core:star:profile before a
# broad recall question reaches /llm/chat -> /facts.
primary_old = '''            Task { await syncPersonalMemory(endpoint: primary, app: app) }
            winner = await requestReply(
'''
primary_new = '''            await syncPersonalMetadata(endpoint: primary, app: app)
            Task { await syncPersonalMemory(endpoint: primary, app: app) }
            winner = await requestReply(
'''
if primary_old in text:
    text = text.replace(primary_old, primary_new, 1)
elif "await syncPersonalMetadata(endpoint: primary, app: app)" not in text:
    raise SystemExit("v0.11.7.51 primary cognition sync anchor missing")

fallback_old = '''                Task { await syncPersonalMemory(endpoint: fallback, app: app) }
                if let candidate = await requestReply(
'''
fallback_new = '''                await syncPersonalMetadata(endpoint: fallback, app: app)
                Task { await syncPersonalMemory(endpoint: fallback, app: app) }
                if let candidate = await requestReply(
'''
if fallback_old in text:
    text = text.replace(fallback_old, fallback_new, 1)
elif "await syncPersonalMetadata(endpoint: fallback, app: app)" not in text:
    raise SystemExit("v0.11.7.51 fallback cognition sync anchor missing")

helper_anchor = '''    private static func syncPersonalMemory(endpoint: String, app: AppModel) async {
'''
helper = r'''    private static func syncPersonalMetadata(endpoint: String, app: AppModel) async {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .secondsSince1970
        guard let encoded = try? encoder.encode(app.profile),
              var profileObject = (try? JSONSerialization.jsonObject(with: encoded)) as? [String: Any]
        else { return }

        // Chat is copied by the existing bounded background backfill. Keep this
        // foreground payload compact enough to safely await on every PC turn.
        profileObject.removeValue(forKey: "messages")
        let payload: [String: Any] = [
            "source": "vexnative-iphone-v0.11.7.51",
            "thread_id": "vexnative-iphone",
            "profile": profileObject
        ]
        _ = await postMemorySync(endpoint: endpoint, payload: payload, timeout: 8)
    }

'''
if helper_anchor in text and "private static func syncPersonalMetadata(endpoint: String, app: AppModel)" not in text:
    text = text.replace(helper_anchor, helper + helper_anchor, 1)
elif "private static func syncPersonalMetadata(endpoint: String, app: AppModel)" not in text:
    raise SystemExit("v0.11.7.51 metadata helper anchor missing")

# A recall miss must not be followed by the raw model inventing a fake memory.
# Catch the immediate explanation follow-up in the PC cognition overlay and give
# a deterministic provenance-safe answer instead.
overlay_marker = "private enum PCCognitionOverlay {"
overlay_pos = text.find(overlay_marker)
if overlay_pos < 0:
    raise SystemExit("PCCognitionOverlay marker missing")
func_anchor = '''    static func tryHandle(_ original: String, app: AppModel) async -> Bool {
        guard shouldUse(original) else { return false }
'''
func_pos = text.find(func_anchor, overlay_pos)
if func_pos < 0:
    if "isRecallMissExplanationFollowup(original, app: app)" not in text:
        raise SystemExit("PCCognitionOverlay tryHandle anchor missing")
else:
    replacement = '''    static func tryHandle(_ original: String, app: AppModel) async -> Bool {
        if isRecallMissExplanationFollowup(original, app: app) {
            app.draft = ""
            app.isGenerating = true
            defer { app.isGenerating = false }
            app.profile.messages.append(ChatMessage(role: .user, content: original))
            app.profile.messages.append(ChatMessage(
                role: .assistant,
                content: "That response means my PC verified-memory lookup returned no trusted fact. The chat alone doesn't distinguish whether the profile sync or the lookup missed, so I'm not going to invent a memory to explain it. 🖤"
            ))
            app.persist()
            return true
        }
        guard shouldUse(original) else { return false }
'''
    text = text[:func_pos] + text[func_pos:].replace(func_anchor, replacement, 1)

should_anchor = '''    private static func shouldUse(_ text: String) -> Bool {
'''
should_pos = text.find(should_anchor, overlay_pos)
followup_helper = r'''    private static func isRecallMissExplanationFollowup(_ original: String, app: AppModel) -> Bool {
        let lower = original.lowercased()
            .replacingOccurrences(of: "’", with: "'")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let explanationShape = lower == "why" || lower == "why?" ||
            lower.contains("why didn't") || lower.contains("why did not") ||
            lower.contains("why not") || lower.contains("what happened") ||
            lower.contains("why couldn't") || lower.contains("why could not")
        guard explanationShape else { return false }

        let previous = app.profile.messages
            .reversed()
            .first(where: { $0.role == .assistant })?
            .content.lowercased() ?? ""
        return previous.contains("verified memory store") &&
            previous.contains("trusted fact") &&
            previous.contains("not going to fill the gap with a guess")
    }

'''
if should_pos >= 0 and "private static func isRecallMissExplanationFollowup(" not in text[overlay_pos:]:
    text = text[:should_pos] + followup_helper + text[should_pos:]
elif "private static func isRecallMissExplanationFollowup(" not in text[overlay_pos:]:
    raise SystemExit("PCCognitionOverlay shouldUse anchor missing")

path.write_text(text, encoding="utf-8")

required = [
    "await syncPersonalMetadata(endpoint: primary, app: app)",
    "await syncPersonalMetadata(endpoint: fallback, app: app)",
    "private static func syncPersonalMetadata(endpoint: String, app: AppModel) async",
    '"source": "vexnative-iphone-v0.11.7.51"',
    "isRecallMissExplanationFollowup(original, app: app)",
    "verified-memory lookup returned no trusted fact",
    "Task { await syncPersonalMemory(endpoint: primary, app: app) }",
]
missing = [m for m in required if m not in text]
if missing:
    raise SystemExit("Missing v0.11.7.51 marker(s): " + ", ".join(missing))
print("Applied v0.11.7.51 synchronous profile sync + recall-miss hallucination guard")
