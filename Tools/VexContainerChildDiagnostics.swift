// VexNative v0.13.6 read-only child-container diagnostics.

import Foundation
import SwiftUI

@_silgen_name("vex_bad_query_grant_read")
private func vex_bad_query_grant_read(_ path: UnsafePointer<CChar>) -> Int64

@_silgen_name("vex_bad_query_release")
private func vex_bad_query_release(_ handle: Int64)

@_silgen_name("vex_bad_query_list_children")
private func vex_bad_query_list_children(_ path: UnsafePointer<CChar>, _ maxInode: Int64) -> UnsafeMutablePointer<CChar>?

@_silgen_name("vex_bad_query_free_string")
private func vex_bad_query_free_string(_ value: UnsafeMutablePointer<CChar>?)

private struct VexContainerFamily: Sendable {
    let label: String
    let path: String
}

struct VexContainerProbeResult: Identifiable, Equatable {
    let id = UUID()
    let family: String
    let path: String
    let grantCode: Int64
    let readable: Bool
    let identifier: String?

    var status: String {
        if grantCode < 0 { return "grant \(grantCode)" }
        if readable {
            if let identifier, !identifier.isEmpty { return "readable • \(identifier)" }
            return "readable"
        }
        return "granted • metadata unreadable"
    }
}

@MainActor
final class VexContainerChildDiagnostics: ObservableObject {
    static let buildMarker = "v0.13.6-read-only-child-container-probe-v1"

    @Published private(set) var results: [VexContainerProbeResult] = []
    @Published private(set) var isRunning = false
    @Published private(set) var note = "Not run on this device."

    private static let families = [
        VexContainerFamily(label: "Application", path: "/var/mobile/Containers/Data/Application"),
        VexContainerFamily(label: "InternalDaemon", path: "/var/mobile/Containers/Data/InternalDaemon"),
        VexContainerFamily(label: "PluginKitPlugin", path: "/var/mobile/Containers/Data/PluginKitPlugin"),
    ]

    var supportedOS: Bool {
        let v = ProcessInfo.processInfo.operatingSystemVersion
        guard v.majorVersion == 26 else { return false }
        return v.minorVersion < 6 || (v.minorVersion == 6 && v.patchVersion <= 1)
    }

    func run() {
        guard supportedOS, !isRunning else { return }
        isRunning = true
        note = "Enumerating direct child paths, then testing read-only grants…"

        Task.detached(priority: .userInitiated) {
            var output: [VexContainerProbeResult] = []
            for family in Self.families {
                let children = Self.children(of: family.path).prefix(12)
                for child in children {
                    output.append(Self.probe(family: family.label, path: child))
                }
                if children.isEmpty {
                    output.append(.init(
                        family: family.label,
                        path: family.path,
                        grantCode: -900,
                        readable: false,
                        identifier: "no children enumerated"
                    ))
                }
            }

            await MainActor.run {
                self.results = output
                let granted = output.filter { $0.grantCode >= 0 }.count
                let readable = output.filter(\.readable).count
                self.note = "Complete • \(granted) grants • \(readable) readable • no files changed"
                self.isRunning = false
            }
        }
    }

    private nonisolated static func children(of root: String) -> [String] {
        root.withCString { pointer in
            guard let raw = vex_bad_query_list_children(pointer, 120_000) else { return [] }
            defer { vex_bad_query_free_string(raw) }
            let text = String(cString: raw)
            return text
                .split(separator: "\n", omittingEmptySubsequences: true)
                .map(String.init)
                .filter { $0.hasPrefix(root + "/") }
                .sorted()
        }
    }

    private nonisolated static func probe(family: String, path: String) -> VexContainerProbeResult {
        let handle = path.withCString { vex_bad_query_grant_read($0) }
        guard handle >= 0 else {
            return .init(family: family, path: path, grantCode: handle, readable: false, identifier: nil)
        }
        defer { vex_bad_query_release(handle) }

        let metadataPath = path + "/.com.apple.mobile_container_manager.metadata.plist"
        guard let data = FileManager.default.contents(atPath: metadataPath),
              let object = try? PropertyListSerialization.propertyList(from: data, format: nil),
              let dict = object as? [String: Any] else {
            return .init(family: family, path: path, grantCode: handle, readable: false, identifier: nil)
        }

        let keys = ["MCMMetadataIdentifier", "MCMMetadataUUID", "MCMMetadataContentClass"]
        let identifier = keys.compactMap { dict[$0] as? String }.first
        return .init(family: family, path: path, grantCode: handle, readable: true, identifier: identifier)
    }
}

struct VexContainerChildProbeView: View {
    @StateObject private var diagnostics = VexContainerChildDiagnostics()

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Child-container probe")
                        .font(.headline)
                    Text("Read-only • specific child UUIDs • metadata only")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button {
                    diagnostics.run()
                } label: {
                    diagnostics.isRunning ? AnyView(ProgressView()) : AnyView(Text("Run"))
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
                        Text(result.family)
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
    }
}
