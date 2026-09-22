// VexNative v0.13.5 read-only bad_query diagnostics.

import Foundation
import SwiftUI

@_silgen_name("vex_bad_query_grant_read")
private func vex_bad_query_grant_read(_ path: UnsafePointer<CChar>) -> Int64

@_silgen_name("vex_bad_query_release")
private func vex_bad_query_release(_ handle: Int64)

private enum VexBadQueryTargetKind: Sendable {
    case file
    case directory
}

private struct VexBadQueryTarget: Sendable {
    let label: String
    let path: String
    let kind: VexBadQueryTargetKind
}

struct VexBadQueryProbeResult: Identifiable, Equatable {
    let id = UUID()
    let label: String
    let path: String
    let grantCode: Int64
    let exists: Bool
    let readable: Bool
    let entryCount: Int?

    var status: String {
        if grantCode < 0 {
            return "grant \(grantCode)"
        }
        if readable {
            if let entryCount {
                return "readable • \(entryCount) entries"
            }
            return "readable"
        }
        if exists {
            return "granted • not readable"
        }
        return "granted • not visible"
    }
}

@MainActor
final class VexBadQueryDiagnostics: ObservableObject {
    static let buildMarker = "v0.13.5-read-only-bad-query-probe-v1"

    @Published private(set) var results: [VexBadQueryProbeResult] = []
    @Published private(set) var isRunning = false
    @Published private(set) var lastRun: Date?
    @Published private(set) var note = "Not run on this device."

    private static let targets: [VexBadQueryTarget] = [
        .init(
            label: "MobileGestalt cache",
            path: "/var/containers/Shared/SystemGroup/systemgroup.com.apple.mobilegestaltcache/Library/Caches/com.apple.MobileGestalt.plist",
            kind: .file
        ),
        .init(
            label: "Shortcuts database",
            path: "/private/var/mobile/Library/Shortcuts/Shortcuts.sqlite",
            kind: .file
        ),
        .init(
            label: "Shortcuts directory",
            path: "/private/var/mobile/Library/Shortcuts",
            kind: .directory
        ),
        .init(
            label: "Application containers",
            path: "/var/mobile/Containers/Data/Application",
            kind: .directory
        ),
        .init(
            label: "Internal daemon containers",
            path: "/var/mobile/Containers/Data/InternalDaemon",
            kind: .directory
        ),
        .init(
            label: "PluginKit containers",
            path: "/var/mobile/Containers/Data/PluginKitPlugin",
            kind: .directory
        ),
    ]

    var supportedOS: Bool {
        Self.isSupportedOS(ProcessInfo.processInfo.operatingSystemVersion)
    }

    func run() {
        guard !isRunning else { return }

        guard supportedOS else {
            results = []
            note = "Probe is gated to iOS 26.0 through 26.6.1."
            lastRun = Date()
            return
        }

        isRunning = true
        note = "Running fixed read-only capability checks…"

        let targets = Self.targets
        Task.detached(priority: .userInitiated) {
            let values = targets.map(Self.probe)
            await MainActor.run {
                self.results = values
                self.lastRun = Date()
                self.note = "Complete. No files were changed."
                for result in values {
                    print("VEX_BAD_QUERY_REPORT|\(result.label)|grant=\(result.grantCode)|exists=\(result.exists)|readable=\(result.readable)|entries=\(result.entryCount.map(String.init) ?? "-")|path=\(result.path)")
                }
                print("VEX_BAD_QUERY_REPORT|COMPLETE|count=\(values.count)")
                Self.persistReport(values)
                self.isRunning = false
            }
        }
    }

    private nonisolated static func persistReport(_ values: [VexBadQueryProbeResult]) {
        let lines = values.map { result in
            "VEX_BAD_QUERY_REPORT|\(result.label)|grant=\(result.grantCode)|exists=\(result.exists)|readable=\(result.readable)|entries=\(result.entryCount.map(String.init) ?? "-")|path=\(result.path)"
        } + ["VEX_BAD_QUERY_REPORT|COMPLETE|count=\(values.count)"]
        guard let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else { return }
        let path = docs.appendingPathComponent("vex_bad_query_report.txt").path
        try? lines.joined(separator: "\n").write(toFile: path, atomically: true, encoding: .utf8)
    }

    private nonisolated static func isSupportedOS(_ version: OperatingSystemVersion) -> Bool {
        guard version.majorVersion == 26 else { return false }
        if version.minorVersion < 6 { return true }
        return version.minorVersion == 6 && version.patchVersion <= 1
    }

    private nonisolated static func probe(_ target: VexBadQueryTarget) -> VexBadQueryProbeResult {
        let handle = target.path.withCString { pointer in
            vex_bad_query_grant_read(pointer)
        }

        guard handle >= 0 else {
            return .init(
                label: target.label,
                path: target.path,
                grantCode: handle,
                exists: false,
                readable: false,
                entryCount: nil
            )
        }

        defer { vex_bad_query_release(handle) }

        let manager = FileManager.default
        let exists = manager.fileExists(atPath: target.path)
        var readable = false
        var entryCount: Int?

        switch target.kind {
        case .file:
            if let file = FileHandle(forReadingAtPath: target.path) {
                readable = true
                try? file.close()
            }
        case .directory:
            if let entries = try? manager.contentsOfDirectory(atPath: target.path) {
                readable = true
                entryCount = entries.count
            }
        }

        return .init(
            label: target.label,
            path: target.path,
            grantCode: handle,
            exists: exists,
            readable: readable,
            entryCount: entryCount
        )
    }
}

struct VexBadQueryProbeView: View {
    @StateObject private var diagnostics = VexBadQueryDiagnostics()

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Device access probe")
                        .font(.headline)
                    Text("Read-only • fixed system paths • iOS 26.0–26.6.1")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button {
                    diagnostics.run()
                } label: {
                    if diagnostics.isRunning {
                        ProgressView()
                    } else {
                        Text("Run")
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(diagnostics.isRunning || !diagnostics.supportedOS)
            }

            Text(diagnostics.note)
                .font(.caption)
                .foregroundStyle(.secondary)

            ForEach(diagnostics.results) { result in
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(result.label)
                            .font(.subheadline.bold())
                        Spacer()
                        Text(result.status)
                            .font(.caption.bold())
                            .foregroundStyle(result.readable ? .green : .secondary)
                    }
                    Text(result.path)
                        .font(.caption2.monospaced())
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }
                .padding(10)
                .background(.white.opacity(0.04))
                .clipShape(RoundedRectangle(cornerRadius: 12))
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(.white.opacity(0.055))
        .clipShape(RoundedRectangle(cornerRadius: 18))
        .task {
            if diagnostics.results.isEmpty && !diagnostics.isRunning {
                diagnostics.run()
            }
        }
    }
}
