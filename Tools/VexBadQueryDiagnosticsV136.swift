import Foundation
import SwiftUI

@_silgen_name("vex_bad_query_grant_read_stage")
private func vex_bad_query_grant_read_stage(_ path: UnsafePointer<CChar>, _ stage: UnsafeMutablePointer<Int32>) -> Int64

@_silgen_name("vex_bad_query_release")
private func vex_bad_query_release(_ handle: Int64)

private struct VexProbeTarget: Sendable {
    let label: String
    let path: String
    let directory: Bool
}

struct VexProbeResult: Identifiable, Equatable {
    let id = UUID()
    let label: String
    let path: String
    let grantCode: Int64
    let stage: Int32
    let exists: Bool
    let readable: Bool
    let entryCount: Int?

    var stageName: String {
        switch stage {
        case 1: return "input"
        case 2: return "dlopen"
        case 3: return "symbols"
        case 4: return "query"
        case 5: return "identifier"
        case 6: return "domain"
        case 7: return "result"
        case 8: return "token"
        case 9: return "consume"
        default: return "unknown"
        }
    }

    var status: String {
        if grantCode < 0 { return "grant \(grantCode) • stage \(stageName)" }
        if readable {
            if let entryCount { return "readable • \(entryCount) entries" }
            return "readable"
        }
        return exists ? "granted • not readable" : "granted • not visible"
    }
}

@MainActor
final class VexBadQueryDiagnostics: ObservableObject {
    static let buildMarker = "v0.13.6-read-only-stage-diagnostics-v1"

    @Published private(set) var results: [VexProbeResult] = []
    @Published private(set) var isRunning = false
    @Published private(set) var lastRun: Date?
    @Published private(set) var note = "Not run on this device."

    private static let targets: [VexProbeTarget] = [
        .init(label: "MobileGestalt /var", path: "/var/containers/Shared/SystemGroup/systemgroup.com.apple.mobilegestaltcache/Library/Caches/com.apple.MobileGestalt.plist", directory: false),
        .init(label: "MobileGestalt /private", path: "/private/var/containers/Shared/SystemGroup/systemgroup.com.apple.mobilegestaltcache/Library/Caches/com.apple.MobileGestalt.plist", directory: false),
        .init(label: "Applications /var", path: "/var/mobile/Containers/Data/Application", directory: true),
        .init(label: "Applications /private", path: "/private/var/mobile/Containers/Data/Application", directory: true),
        .init(label: "InternalDaemon /var", path: "/var/mobile/Containers/Data/InternalDaemon", directory: true),
        .init(label: "InternalDaemon /private", path: "/private/var/mobile/Containers/Data/InternalDaemon", directory: true),
        .init(label: "PluginKit /var", path: "/var/mobile/Containers/Data/PluginKitPlugin", directory: true),
        .init(label: "PluginKit /private", path: "/private/var/mobile/Containers/Data/PluginKitPlugin", directory: true),
        .init(label: "Shortcuts DB", path: "/private/var/mobile/Library/Shortcuts/Shortcuts.sqlite", directory: false),
        .init(label: "Shortcuts directory", path: "/private/var/mobile/Library/Shortcuts", directory: true)
    ]

    var supportedOS: Bool {
        let v = ProcessInfo.processInfo.operatingSystemVersion
        guard v.majorVersion == 26 else { return false }
        if v.minorVersion < 6 { return true }
        return v.minorVersion == 6 && v.patchVersion <= 1
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
        note = "Running fixed read-only stage diagnostics…"
        let targets = Self.targets
        Task.detached(priority: .userInitiated) {
            let values = targets.map(Self.probe)
            await MainActor.run {
                self.results = values
                self.lastRun = Date()
                let id = Bundle.main.bundleIdentifier ?? "unknown"
                self.note = "Complete. No files were changed. Bundle: \(id)"
                self.isRunning = false
            }
        }
    }

    private nonisolated static func probe(_ target: VexProbeTarget) -> VexProbeResult {
        var stage: Int32 = 0
        let handle = target.path.withCString { ptr in
            vex_bad_query_grant_read_stage(ptr, &stage)
        }
        guard handle >= 0 else {
            return .init(label: target.label, path: target.path, grantCode: handle, stage: stage, exists: false, readable: false, entryCount: nil)
        }
        defer { vex_bad_query_release(handle) }

        let fm = FileManager.default
        let exists = fm.fileExists(atPath: target.path)
        var readable = false
        var count: Int?
        if target.directory {
            if let entries = try? fm.contentsOfDirectory(atPath: target.path) {
                readable = true
                count = entries.count
            }
        } else if let file = FileHandle(forReadingAtPath: target.path) {
            readable = true
            try? file.close()
        }
        return .init(label: target.label, path: target.path, grantCode: handle, stage: stage, exists: exists, readable: readable, entryCount: count)
    }
}

struct VexBadQueryProbeView: View {
    @StateObject private var diagnostics = VexBadQueryDiagnostics()

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Device access probe").font(.headline)
                    Text("Read-only • staged diagnostics • iOS 26.0–26.6.1").font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Button { diagnostics.run() } label: {
                    diagnostics.isRunning ? AnyView(ProgressView()) : AnyView(Text("Run"))
                }
                .buttonStyle(.borderedProminent)
                .disabled(diagnostics.isRunning || !diagnostics.supportedOS)
            }

            Text(diagnostics.note).font(.caption).foregroundStyle(.secondary)

            ForEach(diagnostics.results) { result in
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(result.label).font(.subheadline.bold())
                        Spacer()
                        Text(result.status).font(.caption.bold()).foregroundStyle(result.readable ? .green : .secondary)
                    }
                    Text(result.path).font(.caption2.monospaced()).foregroundStyle(.secondary).textSelection(.enabled)
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
    }
}
