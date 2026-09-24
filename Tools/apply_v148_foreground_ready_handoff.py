#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOICE = ROOT / "VexNative" / "VexVoiceIntents.swift"
BG = ROOT / "VexNative" / "VexBackgroundAgent.swift"

voice = VOICE.read_text(encoding="utf-8")
if "V148_FOREGROUND_READY_HANDOFF" in voice:
    print("PASS v0.14.8 foreground-ready handoff already applied")
    raise SystemExit(0)

old = '''        if wake == "wake and check remote relay" {
            _ = await VexPhoneBackgroundWorker.runOnce()
            return .result(dialog: "Ready.")
        }'''
new = '''        if wake == "wake and check remote relay" {
            // V148_FOREGROUND_READY_HANDOFF
            UserDefaults.standard.set(true, forKey: "vex.phone.foregroundWake.pending")
            return .result(dialog: "Ready.")
        }'''
if old not in voice:
    raise SystemExit("v0.14.8 wake-intent anchor missing")
voice = voice.replace(old, new, 1)
VOICE.write_text(voice, encoding="utf-8")

bg = BG.read_text(encoding="utf-8")
anchor = '''    func applicationWillEnterForeground(_ application: UIApplication) {
        VexBackgroundAgent.shared.endBackgroundGrace(using: application)
        VexBackgroundAgent.shared.startPersistentAgent()
        VexBackgroundAgent.shared.schedule()
    }'''
replacement = anchor + '''

    func applicationDidBecomeActive(_ application: UIApplication) {
        let defaults = UserDefaults.standard
        guard defaults.bool(forKey: "vex.phone.foregroundWake.pending") else { return }
        defaults.set(false, forKey: "vex.phone.foregroundWake.pending")

        Task { @MainActor in
            try? await Task.sleep(nanoseconds: 750_000_000)
            _ = await VexPhoneBackgroundWorker.runOnce()
        }
    }'''
if anchor not in bg:
    raise SystemExit("v0.14.8 foreground lifecycle anchor missing")
bg = bg.replace(anchor, replacement, 1)
BG.write_text(bg, encoding="utf-8")

final_voice = VOICE.read_text(encoding="utf-8")
final_bg = BG.read_text(encoding="utf-8")
for marker in [
    "V148_FOREGROUND_READY_HANDOFF",
    'vex.phone.foregroundWake.pending',
]:
    if marker not in final_voice:
        raise SystemExit(f"missing v0.14.8 voice marker: {marker}")
for marker in [
    "applicationDidBecomeActive",
    'vex.phone.foregroundWake.pending',
    "750_000_000",
    "VexPhoneBackgroundWorker.runOnce()",
]:
    if marker not in final_bg:
        raise SystemExit(f"missing v0.14.8 lifecycle marker: {marker}")

print("PASS v0.14.8 foreground-ready handoff patch")
