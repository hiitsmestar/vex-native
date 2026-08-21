#!/usr/bin/env python3
from pathlib import Path

path = Path("VexNative/ContentView.swift")
text = path.read_text(encoding="utf-8")
original = text

# Route all Web Brain requests through the transport helper. Public HTTPS still
# uses normal URLSession.shared inside the helper; only private-LAN :8765 gets
# the dedicated self-signed-certificate trust session.
needle = "let (data, response) = try await URLSession.shared.data(for: request)"
count = text.count(needle)
if count < 3:
    raise SystemExit(f"expected at least 3 URLSession.shared data calls, found {count}")
text = text.replace(needle, "let (data, response) = try await VexBridgeNetworking.data(for: request)")

# Natural bridge/retry wording should re-enter Web Brain instead of falling back
# to tiny-Qwen chatter.
old_triggers = '''            "research ", "learn about ", "study ", "read this url", "read this page"\n'''
new_triggers = '''            "research ", "learn about ", "study ", "read this url", "read this page",\n            "use my computer", "use the computer", "through my computer", "through the computer",\n            "try through my computer", "try through the computer", "check my computer", "search my computer",\n            "try again with the computer", "try again through the computer", "try again i granted you access"\n'''
if old_triggers not in text:
    raise SystemExit("trigger block not found")
text = text.replace(old_triggers, new_triggers, 1)

# Retry phrases reuse the last actual research query rather than searching for
# the words "try again".
old_query = '''        let query = cleanedQuery(from: text)\n        let cacheKey = query.lowercased()\n'''
new_query = '''        let normalizedRequest = normalize(text)\n        let query: String\n        if isBridgeRetryRequest(normalizedRequest), !lastQuery.isEmpty {\n            query = lastQuery\n        } else {\n            query = cleanedQuery(from: text)\n        }\n        let cacheKey = query.lowercased()\n'''
if old_query not in text:
    raise SystemExit("research query block not found")
text = text.replace(old_query, new_query, 1)

insert_before = '''    func shouldLearnPermanently(from text: String) -> Bool {\n'''
helper = '''    private func isBridgeRetryRequest(_ lower: String) -> Bool {\n        let retryWords = lower.contains("try again") || lower.contains("retry") ||\n            lower.contains("through my computer") || lower.contains("through the computer") ||\n            lower.contains("use my computer") || lower.contains("use the computer") ||\n            lower.contains("granted you access")\n        return retryWords && !lastQuery.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty\n    }\n\n'''
if insert_before not in text:
    raise SystemExit("learning function marker not found")
text = text.replace(insert_before, helper + insert_before, 1)

# Remove bridge-control language if it becomes part of a fresh search query.
old_removable = '''            "research", "learn about", "study"\n'''
new_removable = '''            "research", "learn about", "study", "use my computer", "use the computer",\n            "through my computer", "through the computer", "search my computer", "check my computer"\n'''
if old_removable not in text:
    raise SystemExit("cleaned-query removable block not found")
text = text.replace(old_removable, new_removable, 1)

if text == original:
    raise SystemExit("patch made no changes")

path.write_text(text, encoding="utf-8")
print("Applied v0.7.3 direct bridge TLS + retry routing patch")
print(f"Replaced {count} URLSession.shared request call(s)")
