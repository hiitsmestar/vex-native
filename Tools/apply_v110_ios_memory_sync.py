#!/usr/bin/env python3
from pathlib import Path

path = Path("VexNative/ContentView.swift")
text = path.read_text(encoding="utf-8")

# v0.11 sends the existing native BrainProfile + full local chat history to the
# selected PC's authenticated Bridge. The transfer is incremental and best-effort:
# memory being offline must never stop ordinary conversation.
old_primary = '''            winner = await requestReply(
                endpoint: primary,
                original: original,
                history: history,
                persona: personaContext,
                userProfile: userProfileContext,
                state: stateContext
            )
'''
new_primary = '''            await syncPersonalMemory(endpoint: primary, app: app)
            winner = await requestReply(
                endpoint: primary,
                original: original,
                history: history,
                persona: personaContext,
                userProfile: userProfileContext,
                state: stateContext
            )
'''
if old_primary in text:
    text = text.replace(old_primary, new_primary, 1)
elif "await syncPersonalMemory(endpoint: primary, app: app)" not in text:
    raise SystemExit("v0.11 primary memory sync anchor missing")

old_fallback = '''                if let candidate = await requestReply(
                    endpoint: fallback,
                    original: original,
                    history: history,
                    persona: personaContext,
                    userProfile: userProfileContext,
                    state: stateContext
                ) {
'''
new_fallback = '''                await syncPersonalMemory(endpoint: fallback, app: app)
                if let candidate = await requestReply(
                    endpoint: fallback,
                    original: original,
                    history: history,
                    persona: personaContext,
                    userProfile: userProfileContext,
                    state: stateContext
                ) {
'''
if old_fallback in text:
    text = text.replace(old_fallback, new_fallback, 1)
elif "await syncPersonalMemory(endpoint: fallback, app: app)" not in text:
    raise SystemExit("v0.11 fallback memory sync anchor missing")

marker = '''    private static func shouldUse(_ text: String) -> Bool {
'''
helper = r'''    private static let memorySyncCountPrefix = "vex.pc.memory.syncCount.v1."
    private static let memoryMetadataAtPrefix = "vex.pc.memory.metadataAt.v1."

    private static func memoryEndpointKey(_ endpoint: String) -> String {
        Data(endpoint.utf8).base64EncodedString()
    }

    private static func postMemorySync(endpoint: String, payload: [String: Any], timeout: TimeInterval) async -> Bool {
        guard let url = endpointURL(endpoint, path: "/memory/sync") else { return false }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = timeout
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        guard let body = try? JSONSerialization.data(withJSONObject: payload) else { return false }
        request.httpBody = body
        do {
            let (_, response) = try await VexBridgeNetworking.data(for: request)
            guard let http = response as? HTTPURLResponse else { return false }
            return (200...299).contains(http.statusCode)
        } catch {
            return false
        }
    }

    private static func syncPersonalMemory(endpoint: String, app: AppModel) async {
        let key = memoryEndpointKey(endpoint)
        let defaults = UserDefaults.standard

        // Refresh persona/profile/rules/current state periodically. Use Codable so
        // new BrainProfile fields automatically join the memory snapshot later.
        let metadataKey = memoryMetadataAtPrefix + key
        let lastMetadataAt = defaults.double(forKey: metadataKey)
        if lastMetadataAt <= 0 || Date().timeIntervalSince1970 - lastMetadataAt > 600 {
            let encoder = JSONEncoder()
            encoder.dateEncodingStrategy = .secondsSince1970
            if let encoded = try? encoder.encode(app.profile),
               var profileObject = (try? JSONSerialization.jsonObject(with: encoded)) as? [String: Any] {
                // Raw chat history is sent separately in bounded incremental batches.
                profileObject.removeValue(forKey: "messages")
                let payload: [String: Any] = [
                    "source": "vexnative-iphone-v0.11",
                    "thread_id": "vexnative-iphone",
                    "profile": profileObject
                ]
                if await postMemorySync(endpoint: endpoint, payload: payload, timeout: 8) {
                    defaults.set(Date().timeIntervalSince1970, forKey: metadataKey)
                }
            }
        }

        // Copy the complete native chat archive once, then only the new suffix.
        // Count is kept per paired Bridge because each PC owns its own local DB.
        let countKey = memorySyncCountPrefix + key
        let messages = app.profile.messages
        var synced = defaults.integer(forKey: countKey)
        if synced < 0 || synced > messages.count { synced = 0 }
        guard synced < messages.count else { return }

        let batchSize = 100
        while synced < messages.count {
            let end = min(messages.count, synced + batchSize)
            let batch = (synced..<end).map { index -> [String: Any] in
                let message = messages[index]
                return [
                    "id": message.id.uuidString,
                    "ordinal": index,
                    "role": message.role.rawValue,
                    "content": String(message.content.prefix(50000)),
                    "created_at": message.createdAt.timeIntervalSince1970
                ]
            }
            let payload: [String: Any] = [
                "source": "vexnative-iphone-v0.11",
                "thread_id": "vexnative-iphone",
                "start_ordinal": synced,
                "messages": batch
            ]
            guard await postMemorySync(endpoint: endpoint, payload: payload, timeout: 12) else {
                // Older Bridge or temporarily unavailable memory worker: cognition
                // continues normally and the same batch is retried next PC turn.
                return
            }
            synced = end
            defaults.set(synced, forKey: countKey)
        }
    }

'''
if marker in text and "private static func syncPersonalMemory(endpoint: String, app: AppModel)" not in text:
    text = text.replace(marker, helper + marker, 1)
elif "private static func syncPersonalMemory(endpoint: String, app: AppModel)" not in text:
    raise SystemExit("v0.11 memory sync helper insertion marker missing")

path.write_text(text, encoding="utf-8")
for required in [
    "await syncPersonalMemory(endpoint: primary, app: app)",
    "await syncPersonalMemory(endpoint: fallback, app: app)",
    'path: "/memory/sync"',
    "profileObject.removeValue(forKey: \"messages\")",
    '"thread_id": "vexnative-iphone"',
    "message.createdAt.timeIntervalSince1970",
    "memorySyncCountPrefix",
]:
    if required not in text:
        raise SystemExit(f"missing v0.11 iOS memory marker: {required}")
print("Applied v0.11 iPhone full-history personal memory sync")
