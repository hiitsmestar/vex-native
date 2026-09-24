#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BG = ROOT / "VexNative" / "VexBackgroundAgent.swift"

text = BG.read_text(encoding="utf-8")
if "V148_ACTIVE_FOREGROUND_COMMAND_GATE" in text:
    print("PASS v0.14.8 active foreground command gate already applied")
    raise SystemExit(0)

anchor = '''            guard envelope.ok else { return false }
            guard let remote = envelope.command else { return true }

            let outcome = await execute(remote.command)'''
replacement = '''            guard envelope.ok else { return false }
            guard let remote = envelope.command else { return true }

            // V148_ACTIVE_FOREGROUND_COMMAND_GATE
            if requiresForeground(remote.command) {
                let deadline = Date().addingTimeInterval(20)
                while Date() < deadline {
                    if await applicationIsActive() { break }
                    try? await Task.sleep(nanoseconds: 250_000_000)
                }
                guard await applicationIsActive() else {
                    await postResult(
                        id: remote.id,
                        ok: false,
                        result: "Foreground activation timed out."
                    )
                    return false
                }
                // Give UIKit a brief moment to finish scene activation before opening another app.
                try? await Task.sleep(nanoseconds: 500_000_000)
            }

            let outcome = await execute(remote.command)'''
if anchor not in text:
    raise SystemExit("v0.14.8 runOnce anchor missing")
text = text.replace(anchor, replacement, 1)

anchor = '''    private static func phoneTargeted(_ command: String) -> String {'''
insert = '''    private static func applicationIsActive() async -> Bool {
        await MainActor.run {
            UIApplication.shared.applicationState == .active
        }
    }

    private static func requiresForeground(_ command: String) -> Bool {
        let lower = command.lowercased()
        let markers = [
            "open ", "launch ", "play ", "show ", "search ",
            "navigate ", "go to ", "youtube", "safari", "browser",
            "maps", "music", "spotify", "tiktok", "netflix",
            "camera", "photos"
        ]
        return markers.contains(where: { lower.contains($0) })
    }

    private static func phoneTargeted(_ command: String) -> String {'''
if anchor not in text:
    raise SystemExit("v0.14.8 phoneTargeted anchor missing")
text = text.replace(anchor, insert, 1)

BG.write_text(text, encoding="utf-8")

final = BG.read_text(encoding="utf-8")
for marker in [
    "V148_ACTIVE_FOREGROUND_COMMAND_GATE",
    "requiresForeground(remote.command)",
    "UIApplication.shared.applicationState == .active",
    "Foreground activation timed out.",
    "try? await Task.sleep(nanoseconds: 500_000_000)",
]:
    if marker not in final:
        raise SystemExit(f"missing v0.14.8 marker: {marker}")

print("PASS v0.14.8 active foreground command gate patch")
