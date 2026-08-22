#!/usr/bin/env python3
from pathlib import Path

path = Path("VexNative/ContentView.swift")
text = path.read_text(encoding="utf-8")


def once(old: str, new: str, label: str) -> None:
    global text
    if old not in text:
        raise SystemExit(f"{label}: source block missing")
    text = text.replace(old, new, 1)


once(
    "// MARK: - Vex Housekeeper v0.9.5",
    "// MARK: - Vex Housekeeper v0.9.6 active maintenance",
    "housekeeper version marker",
)

once(
    "    private enum Mode { case audit, clean, restore, purge }",
    "    private enum Mode { case audit, clean, maintain, restore, purge }",
    "maintenance mode enum",
)

once(
    '''        let safe_temp_files: Int?\n        let safe_temp_bytes: Int64?\n        let review_installer_files: Int?\n        let review_installer_bytes: Int64?\n        let safe_reclaimable_bytes: Int64?\n''',
    '''        let safe_temp_files: Int?\n        let safe_temp_bytes: Int64?\n        let safe_cache_files: Int?\n        let safe_cache_bytes: Int64?\n        let auto_installer_files: Int?\n        let auto_installer_bytes: Int64?\n        let approval_required_files: Int?\n        let approval_required_bytes: Int64?\n        let review_installer_files: Int?\n        let review_installer_bytes: Int64?\n        let safe_reclaimable_bytes: Int64?\n''',
    "audit reply fields",
)

once(
    '''        let deleted_temp_files: Int?\n        let reclaimed_bytes: Int64?\n        let quarantined_files: Int?\n        let quarantined_bytes: Int64?\n        let restored_files: Int?\n''',
    '''        let deleted_temp_files: Int?\n        let deleted_safe_files: Int?\n        let deleted_installer_files: Int?\n        let reclaimed_bytes: Int64?\n        let quarantined_files: Int?\n        let quarantined_bytes: Int64?\n        let approval_required_files: Int?\n        let approval_required_bytes: Int64?\n        let index_refresh_started: Bool?\n        let optimized_drives: Int?\n        let optimization_attempted: Int?\n        let restored_files: Int?\n''',
    "clean reply fields",
)

old_audit = '''                    let safe = formatBytes(result.safe_reclaimable_bytes ?? result.safe_temp_bytes ?? 0)\n                    let installers = formatBytes(result.review_installer_bytes ?? 0)\n                    replies.append("\\(name): \\(safe) of safe temp junk across \\(result.safe_temp_files ?? 0) files; \\(installers) of old installer/archive clutter across \\(result.review_installer_files ?? 0) files can be quarantined for review")\n'''
new_audit = '''                    let safe = formatBytes(result.safe_reclaimable_bytes ?? result.safe_temp_bytes ?? 0)\n                    let review = formatBytes(result.approval_required_bytes ?? result.review_installer_bytes ?? 0)\n                    let safeCount = (result.safe_temp_files ?? 0) + (result.safe_cache_files ?? 0) + (result.auto_installer_files ?? 0)\n                    replies.append("\\(name): \\(safe) / \\(safeCount) safe junk files can be permanently removed now; \\(review) / \\(result.approval_required_files ?? result.review_installer_files ?? 0) review files stay exactly where they are until you approve them")\n'''
once(old_audit, new_audit, "audit wording")

old_clean = '''            case .clean:\n                if let result = await mutate(node.endpoint, path: "/housekeeping/clean"), result.ok {\n                    let name = cleanName(result.node_name) ?? node.label\n                    replies.append("\\(name): reclaimed \\(formatBytes(result.reclaimed_bytes ?? 0)) from stale temp files and quarantined \\(result.quarantined_files ?? 0) old installer/archive files for rollback")\n                } else {\n                    replies.append("\\(node.label): cleanup didn't answer")\n                }\n            case .restore:\n'''
new_clean = '''            case .clean:\n                if let result = await mutate(node.endpoint, path: "/housekeeping/clean"), result.ok {\n                    let name = cleanName(result.node_name) ?? node.label\n                    let indexed = result.index_refresh_started == true ? "; Vex index refresh started" : ""\n                    let approval = result.approval_required_files ?? 0\n                    replies.append("\\(name): permanently removed \\(result.deleted_safe_files ?? result.deleted_temp_files ?? 0) safe junk files and reclaimed \\(formatBytes(result.reclaimed_bytes ?? 0))\\(indexed); \\(approval) review files were left untouched")\n                } else {\n                    replies.append("\\(node.label): cleanup didn't answer")\n                }\n            case .maintain:\n                if let result = await mutate(node.endpoint, path: "/maintenance/run", optimize: true), result.ok {\n                    let name = cleanName(result.node_name) ?? node.label\n                    replies.append("\\(name): reclaimed \\(formatBytes(result.reclaimed_bytes ?? 0)), refreshed the Vex index, and optimized \\(result.optimized_drives ?? 0) of \\(result.optimization_attempted ?? 0) fixed drives using Windows' media-aware optimizer")\n                } else {\n                    replies.append("\\(node.label): maintenance didn't complete")\n                }\n            case .restore:\n'''
once(old_clean, new_clean, "clean/maintain switch")

old_prefix = '''        switch mode {\n        case .audit: prefix = "Housekeeping scan finished, baby."\n        case .clean: prefix = "Safe cleanup finished, baby. Personal pictures, video, music, documents, active programs, and Vex/Ollama/ComfyUI models were protected."\n        case .restore: prefix = "Rollback finished, baby."\n        case .purge: prefix = "Quarantine purge finished, baby."\n        }\n'''
new_prefix = '''        switch mode {\n        case .audit: prefix = "Housekeeping scan finished, baby."\n        case .clean: prefix = "Cleanup finished, baby. Safe junk was actually deleted for space; protected/review files stayed in place and nothing new was shoved into quarantine."\n        case .maintain: prefix = "Maintenance pass finished, baby. Photos, video, music, documents, installed programs, Windows/system files, and Vex/Ollama/ComfyUI models stayed protected."\n        case .restore: prefix = "Legacy rollback finished, baby."\n        case .purge: prefix = "Legacy quarantine purge finished, baby."\n        }\n'''
once(old_prefix, new_prefix, "prefix switch")

old_mode = '''        if lower.contains("restore") && (lower.contains("cleanup") || lower.contains("quarantine")) { return .restore }\n        if (lower.contains("purge") || lower.contains("permanently delete")) && lower.contains("quarantine") { return .purge }\n        guard houseWords else { return nil }\n        if lower.contains("scan") || lower.contains("audit") || lower.contains("check") || lower.contains("how much") { return .audit }\n        if lower.contains("clean") || lower.contains("remove") || lower.contains("housekeep") { return .clean }\n        return .audit\n'''
new_mode = '''        if lower.contains("restore") && (lower.contains("cleanup") || lower.contains("quarantine")) { return .restore }\n        if (lower.contains("purge") || lower.contains("permanently delete")) && lower.contains("quarantine") { return .purge }\n        if lower.contains("optimize") || lower.contains("optimise") || lower.contains("reindex") ||\n            lower.contains("index and") || lower.contains("maintain") || lower.contains("maintenance") { return .maintain }\n        guard houseWords else { return nil }\n        if lower.contains("scan") || lower.contains("audit") || lower.contains("check") || lower.contains("how much") { return .audit }\n        if lower.contains("clean") || lower.contains("remove") || lower.contains("housekeep") { return .clean }\n        return .audit\n'''
once(old_mode, new_mode, "mode routing")

old_mutate = '''    private static func mutate(_ endpoint: String, path: String, confirm: Bool = true) async -> CleanReply? {\n        guard let url = makeURL(endpoint, path: path) else { return nil }\n        var request = URLRequest(url: url)\n        request.httpMethod = "POST"\n        request.timeoutInterval = 60\n        request.setValue("application/json", forHTTPHeaderField: "Content-Type")\n        request.httpBody = try? JSONSerialization.data(withJSONObject: confirm ? ["confirm": true] : [:])\n'''
new_mutate = '''    private static func mutate(_ endpoint: String, path: String, confirm: Bool = true, optimize: Bool = false) async -> CleanReply? {\n        guard let url = makeURL(endpoint, path: path) else { return nil }\n        var request = URLRequest(url: url)\n        request.httpMethod = "POST"\n        request.timeoutInterval = optimize ? 1900 : 90\n        request.setValue("application/json", forHTTPHeaderField: "Content-Type")\n        var payload: [String: Any] = [:]\n        if confirm { payload["confirm"] = true }\n        if optimize { payload["optimize"] = true }\n        request.httpBody = try? JSONSerialization.data(withJSONObject: payload)\n'''
once(old_mutate, new_mutate, "maintenance mutate payload")

path.write_text(text, encoding="utf-8")

checks = [
    "Vex Housekeeper v0.9.6 active maintenance", "case audit, clean, maintain, restore, purge",
    'path: "/maintenance/run"', "safe junk was actually deleted for space",
    "review files stay exactly where they are until you approve them", "optimize: Bool = false",
]
final = path.read_text(encoding="utf-8")
for marker in checks:
    if marker not in final:
        raise SystemExit(f"missing v0.9.6 iOS marker: {marker}")

print("Applied v0.9.6 iPhone active-maintenance routing and permanent-cleanup language")
