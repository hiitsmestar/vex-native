import CoreBluetooth
import Foundation

@MainActor
final class BLEController: NSObject, ObservableObject, CBPeripheralManagerDelegate {
    @Published var bluetooth = "Starting"
    @Published var status = "Idle"
    @Published var diagnostics: [String] = []

    private var peripheral: CBPeripheralManager!
    private var generation = 0

    // Official Love Spouse iPhone advertising format.
    // The toy reads the first six 16-bit service UUIDs:
    // 4 fixed prefix UUIDs + 2 command UUIDs.
    private let prefix = ["08F9", "2349", "CBAE", "D1C1"]

    // 0 = stop, 1...9 = pattern.
    // AP27 top row / extension-thrust channel.
    private let thrust = [
        ["1F5E", "0B0C"],
        ["965F", "0B1D"],
        ["0D5C", "0B2F"],
        ["845D", "0B3E"],
        ["3B5A", "0B4A"],
        ["B25B", "0B5B"],
        ["2958", "0B69"],
        ["A059", "0B78"],
        ["5756", "0B80"],
        ["DE57", "0B91"]
    ]

    // AP27 bottom row / vibration channel.
    private let vibrate = [
        ["982E", "0B7F"],
        ["112F", "0B6E"],
        ["8A2C", "0B5C"],
        ["032D", "0B4D"],
        ["BC2A", "0B39"],
        ["352B", "0B28"],
        ["AE28", "0B1A"],
        ["2729", "0B0B"],
        ["D026", "0BF3"],
        ["5927", "0BE2"]
    ]

    override init() {
        super.init()
        peripheral = CBPeripheralManager(delegate: self, queue: .main)
    }

    func peripheralManagerDidUpdateState(_ peripheral: CBPeripheralManager) {
        switch peripheral.state {
        case .poweredOn:
            bluetooth = "Ready"
            status = "Ready to transmit"
        case .poweredOff:
            bluetooth = "Off"
            status = "Turn Bluetooth on"
        case .unauthorized:
            bluetooth = "Not authorized"
            status = "Bluetooth permission needed"
        case .unsupported:
            bluetooth = "Unsupported"
            status = "BLE advertising unavailable"
        case .resetting:
            bluetooth = "Resetting"
        default:
            bluetooth = "Starting"
        }
    }

    func peripheralManagerDidStartAdvertising(_ peripheral: CBPeripheralManager, error: Error?) {
        if let error {
            status = "Transmit error"
            diagnostics.append("TX ERROR: \(error.localizedDescription)")
        } else {
            diagnostics.append("TX ON")
        }
    }

    func thrustPattern(_ level: Int) {
        let level = max(0, min(9, level))
        advertise(command: thrust[level], label: level == 0 ? "Thrust stop" : "Thrust \(level)")
    }

    func vibrationPattern(_ level: Int) {
        let level = max(0, min(9, level))
        advertise(command: vibrate[level], label: level == 0 ? "Vibration stop" : "Vibration \(level)")
    }

    func stopAll() {
        generation += 1
        let token = generation
        transmit(command: thrust[0], label: "Thrust stop", token: token) { [weak self] in
            guard let self, self.generation == token else { return }
            self.transmit(command: self.vibrate[0], label: "Vibration stop", token: token) {
                guard self.generation == token else { return }
                self.status = "Stopped"
            }
        }
    }

    private func advertise(command: [String], label: String) {
        generation += 1
        let token = generation
        transmit(command: command, label: label, token: token, completion: nil)
    }

    private func transmit(
        command: [String],
        label: String,
        token: Int,
        completion: (() -> Void)?
    ) {
        guard peripheral.state == .poweredOn else {
            status = "Bluetooth not ready"
            diagnostics.append("TX skipped: Bluetooth not ready")
            return
        }

        peripheral.stopAdvertising()
        let uuids = (prefix + command).map(CBUUID.init(string:))
        let hex = (prefix + command).joined(separator: " ")
        status = label
        diagnostics.append("\(label): \(hex)")

        DispatchQueue.main.asyncAfter(deadline: .now() + 0.08) { [weak self] in
            guard let self, self.generation == token else { return }
            self.peripheral.startAdvertising([
                CBAdvertisementDataServiceUUIDsKey: uuids
            ])

            DispatchQueue.main.asyncAfter(deadline: .now() + 0.75) { [weak self] in
                guard let self, self.generation == token else { return }
                self.peripheral.stopAdvertising()
                self.diagnostics.append("TX OFF")
                completion?()
            }
        }
    }
}
