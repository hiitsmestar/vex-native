#!/usr/bin/env python3
from pathlib import Path

path = Path("VexNative/ContentView.swift")
text = path.read_text(encoding="utf-8")

# Field result after iPhone .51 + upstairs Agent Runtime .80 still showed the
# trusted-memory miss. The iPhone currently races every paired PC for /llm/chat.
# That is useful for ordinary chat latency, but unsafe for continuity-sensitive
# recall while nodes are on different runtime generations: an older secondary can
# answer first and mask the freshly repaired primary. For explicit personal recall,
# keep ownership on the configured primary endpoint. Ordinary chat still races.

old_sync = '''        for endpoint in endpoints where isBridgeEndpoint(endpoint.value) {
            await syncPersonalMetadata(endpoint: endpoint.value, app: app)
            Task { await syncPersonalMemory(endpoint: endpoint.value, app: app) }
        }

        var winner: CognitionAttempt?
        await withTaskGroup(of: CognitionResult.self) { group in
            for endpoint in endpoints {
'''
new_sync = '''        let cognitionEndpoints = isVerifiedPersonalRecallTurn(original)
            ? Array(endpoints.prefix(1))
            : endpoints

        for endpoint in cognitionEndpoints where isBridgeEndpoint(endpoint.value) {
            await syncPersonalMetadata(endpoint: endpoint.value, app: app)
            Task { await syncPersonalMemory(endpoint: endpoint.value, app: app) }
        }

        var winner: CognitionAttempt?
        await withTaskGroup(of: CognitionResult.self) { group in
            for endpoint in cognitionEndpoints {
'''
if old_sync not in text:
    raise SystemExit("v0.11.7.52 cognition endpoint race anchor missing")
text = text.replace(old_sync, new_sync, 1)

# Keep diagnostics consistent with the set actually used for this turn.
text = text.replace(
    'failureSummary(failures, endpointCount: endpoints.count)',
    'failureSummary(failures, endpointCount: cognitionEndpoints.count)',
    1,
)

anchor = '''    private static func isRecallMissExplanationFollowup(_ original: String, app: AppModel) -> Bool {
'''
pos = text.find(anchor)
if pos < 0:
    raise SystemExit("v0.11.7.52 recall guard anchor missing")

helper = r'''    private static func isVerifiedPersonalRecallTurn(_ original: String) -> Bool {
        let lower = original.lowercased()
            .replacingOccurrences(of: "’", with: "'")
            .replacingOccurrences(of: "[^a-z0-9']+", with: " ", options: .regularExpression)
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let broad = [
            "what do you remember about me",
            "what do you know about me",
            "tell me what you remember about me",
            "tell me what you know about me",
            "what have you got saved about me",
            "what have you learned about me"
        ]
        if broad.contains(where: { lower.contains($0) }) { return true }
        return (lower.contains("remember") || lower.contains("memory")) &&
            (lower.contains(" about me") || lower.contains(" my ") || lower.hasSuffix(" my"))
    }

'''
if "private static func isVerifiedPersonalRecallTurn(" not in text:
    text = text[:pos] + helper + text[pos:]

path.write_text(text, encoding="utf-8")

required = [
    "let cognitionEndpoints = isVerifiedPersonalRecallTurn(original)",
    "Array(endpoints.prefix(1))",
    "for endpoint in cognitionEndpoints where isBridgeEndpoint(endpoint.value)",
    "for endpoint in cognitionEndpoints {",
    "private static func isVerifiedPersonalRecallTurn(",
    '"what do you remember about me"',
    "failureSummary(failures, endpointCount: cognitionEndpoints.count)",
    "await syncPersonalMetadata(endpoint: endpoint.value, app: app)",
]
missing = [item for item in required if item not in text]
if missing:
    raise SystemExit("Missing v0.11.7.52 marker(s): " + " | ".join(missing))
print("Applied v0.11.7.52 primary-owner verified recall routing")
