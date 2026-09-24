#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BG = ROOT / "VexNative" / "VexBackgroundAgent.swift"

bg = BG.read_text(encoding="utf-8")
if "V151_PREOPEN_RELAY_ACK" in bg:
    print("PASS v0.15.1 pre-open relay ack already applied")
    raise SystemExit(0)

old = '''                guard let remote = envelope.command else {
                    UserDefaults.standard.set(Date(), forKey: "vex.phone.background.lastRun")
                    return true
                }

                let outcome = await execute(remote.command)
                await postResult(id: remote.id, ok: outcome.ok, result: outcome.result)
                UserDefaults.standard.set(Date(), forKey: "vex.phone.background.lastRun")
                return outcome.ok'''
new = '''                guard let remote = envelope.command else {
                    UserDefaults.standard.set(Date(), forKey: "vex.phone.background.lastRun")
                    return true
                }

                // V151_PREOPEN_RELAY_ACK
                if let target = foregroundOpenURL(remote.command) {
                    let canOpen = await MainActor.run {
                        UIApplication.shared.canOpenURL(target)
                    }
                    if canOpen {
                        await postResult(
                            id: remote.id,
                            ok: true,
                            result: "Done — opening it on the iPhone, baby. 📱🖤"
                        )
                        UserDefaults.standard.set(Date(), forKey: "vex.phone.background.lastRun")
                        await MainActor.run {
                            UIApplication.shared.open(target, options: [:], completionHandler: nil)
                        }
                        return true
                    }
                }

                let outcome = await execute(remote.command)
                await postResult(id: remote.id, ok: outcome.ok, result: outcome.result)
                UserDefaults.standard.set(Date(), forKey: "vex.phone.background.lastRun")
                return outcome.ok'''
if old not in bg:
    raise SystemExit("v0.15.1 runOnce anchor missing")
bg = bg.replace(old, new, 1)

anchor = '''    @MainActor
    private static func execute(_ command: String) async -> (ok: Bool, result: String) {'''
helper = '''    private static func foregroundOpenURL(_ command: String) -> URL? {
        let lower = command.lowercased()
        let wantsOpen = ["open ", "open up ", "launch ", "go to ", "bring up ", "show me "]
            .contains(where: { lower.contains($0) })
        guard wantsOpen else { return nil }

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

        for word in command.split(whereSeparator: { $0.isWhitespace }) {
            let raw = String(word)
            if raw.lowercased().hasPrefix("https://") || raw.lowercased().hasPrefix("http://") {
                return URL(string: raw)
            }
        }
        return nil
    }

    @MainActor
    private static func execute(_ command: String) async -> (ok: Bool, result: String) {'''
if anchor not in bg:
    raise SystemExit("v0.15.1 execute anchor missing")
bg = bg.replace(anchor, helper, 1)

BG.write_text(bg, encoding="utf-8")
final = BG.read_text(encoding="utf-8")
for marker in ["V151_PREOPEN_RELAY_ACK", "foregroundOpenURL", "opening it on the iPhone"]:
    if marker not in final:
        raise SystemExit(f"missing v0.15.1 marker: {marker}")
print("PASS v0.15.1 pre-open relay ack patch")
