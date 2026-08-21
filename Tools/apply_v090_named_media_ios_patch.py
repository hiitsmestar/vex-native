#!/usr/bin/env python3
from pathlib import Path

path = Path("VexNative/ContentView.swift")
text = path.read_text(encoding="utf-8")


def once(old: str, new: str, label: str):
    global text
    if old not in text:
        raise SystemExit(f"{label}: source block not found")
    text = text.replace(old, new, 1)


once(
    '''    private struct ToolReply: Decodable {
        let ok: Bool
        let action: String?
        let node_name: String?
        let message: String?
    }
''',
    '''    private struct ToolReply: Decodable {
        let ok: Bool
        let action: String?
        let node_name: String?
        let message: String?
        let playback_verified: Bool?
        let media_title: String?
        let source_app: String?
    }
''',
    "media verification reply fields",
)

# v0.8.4 inserted the learned-skill fallback here. Named media must be parsed
# BEFORE that fallback, otherwise “playlist called …” can fall through to Web Brain
# and accidentally search indexed PC files.
once(
    '''        let parsedAction = requestedAction(lower, original: original)
        guard let target = requestedTarget(lower) else { return false }

        if parsedAction == nil, looksLikePCCommand(lower) {
            return await tryLearnedSkill(original, target: target, app: app)
        }

        guard let action = parsedAction else { return false }
        let requestedURL = requestedURL(lower: lower, original: original)
''',
    '''        let mediaQuery = requestedMediaQuery(lower: lower, original: original)
        let parsedAction = requestedAction(lower, original: original, mediaQuery: mediaQuery)
        guard let target = requestedTarget(lower) else { return false }

        if parsedAction == nil, looksLikePCCommand(lower) {
            return await tryLearnedSkill(original, target: target, app: app)
        }

        guard let action = parsedAction else { return false }
        let requestedURL = requestedURL(lower: lower, original: original)
''',
    "named media routing before skill/search fallback",
)

once(
    'if let result = await perform(action: action, url: requestedURL, endpoint: node.endpoint), result.ok {',
    'if let result = await perform(action: action, url: requestedURL, mediaQuery: mediaQuery, endpoint: node.endpoint), result.ok {',
    "named media perform call",
)

old_success = r'''        var successes: [String] = []
        var failures: [String] = []
        for node in selected {
            if let result = await perform(action: action, url: requestedURL, mediaQuery: mediaQuery, endpoint: node.endpoint), result.ok {
                let reported = result.node_name?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                successes.append(reported.isEmpty ? node.label : reported)
            } else {
                failures.append(node.label)
            }
        }

        let reply: String
        if !successes.isEmpty && failures.isEmpty {
            reply = successMessage(action: action, nodes: successes)
        } else if !successes.isEmpty {
            reply = "I did it on \(naturalList(successes)), baby, but \(naturalList(failures)) didn't answer the command. 🖤"
        } else {
            reply = "That PC command didn't reach the Bridge, baby. The brain/file connection can still be online even when a tool action fails, so I'm not pretending it happened. 🖤"
        }
'''
new_success = r'''        var successes: [String] = []
        var failures: [String] = []
        var mediaDetails: [String] = []
        for node in selected {
            if let result = await perform(action: action, url: requestedURL, mediaQuery: mediaQuery, endpoint: node.endpoint), result.ok {
                let reported = result.node_name?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                let nodeName = reported.isEmpty ? node.label : reported
                successes.append(nodeName)
                if action == "play_named_media" {
                    let title = result.media_title?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                    if result.playback_verified == true {
                        mediaDetails.append(title.isEmpty
                            ? "Yep — Windows confirmed it's actually playing on \(nodeName)."
                            : "Yep — \(title) is actually playing on \(nodeName).")
                    } else {
                        mediaDetails.append(title.isEmpty
                            ? "I opened the best matching YouTube media on \(nodeName), but Windows hasn't confirmed playback yet."
                            : "I opened \(title) on \(nodeName), but Windows hasn't confirmed playback yet.")
                    }
                }
            } else {
                failures.append(node.label)
            }
        }

        let reply: String
        if action == "play_named_media", !mediaDetails.isEmpty {
            reply = mediaDetails.joined(separator: " ") + (failures.isEmpty ? " 🖤" : " \(naturalList(failures)) didn't complete it. 🖤")
        } else if !successes.isEmpty && failures.isEmpty {
            reply = successMessage(action: action, nodes: successes)
        } else if !successes.isEmpty {
            reply = "I did it on \(naturalList(successes)), baby, but \(naturalList(failures)) didn't answer the command. 🖤"
        } else if action == "play_named_media" {
            reply = "I couldn't resolve and verify that media request on the selected PC, baby, so I'm not calling it played. 🖤"
        } else {
            reply = "That PC command didn't reach the Bridge, baby. The brain/file connection can still be online even when a tool action fails, so I'm not pretending it happened. 🖤"
        }
'''
once(old_success, new_success, "verified media success handling")

once(
    '    private static func requestedAction(_ lower: String, original: String) -> String? {\n',
    '    private static func requestedAction(_ lower: String, original: String, mediaQuery: String?) -> String? {\n        if mediaQuery != nil { return "play_named_media" }\n',
    "named media action parser",
)

url_marker = '    private static func requestedURL(lower: String, original: String) -> String? {\n'
if url_marker not in text:
    raise SystemExit("requestedURL marker missing")
media_parser = r'''    private static func requestedMediaQuery(lower: String, original: String) -> String? {
        let mediaNoun = ["playlist", " song", " track", " album", "music video", "youtube mix"]
            .contains(where: { lower.contains($0) })
        let playIntent = lower.hasPrefix("play ") || lower.hasPrefix("put on ") ||
            lower.hasPrefix("start ") || lower.hasPrefix("playlist ") ||
            lower.contains("playlist called ") || lower.contains("playlist named ") ||
            lower.contains("play the ") || (lower.contains("put the ") && lower.contains(" on"))
        guard mediaNoun && playIntent else { return nil }
        return original.trimmingCharacters(in: .whitespacesAndNewlines)
    }

'''
text = text.replace(url_marker, media_parser + url_marker, 1)

once(
    '    private static func perform(action: String, url requestedURL: String?, endpoint: String) async -> ToolReply? {\n',
    '    private static func perform(action: String, url requestedURL: String?, mediaQuery: String?, endpoint: String) async -> ToolReply? {\n',
    "media query perform signature",
)
once(
    '''        var payload: [String: String] = ["action": action]
        if let requestedURL { payload["url"] = requestedURL }
''',
    '''        var payload: [String: String] = ["action": action]
        if let requestedURL { payload["url"] = requestedURL }
        if let mediaQuery { payload["query"] = mediaQuery }
''',
    "media query payload",
)

path.write_text(text, encoding="utf-8")
for marker in ["play_named_media", "playback_verified", "requestedMediaQuery", "I'm not calling it played"]:
    if marker not in text:
        raise SystemExit(f"missing v0.9.0 named-media marker: {marker}")
print("Applied v0.9.0 first-class named media + playback verification iOS patch")
