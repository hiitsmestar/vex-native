import SwiftUI

@main struct VexControlApp: App {
    var body: some Scene { WindowGroup { ContentView() } }
}

struct ContentView: View {
    @StateObject private var ble = BLEController()
    var body: some View {
        NavigationStack { VStack(spacing: 16) {
            Text("Bluetooth: \(ble.bluetooth)")
            Text("AP71: \(ble.device)")
            HStack {
                Button("Scan / Connect") { ble.scan() }
                Button("Disconnect") { ble.disconnect() }
            }
            Button("STOP") { ble.stop() }.buttonStyle(.borderedProminent)
            List(ble.diagnostics, id: \.self) { Text($0).font(.caption.monospaced()) }
        }.padding().navigationTitle("Vex Control") }
    }
}
