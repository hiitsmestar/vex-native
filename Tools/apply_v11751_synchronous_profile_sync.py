#!/usr/bin/env python3
from pathlib import Path

path = Path("VexNative/ContentView.swift")
text = path.read_text(encoding="utf-8")

# v0.11.1 moved the large archive backfill into a delayed background task.
# v0.11.7.48 then changed PC cognition from serial primary/fallback requests to a
# concurrent endpoint race. Repair the actual raced-endpoint loop: every private
# Bridge receives the compact profile snapshot before any /llm/chat task starts,
# while the potentially large chat archive remains asynchronous.
race_old = '''        for endpoint in endpoints where isBridgeEndpoint(endpoint.value) {
            Task { await syncPersonalMemory(endpoint: endpoint.value, app: app) }
        }

        var winner: CognitionAttempt?
        await withTaskGroup(of: CognitionResult.self) { group in
'''
race_new = '''        for endpoint in endpoints where isBridgeEndpoint(endpoint.value) {
            await syncPersonalMetadata(endpoint: endpoint.value, app: app)
            Task { await syncPersonalMemory(endpoint: endpoint.value, app: app) }
        }

        var winner: CognitionAttempt?
        await withTaskGroup(of: CognitionResult.self) { group in
'''
if "await syncPersonalMetadata(endpoint: endpoint.value, app: app)" not in text:
    if race_old not in text:
        raise SystemExit("v0.11.7.51 raced cognition sync anchor missing")
    text = text.replace(race_old, race_new, 1)

helper_anchor = '''    private static func syncPersonalMemory(endpoint: String, app: AppModel) async {
'''
helper = r'''    private static func syncPersonalMetadata(endpoint: String, app: AppModel) async {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .secondsSince1970
        guard let encoded = try? encoder.encode(app.profile),
              var profileObject = (try? JSONSerialization.jsonObject(with: encoded)) as? [String: Any]
        else { return }

        // Raw chat is copied by the existing bounded background backfill. Keep this
        // foreground payload compact enough to await before every PC cognition race.
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

# A verified-memory miss followed by "why?" must never escape to the raw model,
# which can manufacture autobiographical details. Insert this deterministic guard
# immediately after PCCognitionOverlay.tryHandle's declaration.
overlay_marker = "private enum PCCognitionOverlay {"
overlay_pos = text.find(overlay_marker)
if overlay_pos < 0:
    raise SystemExit("PCCognitionOverlay marker missing")

decl = "    static func tryHandle(_ original: String, app: AppModel) async -> Bool {\n"
decl_pos = text.find(decl, overlay_pos)
if decl_pos < 0:
    raise SystemExit("PCCognitionOverlay tryHandle declaration missing")
if "isRecallMissExplanationFollowup(original, app: app)" not in text[decl_pos:decl_pos + 2200]:
    guard_block = '''        if isRecallMissExplanationFollowup(original, app: app) {
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
'''
    insert_at = decl_pos + len(decl)
    text = text[:insert_at] + guard_block + text[insert_at:]

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
    "await syncPersonalMetadata(endpoint: endpoint.value, app: app)",
    "private static func syncPersonalMetadata(endpoint: String, app: AppModel) async",
    '"source": "vexnative-iphone-v0.11.7.51"',
    "isRecallMissExplanationFollowup(original, app: app)",
    "verified-memory lookup returned no trusted fact",
    "Task { await syncPersonalMemory(endpoint: endpoint.value, app: app) }",
    "await withTaskGroup(of: CognitionResult.self)",
]
missing = [m for m in required if m not in text]
if missing:
    raise SystemExit("Missing v0.11.7.51 marker(s): " + ", ".join(missing))
print("Applied v0.11.7.51 synchronous profile sync + recall-miss hallucination guard")
