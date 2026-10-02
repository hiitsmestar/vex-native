import CoreBluetooth
import Foundation

@MainActor
final class AP71Controller: NSObject, ObservableObject {
    static let shared = AP71Controller()

    @Published private(set) var bluetoothState = "Starting"
    @Published private(set) var deviceState = "Disconnected"
    @Published private(set) var intensity = 0
    @Published private(set) var lastError: String?

    private var central: CBCentralManager!
    private var peripheral: CBPeripheral?
    private var writeCharacteristic: CBCharacteristic?
    private var reconnect = true

    override private init() {
        super.init()
        central = CBCentralManager(delegate: self, queue: nil, options: [
            CBCentralManagerOptionShowPowerAlertKey: true,
            CBCentralManagerOptionRestoreIdentifierKey: "local.star.vexnative.ap71.central"
        ])
    }

    func connect() {
        reconnect = true
        guard central.state == .poweredOn else {
            bluetoothState = "Bluetooth unavailable"
            return
        }
        deviceState = "Scanning"
        central.scanForPeripherals(withServices: nil, options: [CBCentralManagerScanOptionAllowDuplicatesKey: false])
    }

    func disconnect() {
        reconnect = false
        if let peripheral, let characteristic = writeCharacteristic {
            write(level: 0, peripheral: peripheral, characteristic: characteristic)
        }
        if let peripheral { central.cancelPeripheralConnection(peripheral) }
        peripheral = nil
        writeCharacteristic = nil
        deviceState = "Disconnected"
    }

    func setIntensity(_ value: Int) {
        let level = min(9, max(0, value))
        intensity = level
        guard let peripheral, let characteristic = writeCharacteristic else {
            lastError = "AP71 is not connected"
            connect()
            return
        }
        write(level: level, peripheral: peripheral, characteristic: characteristic)
    }

    func pulse(level: Int, seconds: Double) {
        setIntensity(level)
        Task {
            try? await Task.sleep(nanoseconds: UInt64(max(0.05, seconds) * 1_000_000_000))
            await MainActor.run { self.stop() }
        }
    }

    func stop() {
        intensity = 0
        guard let peripheral, let characteristic = writeCharacteristic else { return }
        write(level: 0, peripheral: peripheral, characteristic: characteristic)
    }

    private func write(level: Int, peripheral: CBPeripheral, characteristic: CBCharacteristic) {
        let command: [UInt8] = [0x6D,0xB6,0x43,0xCE,0x97,0xFE,0x42,0x7C] + channel(level)
        let type: CBCharacteristicWriteType = characteristic.properties.contains(.writeWithoutResponse) ? .withoutResponse : .withResponse
        peripheral.writeValue(Data(command), for: characteristic, type: type)
    }

    private func channel(_ level: Int) -> [UInt8] {
        let channels: [[UInt8]] = [
            [0xE5,0x00,0x00], [0xF4,0x00,0x00], [0xF7,0x00,0x00],
            [0xF6,0x00,0x00], [0xF1,0x00,0x00], [0xF0,0x00,0x00],
            [0xF3,0x00,0x00], [0xE7,0x00,0x00], [0xFC,0x00,0x00],
            [0xE6,0x00,0x00]
        ]
        return channels[min(9, max(0, level))]
    }

    private func looksLikeAP71(_ peripheral: CBPeripheral, advertisementData: [String: Any]) -> Bool {
        let haystack = [
            peripheral.name ?? "",
            advertisementData[CBAdvertisementDataLocalNameKey] as? String ?? ""
        ].joined(separator: " ").lowercased()
        if haystack.contains("ap71") || haystack.contains("muse") || haystack.contains("love") { return true }
        if let manufacturer = advertisementData[CBAdvertisementDataManufacturerDataKey] as? Data {
            let hex = manufacturer.map { String(format: "%02x", $0) }.joined()
            if hex.contains("6db643ce97fe427c") { return true }
        }
        return false
    }
}

extension AP71Controller: CBCentralManagerDelegate {
    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        switch central.state {
        case .poweredOn:
            bluetoothState = "On"
            connect()
        case .poweredOff: bluetoothState = "Off"
        case .unauthorized: bluetoothState = "Permission needed"
        case .unsupported: bluetoothState = "Unsupported"
        default: bluetoothState = "Unavailable"
        }
    }

    func centralManager(_ central: CBCentralManager, willRestoreState dict: [String : Any]) {
        if let restored = (dict[CBCentralManagerRestoredStatePeripheralsKey] as? [CBPeripheral])?.first {
            peripheral = restored
            restored.delegate = self
            deviceState = "Restoring"
            central.connect(restored)
        }
    }

    func centralManager(_ central: CBCentralManager, didDiscover p: CBPeripheral, advertisementData: [String : Any], rssi RSSI: NSNumber) {
        guard looksLikeAP71(p, advertisementData: advertisementData) else { return }
        central.stopScan()
        peripheral = p
        p.delegate = self
        deviceState = "Connecting"
        central.connect(p)
    }

    func centralManager(_ central: CBCentralManager, didConnect p: CBPeripheral) {
        deviceState = "Discovering"
        p.discoverServices(nil)
    }

    func centralManager(_ central: CBCentralManager, didDisconnectPeripheral p: CBPeripheral, error: Error?) {
        writeCharacteristic = nil
        deviceState = "Disconnected"
        if reconnect { connect() }
    }

    func centralManager(_ central: CBCentralManager, didFailToConnect p: CBPeripheral, error: Error?) {
        lastError = error?.localizedDescription
        deviceState = "Connection failed"
        if reconnect { connect() }
    }
}

extension AP71Controller: CBPeripheralDelegate {
    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        if let error { lastError = error.localizedDescription; return }
        peripheral.services?.forEach { peripheral.discoverCharacteristics(nil, for: $0) }
    }

    func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        if let error { lastError = error.localizedDescription; return }
        guard writeCharacteristic == nil else { return }
        if let c = service.characteristics?.first(where: { $0.properties.contains(.writeWithoutResponse) || $0.properties.contains(.write) }) {
            writeCharacteristic = c
            deviceState = "Connected"
        }
    }
}
