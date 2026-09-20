#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

BRAIN = Path("VexNative/Views/BrainView.swift")
MARKER = 'V128_RUNTIME_WANTS_IOS = "v0.12.8-runtime-wants-v1"'

text = BRAIN.read_text(encoding="utf-8")

if "V128_RUNTIME_WANTS_STATE" not in text:
    anchor = '    @State private var trainingExportURL: URL?\n'
    if anchor not in text:
        raise SystemExit("v0.12.8 state anchor missing")
    block = '''    // V128_RUNTIME_WANTS_STATE = "v0.12.8-live-runtime-state-v1"
    @State private var runtimeOnline = false
    @State private var runtimeStatus = "Not checked"
    @State private var runtimeMemory = "—"
    @State private var runtimeIdle = "—"
    @State private var runtimeIndex = "—"
    @State private var runtimeWants: [String] = []
    @State private var runtimeWantsCount = 0
    @State private var runtimeRefreshing = false

'''
    text = text.replace(anchor, anchor + block, 1)

if 'Section("Vex runtime + wants")' not in text:
    anchor = '                Section("Self-education — v0.5") {\n'
    if anchor not in text:
        raise SystemExit("v0.12.8 section anchor missing")
    section = '''                Section("Vex runtime + wants") {
                    HStack {
                        Label("PC runtime", systemImage: runtimeOnline ? "bolt.heart.fill" : "bolt.slash")
                        Spacer()
                        Text(runtimeStatus)
                            .foregroundStyle(runtimeOnline ? .green : .secondary)
                            .multilineTextAlignment(.trailing)
                    }

                    HStack {
                        Text("Persistent memory")
                        Spacer()
                        Text(runtimeMemory)
                            .foregroundStyle(.secondary)
                    }

                    HStack {
                        Text("Idle / adaptive loop")
                        Spacer()
                        Text(runtimeIdle)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.trailing)
                    }

                    HStack {
                        Text("File index")
                        Spacer()
                        Text(runtimeIndex)
                            .foregroundStyle(.secondary)
                    }

                    HStack {
                        Text("Open wants / gaps")
                        Spacer()
                        Text("\\(runtimeWantsCount)")
                            .foregroundStyle(runtimeWantsCount > 0 ? .orange : .secondary)
                    }

                    if !runtimeWants.isEmpty {
                        ForEach(Array(runtimeWants.prefix(8).enumerated()), id: \\.offset) { _, want in
                            Text("• " + want)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }

                    Button {
                        Task { await refreshRuntimeAndWants() }
                    } label: {
                        Label(runtimeRefreshing ? "Refreshing…" : "Refresh runtime + wants", systemImage: "arrow.clockwise")
                    }
                    .disabled(runtimeRefreshing)

                    Text("This is the live paired PC state: Bridge, persistent memory, adaptive idle work, file index, and Vex's current self-improvement requests. It is read from the authenticated local Vex Bridge and is not published to the public relay.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

''' + anchor
    text = text.replace(anchor, section, 1)

if "V128_RUNTIME_WANTS_REFRESH" not in text:
    anchor = '    private var averageConfidenceText: String {\n'
    if anchor not in text:
        raise SystemExit("v0.12.8 helper anchor missing")
    helpers = '''    // V128_RUNTIME_WANTS_REFRESH = "v0.12.8-live-runtime-refresh-v1"
    private func pairedBridgeURL(path: String) -> URL? {
        let raw = searxEndpoint.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let root = URL(string: raw),
              VexBridgeNetworking.isBridgeURL(root),
              var parts = URLComponents(url: root, resolvingAgainstBaseURL: false)
        else { return nil }
        parts.path = path
        return parts.url
    }

    private func bridgeJSON(path: String) async throws -> [String: Any] {
        guard let url = pairedBridgeURL(path: path) else {
            throw URLError(.badURL)
        }
        var request = URLRequest(url: url)
        request.timeoutInterval = 12
        let (data, response) = try await VexBridgeNetworking.data(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode),
              let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { throw URLError(.badServerResponse) }
        return json
    }

    @MainActor
    private func refreshRuntimeAndWants() async {
        guard !runtimeRefreshing else { return }
        runtimeRefreshing = true
        defer { runtimeRefreshing = false }

        do {
            async let statusCall = bridgeJSON(path: "/status")
            async let memoryCall = bridgeJSON(path: "/memory/status")
            async let adaptiveCall = bridgeJSON(path: "/adaptive/status")
            async let wantsCall = bridgeJSON(path: "/autonomy/requests")

            let (status, memory, adaptive, wants) = try await (statusCall, memoryCall, adaptiveCall, wantsCall)

            runtimeOnline = true
            let bridgeVersion = status["version"] as? String ?? "?"
            let bundle = status["agent_runtime_bundle"] as? String ?? "?"
            runtimeStatus = "Bridge \\(bridgeVersion) • bundle \\(bundle)"

            let memories = memory["memories"] as? Int ?? 0
            let messages = memory["messages"] as? Int ?? 0
            let episodes = memory["episodes"] as? Int ?? 0
            runtimeMemory = "\\(memories) facts • \\(messages) msgs • \\(episodes) eps"

            let alive = adaptive["worker_alive"] as? Bool ?? false
            let cycles = adaptive["worker_cycles"] as? Int ?? 0
            let open = adaptive["open_gaps"] as? Int ?? 0
            runtimeIdle = alive ? "alive • \\(cycles) cycles • \\(open) gaps" : "not running"

            let indexed = status["indexed_files"] as? Int ?? 0
            let indexing = status["indexing"] as? Bool ?? false
            runtimeIndex = indexing ? "\\(indexed) • rebuilding" : "\\(indexed) files"

            let gaps = wants["gaps"] as? [[String: Any]] ?? []
            runtimeWants = gaps.compactMap { row in
                let request = (row["request"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
                let detail = (row["detail"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
                if request.isEmpty { return nil }
                return detail.isEmpty ? request : request + " — " + detail
            }
            runtimeWantsCount = runtimeWants.count
        } catch {
            runtimeOnline = false
            runtimeStatus = "Unavailable"
            runtimeMemory = "—"
            runtimeIdle = "—"
            runtimeIndex = "—"
            runtimeWants = []
            runtimeWantsCount = 0
        }
    }

'''
    text = text.replace(anchor, helpers + anchor, 1)

if MARKER not in text:
    anchor = 'struct BrainView: View {\n'
    if anchor not in text:
        raise SystemExit("v0.12.8 marker anchor missing")
    text = text.replace(anchor, anchor + '    // ' + MARKER + '\n', 1)

if "V128_RUNTIME_WANTS_AUTREFRESH" not in text:
    anchor = '''        .fileImporter(
            isPresented: $app.showModelImporter,
'''
    if anchor not in text:
        raise SystemExit("v0.12.8 task anchor missing")
    text = text.replace(anchor, '''        // V128_RUNTIME_WANTS_AUTREFRESH = "v0.12.8-brain-open-refresh-v1"
        .task {
            await refreshRuntimeAndWants()
        }
''' + anchor, 1)

BRAIN.write_text(text, encoding="utf-8")

check = BRAIN.read_text(encoding="utf-8")
for required in [
    MARKER,
    "V128_RUNTIME_WANTS_STATE",
    'Section("Vex runtime + wants")',
    'bridgeJSON(path: "/autonomy/requests")',
    "refreshRuntimeAndWants()",
    "V128_RUNTIME_WANTS_AUTREFRESH",
]:
    if required not in check:
        raise SystemExit(f"v0.12.8 invariant missing: {required}")

print("Applied v0.12.8 live Runtime + Wants panel")
