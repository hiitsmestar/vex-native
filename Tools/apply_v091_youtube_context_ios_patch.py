#!/usr/bin/env python3
from pathlib import Path

path = Path("VexNative/ContentView.swift")
text = path.read_text(encoding="utf-8")


def once(old: str, new: str, label: str):
    global text
    if old not in text:
        raise SystemExit(f"{label}: source block not found")
    text = text.replace(old, new, 1)


# v0.9.0 was still too literal: "open the playlist on YouTube called ..."
# was classified as a generic YouTube URL open, while contextual follow-ups such
# as "play the first playlist on that channel" reached the media action with too
# little time for the Bridge to resolve + verify playback. v0.9.1 makes media
# intent category-level and gives that one action an appropriate network timeout.
old_parser = r'''    private static func requestedMediaQuery(lower: String, original: String) -> String? {
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
new_parser = r'''    private static func requestedMediaQuery(lower: String, original: String) -> String? {
        let mediaNoun = [
            "playlist", " song", " track", " album", "music video", "youtube mix"
        ].contains(where: { lower.contains($0) })

        let contextualMedia = [
            "that channel", "this channel", "the channel", "off of there", "off there",
            "from there", "on there", "first playlist", "next playlist", "previous playlist"
        ].contains(where: { lower.contains($0) })

        guard mediaNoun || contextualMedia else { return nil }

        let actionIntent = [
            "play ", "put on ", "start ", "open ", "find ", "load ", "queue ",
            "bring up ", "go to "
        ].contains(where: { lower.hasPrefix($0) || lower.contains(" " + $0) })

        let namedMedia = lower.contains(" called ") || lower.contains(" named ")
        let bareMedia = lower.hasPrefix("playlist ") || lower.hasPrefix("song ") ||
            lower.hasPrefix("track ") || lower.hasPrefix("album ")

        guard actionIntent || namedMedia || bareMedia || contextualMedia else { return nil }
        return original.trimmingCharacters(in: .whitespacesAndNewlines)
    }
'''
once(old_parser, new_parser, "broader media intent parser")

# The generic PC action timeout was four seconds. Named-media resolution performs
# an actual YouTube lookup and Windows playback verification, so four seconds can
# disconnect the phone while the Bridge is still working (and make a retry open
# another tab). Only this action gets the longer timeout; normal PC controls stay
# snappy at four seconds.
perform_start = text.find('    private static func perform(action: String, url requestedURL: String?, mediaQuery: String?, endpoint: String) async -> ToolReply? {')
if perform_start < 0:
    raise SystemExit("media perform function missing")
perform_end = text.find('\n    private static func toolURL(', perform_start)
if perform_end < 0:
    raise SystemExit("media perform function end missing")
block = text[perform_start:perform_end]
old_timeout = '        request.timeoutInterval = 4.0\n'
new_timeout = '        request.timeoutInterval = action == "play_named_media" ? 35.0 : 4.0\n'
if old_timeout not in block:
    raise SystemExit("media perform timeout marker missing")
block = block.replace(old_timeout, new_timeout, 1)
text = text[:perform_start] + block + text[perform_end:]

path.write_text(text, encoding="utf-8")
for marker in [
    '"off of there"',
    '"open "',
    'action == "play_named_media" ? 35.0 : 4.0',
    "requestedMediaQuery",
]:
    if marker not in text:
        raise SystemExit(f"missing v0.9.1 iOS marker: {marker}")
print("Applied v0.9.1 broad/contextual YouTube media routing + timeout fix")
