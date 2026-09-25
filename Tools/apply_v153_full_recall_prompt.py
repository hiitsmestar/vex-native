#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BG = ROOT / "VexNative" / "VexBackgroundAgent.swift"

bg = BG.read_text(encoding="utf-8")
old_clip = '''                // V152_CHATGPT_RECALL
                if remote.command.lowercased().contains("vexrecall60") {
                    await MainActor.run {
                        UIPasteboard.general.string = "VEXRECALL60"
                    }
                }'''
new_clip = '''                // V153_FULL_RECALL_PROMPT
                if remote.command.lowercased().contains("vexrecall60") {
                    await MainActor.run {
                        UIPasteboard.general.string = remote.command
                    }
                }'''
if old_clip not in bg:
    raise SystemExit("v0.15.3 clipboard anchor missing")
bg = bg.replace(old_clip, new_clip, 1)

old_url = '''        if lower.contains("vexrecall60") {
            return URL(string: "https://chatgpt.com/?prompt=VEXRECALL60")
        }'''
new_url = '''        if lower.contains("vexrecall60") {
            var components = URLComponents(string: "https://chatgpt.com/")!
            components.queryItems = [URLQueryItem(name: "prompt", value: command)]
            return components.url
        }'''
if old_url not in bg:
    raise SystemExit("v0.15.3 recall URL anchor missing")
bg = bg.replace(old_url, new_url, 1)

BG.write_text(bg, encoding="utf-8")

check = BG.read_text(encoding="utf-8")
for marker in ["V153_FULL_RECALL_PROMPT", "UIPasteboard.general.string = remote.command", 'URLQueryItem(name: "prompt", value: command)']:
    if marker not in check:
        raise SystemExit(f"missing v0.15.3 marker: {marker}")
print("PASS v0.15.3 full recall prompt patch")
