#!/usr/bin/env python3
from pathlib import Path

path = Path("VexNative/ContentView.swift")
text = path.read_text(encoding="utf-8")

# Let the reply decoder understand the expanded permanent-delete result.
old = '''        let deleted_temp_files: Int?\n        let reclaimed_bytes: Int64?\n        let quarantined_files: Int?\n'''
new = '''        let deleted_temp_files: Int?\n        let deleted_installer_files: Int?\n        let deleted_clutter_files: Int?\n        let reclaimed_bytes: Int64?\n        let quarantined_files: Int?\n'''
if old not in text:
    raise SystemExit("CleanReply marker missing")
text = text.replace(old, new, 1)

old_audit = '''                    replies.append("\\(name): \\(safe) of safe temp junk across \\(result.safe_temp_files ?? 0) files; \\(installers) of old installer/archive clutter across \\(result.review_installer_files ?? 0) files can be quarantined for review")\n'''
new_audit = '''                    replies.append("\\(name): \\(safe) safely reclaimable now, including stale temp junk plus \\(installers) of old installer/archive packages; protected personal/program/system/model data stays untouched")\n'''
if old_audit not in text:
    raise SystemExit("audit reply marker missing")
text = text.replace(old_audit, new_audit, 1)

old_clean = '''                    replies.append("\\(name): reclaimed \\(formatBytes(result.reclaimed_bytes ?? 0)) from stale temp files and quarantined \\(result.quarantined_files ?? 0) old installer/archive files for rollback")\n'''
new_clean = '''                    replies.append("\\(name): permanently reclaimed \\(formatBytes(result.reclaimed_bytes ?? 0)) by deleting \\(result.deleted_clutter_files ?? result.deleted_temp_files ?? 0) safe-junk files; no new quarantine was created")\n'''
if old_clean not in text:
    raise SystemExit("clean reply marker missing")
text = text.replace(old_clean, new_clean, 1)

old_prefix = '''        case .clean: prefix = "Safe cleanup finished, baby. Personal pictures, video, music, documents, active programs, and Vex/Ollama/ComfyUI models were protected."\n'''
new_prefix = '''        case .clean: prefix = "Cleanup finished, baby. Safe junk was actually deleted to reclaim space. Photos, video, music/audio, documents/projects, installed programs, Windows/system files, and Vex/Ollama/ComfyUI models were protected and require separate approval before destructive removal."\n'''
if old_prefix not in text:
    raise SystemExit("clean prefix marker missing")
text = text.replace(old_prefix, new_prefix, 1)

# Natural maintenance language should route to the housekeeper too.
old_words = '''            lower.contains("cleanup") || lower.contains("clean up") || lower.contains("temp files") ||\n            lower.contains("unnecessary files")\n'''
new_words = '''            lower.contains("cleanup") || lower.contains("clean up") || lower.contains("temp files") ||\n            lower.contains("unnecessary files") || lower.contains("maintenance") || lower.contains("maintain") ||\n            lower.contains("optimize") || lower.contains("free up space")\n'''
if old_words not in text:
    raise SystemExit("housekeeper intent words marker missing")
text = text.replace(old_words, new_words, 1)

old_mode = '''        if lower.contains("clean") || lower.contains("remove") || lower.contains("housekeep") { return .clean }\n'''
new_mode = '''        if lower.contains("clean") || lower.contains("remove") || lower.contains("housekeep") ||\n            lower.contains("maintain") || lower.contains("maintenance") || lower.contains("optimize") || lower.contains("free up space") { return .clean }\n'''
if old_mode not in text:
    raise SystemExit("housekeeper clean mode marker missing")
text = text.replace(old_mode, new_mode, 1)

path.write_text(text, encoding="utf-8")

for marker in [
    "deleted_clutter_files", "Safe junk was actually deleted", "no new quarantine was created",
    'lower.contains("maintenance")', 'lower.contains("optimize")'
]:
    if marker not in text:
        raise SystemExit(f"missing v0.9.5.1 iOS marker: {marker}")

print("Applied v0.9.5.1 iOS housekeeper wording and maintenance intents")
