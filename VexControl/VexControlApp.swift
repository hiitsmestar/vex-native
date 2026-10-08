import SwiftUI

@main
struct VexControlApp: App {
    var body: some Scene {
        WindowGroup { ContentView() }
    }
}

struct ContentView: View {
    @StateObject private var ble = BLEController()
    private let columns = Array(repeating: GridItem(.flexible(), spacing: 8), count: 3)

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 14) {
                    Text("Bluetooth: \(ble.bluetooth)")
                    Text(ble.status)
                        .font(.headline)

                    Button("STOP ALL") {
                        ble.stopAll()
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)

                    Button("TEST THRUST 1s") {
                        ble.oneSecondThrustTest()
                    }
                    .buttonStyle(.borderedProminent)

                    GroupBox("Thrust") {
                        LazyVGrid(columns: columns, spacing: 8) {
                            ForEach(1...9, id: \.self) { level in
                                Button("T\(level)") {
                                    ble.thrustPattern(level)
                                }
                                .buttonStyle(.bordered)
                            }
                        }
                        .padding(.vertical, 4)

                        Button("Stop thrust") {
                            ble.thrustPattern(0)
                        }
                        .buttonStyle(.bordered)
                    }

                    GroupBox("Vibration") {
                        LazyVGrid(columns: columns, spacing: 8) {
                            ForEach(1...9, id: \.self) { level in
                                Button("V\(level)") {
                                    ble.vibrationPattern(level)
                                }
                                .buttonStyle(.bordered)
                            }
                        }
                        .padding(.vertical, 4)

                        Button("Stop vibration") {
                            ble.vibrationPattern(0)
                        }
                        .buttonStyle(.bordered)
                    }

                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(Array(ble.diagnostics.suffix(8).enumerated()), id: \.offset) { _, line in
                            Text(line)
                                .font(.caption2.monospaced())
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                }
                .padding()
            }
            .navigationTitle("Vex Control")
        }
    }
}
