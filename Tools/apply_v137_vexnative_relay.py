#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "VexNative" / "ContentView.swift"
MARKER = 'V137_VEXNATIVE_RELAY = "v0.13.7-vexnative-relay-v1"'

text = CONTENT.read_text(encoding="utf-8")
if MARKER not in text:
    anchor = 'private let V136_VEXNATIVE_LINK = "v0.13.6-vexnative-link-v1"'
    if anchor not in text:
        raise SystemExit("v0.13.7 v0.13.6 marker missing")
    text = text.replace(anchor, anchor + '\nprivate let ' + MARKER, 1)

    old = '''        parts.path = path
        guard let url = parts.url else { return nil }'''
    new = '''        parts.path = path
        if path.hasPrefix("/vexnative/") {
            parts.port = 8771
        }
        guard let url = parts.url else { return nil }'''
    if old not in text:
        raise SystemExit("v0.13.7 JSON route anchor missing")
    text = text.replace(old, new, 1)

    old2 = '''            if let native = await json(endpoint: endpoint, path: "/vexnative/status"),
               (native["ok"] as? Bool) == true {
                vexNativeOnline = true
                if let health = native["health"] as? [String: Any] {
                    vexNativeAgentCount = number(health["agent_count"])
                }
                if let autonomy = native["autonomy"] as? [String: Any],
                   let runtime = autonomy["runtime"] as? [String: Any] {
                    autonomyRunning = (runtime["running"] as? Bool) ?? false
                    if let store = runtime["store"] as? [String: Any] {
                        autonomyEnabled = (store["enabled"] as? Bool) ?? false
                        if let goals = store["goals"] as? [String: Any] {
                            autonomyGoalSummary = summary(goals)
                        }
                        if let work = store["work"] as? [String: Any] {
                            autonomyWorkSummary = summary(work)
                        }
                    }
                }
            }'''
    new2 = '''            if let native = await json(endpoint: endpoint, path: "/vexnative/status"),
               (native["ok"] as? Bool) == true,
               let a2a = native["a2a"] as? [String: Any] {
                vexNativeOnline = true
                if let health = a2a["health"] as? [String: Any] {
                    vexNativeAgentCount = number(health["agent_count"])
                }
                if let runtime = a2a["runtime"] as? [String: Any] {
                    autonomyRunning = (runtime["running"] as? Bool) ?? false
                    if let store = runtime["store"] as? [String: Any] {
                        autonomyEnabled = (store["enabled"] as? Bool) ?? false
                        if let goals = store["goals"] as? [String: Any] {
                            autonomyGoalSummary = summary(goals)
                        }
                        if let work = store["work"] as? [String: Any] {
                            autonomyWorkSummary = summary(work)
                        }
                    }
                }
            }'''
    if old2 not in text:
        raise SystemExit("v0.13.7 response-shape anchor missing")
    text = text.replace(old2, new2, 1)

CONTENT.write_text(text, encoding="utf-8")

final = CONTENT.read_text(encoding="utf-8")
for marker in [
    MARKER,
    'if path.hasPrefix("/vexnative/")',
    "parts.port = 8771",
    'let a2a = native["a2a"] as? [String: Any]',
    'path: "/vexnative/status"',
    'path: "/vexnative/autonomy"',
]:
    if marker not in final:
        raise SystemExit(f"v0.13.7 marker missing: {marker}")

print("PASS v0.13.7 VexNative relay correction")
