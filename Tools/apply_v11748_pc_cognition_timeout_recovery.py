#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


CONTENT = Path("VexNative/ContentView.swift")
APP = Path("VexNative/VexNativeApp.swift")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"v0.11.7.48 missing anchor: {label}")
    return text.replace(old, new, 1)


content = CONTENT.read_text(encoding="utf-8")
app = APP.read_text(encoding="utf-8")

content = replace_once(
    content,
    '''        let history = app.profile.messages.suffix(28).map { message -> [String: String] in
            ["role": message.role.rawValue, "content": String(message.content.prefix(5000))]
        }

        let personaContext = String(app.profile.persona.prefix(6000))
        let userProfileContext = String(app.profile.userProfile.prefix(3500))
''',
    '''        // v0.11.7.48: keep the PC turn lean enough for cold CPU Ollama starts.
        // The Bridge already owns long-term memory sync; the chat request only needs
        // recent local conversational shape plus compact current profile grounding.
        let history = app.profile.messages.suffix(12).map { message -> [String: String] in
            ["role": message.role.rawValue, "content": String(message.content.prefix(2800))]
        }

        let personaContext = String(app.profile.persona.prefix(3600))
        let userProfileContext = String(app.profile.userProfile.prefix(1800))
''',
    "compact PC cognition payload",
)

old_serial = '''        // v0.9.5 Resource Director: the first configured Bridge is the foreground
        // primary node. Utility nodes retain every tool permission, but they only
        // receive interactive cognition when primary fails.
        var winner: CognitionAttempt?
        if let primary = endpoints.first {
            if isBridgeEndpoint(primary.value) {
                Task { await syncPersonalMemory(endpoint: primary.value, app: app) }
            }
            let result = await requestReply(
                endpoint: primary,
                original: original,
                history: history,
                persona: personaContext,
                userProfile: userProfileContext,
                state: stateContext
            )
            winner = record(result)
        } else {
            winner = nil
        }

        if winner == nil {
            for fallback in endpoints.dropFirst() {
                if isBridgeEndpoint(fallback.value) {
                    Task { await syncPersonalMemory(endpoint: fallback.value, app: app) }
                }
                let result = await requestReply(
                    endpoint: fallback,
                    original: original,
                    history: history,
                    persona: personaContext,
                    userProfile: userProfileContext,
                    state: stateContext
                )
                if let candidate = record(result) {
                    winner = candidate
                    break
                }
            }
        }
'''
new_race = '''        // v0.11.7.48: race paired Bridge endpoints for cognition. A stale primary
        // should not make Star wait through a full /llm/chat timeout before the
        // second or last-good PC gets a chance to answer.
        for endpoint in endpoints where isBridgeEndpoint(endpoint.value) {
            Task { await syncPersonalMemory(endpoint: endpoint.value, app: app) }
        }

        var winner: CognitionAttempt?
        await withTaskGroup(of: CognitionResult.self) { group in
            for endpoint in endpoints {
                group.addTask {
                    await requestReply(
                        endpoint: endpoint,
                        original: original,
                        history: history,
                        persona: personaContext,
                        userProfile: userProfileContext,
                        state: stateContext
                    )
                }
            }

            while let result = await group.next() {
                if let candidate = record(result) {
                    winner = candidate
                    group.cancelAll()
                    break
                }
            }
        }
'''
content = replace_once(content, old_serial, new_race, "serial PC cognition endpoint loop")

content = replace_once(
    content,
    '''            "message": String(original.prefix(5000)),
''',
    '''            "message": String(original.prefix(3500)),
''',
    "PC cognition message prefix",
)
content = replace_once(
    content,
    "        request.timeoutInterval = 90\n",
    "        request.timeoutInterval = 125\n",
    "PC cognition request timeout",
)

app = replace_once(
    app,
    '''        if path == "/llm/chat" {
            configuration.timeoutIntervalForRequest = 95
            configuration.timeoutIntervalForResource = 100
''',
    '''        if path == "/llm/chat" {
            configuration.timeoutIntervalForRequest = 130
            configuration.timeoutIntervalForResource = 145
''',
    "Bridge /llm/chat transport timeout",
)

CONTENT.write_text(content, encoding="utf-8")
APP.write_text(app, encoding="utf-8")

checks = [
    ("endpoint race", "await withTaskGroup(of: CognitionResult.self)" in content and "group.cancelAll()" in content),
    ("compact history", "profile.messages.suffix(12)" in content and "prefix(2800)" in content),
    ("compact profile", "persona.prefix(3600)" in content and "userProfile.prefix(1800)" in content),
    ("message trim", "String(original.prefix(3500))" in content),
    ("request timeout", "request.timeoutInterval = 125" in content),
    ("transport timeout", "configuration.timeoutIntervalForRequest = 130" in app and "configuration.timeoutIntervalForResource = 145" in app),
]
missing = [name for name, ok in checks if not ok]
if missing:
    raise SystemExit("v0.11.7.48 verifier failed: " + ", ".join(missing))

print("Applied VexNative v0.11.7.48 PC cognition timeout recovery")
