#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

APP = Path("VexNative/AppModel.swift")
MARKER = 'V127_INLINE_STAGE_DIRECTION_FIX_IOS = "v0.12.7-inline-stage-direction-v1"'

app = APP.read_text(encoding="utf-8")

# v0.12.6 removed pure narration lines but field testing still surfaced an
# inline action prefix such as "snaps fingers Oh my goodness...". Strip those
# leading action fragments while preserving the actual spoken dialogue.
if "V127_INLINE_STAGE_DIRECTION_FILTER" not in app:
    anchor = '''            for token in inlineActions {
                line = line.replacingOccurrences(of: token, with: " ", options: [.caseInsensitive])
            }
'''
    if anchor not in app:
        raise SystemExit("v0.12.7 inline action anchor missing")
    patch = anchor + '''            // V127_INLINE_STAGE_DIRECTION_FILTER = "v0.12.7-leading-action-v1"
            let leadingActions = [
                "snaps fingers", "snaps her fingers", "snaps my fingers",
                "claps hands", "claps her hands", "claps my hands",
                "laughs softly", "laughs", "chuckles", "nods", "nods slowly",
                "tilts head", "tilts her head", "tilts my head"
            ]
            var strippedLeadingAction = true
            while strippedLeadingAction && !line.isEmpty {
                strippedLeadingAction = false
                let lower = line.lowercased()
                for action in leadingActions where lower.hasPrefix(action) {
                    line = String(line.dropFirst(action.count))
                        .trimmingCharacters(in: CharacterSet.whitespacesAndNewlines.union(CharacterSet(charactersIn: ",:.-…")))
                    strippedLeadingAction = true
                    break
                }
            }
'''
    app = app.replace(anchor, patch, 1)

if MARKER not in app:
    helper_anchor = '    private func sanitizeNaturalDialogue(_ raw: String) -> String {\n'
    if helper_anchor not in app:
        raise SystemExit("v0.12.7 sanitizer helper anchor missing")
    app = app.replace(helper_anchor, '    // ' + MARKER + '\n' + helper_anchor, 1)

APP.write_text(app, encoding="utf-8")

check = APP.read_text(encoding="utf-8")
for required in [MARKER, "V127_INLINE_STAGE_DIRECTION_FILTER", '"snaps fingers"']:
    if required not in check:
        raise SystemExit(f"v0.12.7 invariant missing: {required}")

print("Applied v0.12.7 inline stage-direction cleanup")
