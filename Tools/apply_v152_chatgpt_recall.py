#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BG = ROOT / "VexNative" / "VexBackgroundAgent.swift"
VOICE = ROOT / "Tools" / "VexVoiceIntents.swift"

bg = BG.read_text(encoding="utf-8")
if "V152_CHATGPT_RECALL" not in bg:
    anchor = '''                // V151_PREOPEN_RELAY_ACK
                if let target = foregroundOpenURL(remote.command) {'''
    replacement = '''                // V152_CHATGPT_RECALL
                if remote.command.lowercased().contains("vexrecall60") {
                    await MainActor.run {
                        UIPasteboard.general.string = "VEXRECALL60"
                    }
                }

                // V151_PREOPEN_RELAY_ACK
                if let target = foregroundOpenURL(remote.command) {'''
    if anchor not in bg:
        raise SystemExit("v0.15.2 runOnce anchor missing")
    bg = bg.replace(anchor, replacement, 1)

    guard_anchor = '''        guard wantsOpen else { return nil }

        let known: [(String, String)] = ['''
    guard_replacement = '''        if lower.contains("vexrecall60") {
            return URL(string: "https://chatgpt.com/?prompt=VEXRECALL60")
        }

        guard wantsOpen else { return nil }

        let known: [(String, String)] = ['''
    if guard_anchor not in bg:
        raise SystemExit("v0.15.2 foregroundOpenURL anchor missing")
    bg = bg.replace(guard_anchor, guard_replacement, 1)

    maps_anchor = '''            ("github", "https://github.com"),
            ("maps", "https://maps.apple.com")'''
    maps_replacement = '''            ("github", "https://github.com"),
            ("chatgpt", "https://chatgpt.com"),
            ("maps", "https://maps.apple.com")'''
    if maps_anchor not in bg:
        raise SystemExit("v0.15.2 background knownURL anchor missing")
    bg = bg.replace(maps_anchor, maps_replacement, 1)
    BG.write_text(bg, encoding="utf-8")

voice = VOICE.read_text(encoding="utf-8")
if "case openChatGPT" not in voice:
    voice = voice.replace(
        '''    case openGmail
    case openSpotify''',
        '''    case openGmail
    case openChatGPT
    case openSpotify''',
        1,
    )
    voice = voice.replace(
        '''        .openGmail: "open Gmail",
        .openSpotify: "open Spotify",''',
        '''        .openGmail: "open Gmail",
        .openChatGPT: "open ChatGPT",
        .openSpotify: "open Spotify",''',
        1,
    )
    voice = voice.replace(
        '''        case .openGmail: return "open Gmail on my phone"
        case .openSpotify: return "open Spotify on my phone"''',
        '''        case .openGmail: return "open Gmail on my phone"
        case .openChatGPT: return "open ChatGPT on my phone"
        case .openSpotify: return "open Spotify on my phone"''',
        1,
    )
    voice = voice.replace(
        '''            ("gmail", "https://mail.google.com"),
            ("spotify", "https://open.spotify.com"),''',
        '''            ("gmail", "https://mail.google.com"),
            ("chatgpt", "https://chatgpt.com"),
            ("spotify", "https://open.spotify.com"),''',
        1,
    )
    VOICE.write_text(voice, encoding="utf-8")

bg = BG.read_text(encoding="utf-8")
voice = VOICE.read_text(encoding="utf-8")
for marker in ["V152_CHATGPT_RECALL", "VEXRECALL60", "chatgpt.com"]:
    if marker not in bg:
        raise SystemExit(f"missing v0.15.2 background marker: {marker}")
for marker in ["case openChatGPT", "open ChatGPT", "chatgpt.com"]:
    if marker not in voice:
        raise SystemExit(f"missing v0.15.2 voice marker: {marker}")
print("PASS v0.15.2 ChatGPT recall patch")
