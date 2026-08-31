#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

CONTENT = Path("VexNative/ContentView.swift")
text = CONTENT.read_text(encoding="utf-8")

old = '''        // Let the remaining native/web fallback routes handle the turn. They expect
        // the original text to still be in draft, so restore it only on total PC
        // cognition failure.
        app.draft = original
        app.pcBrainConnected = false
        app.pcBrainStatus = "PC cognition unavailable • \\(failureSummary(failures, endpointCount: endpoints.count))"
        return false
'''
new = '''        // v0.11.7.50: once an ordinary chat turn is owned by PC cognition, a total
        // Bridge failure must not fall through into the parked onboard model. That
        // fallback produced unrelated generic prose during field testing. Preserve
        // the diagnostic reason and answer explicitly instead of pretending.
        let failureReason = failureSummary(failures, endpointCount: endpoints.count)
        app.pcBrainConnected = false
        app.pcBrainStatus = "PC cognition unavailable • \\(failureReason)"
        app.profile.messages.append(ChatMessage(role: .user, content: original))
        app.profile.messages.append(ChatMessage(
            role: .assistant,
            content: "Baby, the PC brain didn't answer that turn (\\(failureReason)), so I'm not going to fake it with the parked phone model. Try me again in a sec. 🖤"
        ))
        app.persist()
        return true
'''

if old not in text:
    raise SystemExit("v0.11.7.50 PC cognition failure anchor missing")
text = text.replace(old, new, 1)
CONTENT.write_text(text, encoding="utf-8")

checks = [
    ("owned failure", "let failureReason = failureSummary" in text and "return true" in text),
    ("no fallback restore", "app.draft = original\n        app.pcBrainConnected = false" not in text),
    ("explicit parked-model guard", "not going to fake it with the parked phone model" in text),
    ("preserves diagnostics", 'app.pcBrainStatus = "PC cognition unavailable • \\(failureReason)"' in text),
    ("preserves endpoint race", "await withTaskGroup(of: CognitionResult.self)" in text),
    ("preserves timeout recovery", "request.timeoutInterval = 125" in text),
]
missing = [name for name, ok in checks if not ok]
if missing:
    raise SystemExit("v0.11.7.50 verifier failed: " + ", ".join(missing))
print("Applied VexNative v0.11.7.50 PC cognition owned-fallback guard")
