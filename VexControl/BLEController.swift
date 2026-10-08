import CoreBluetooth
import Foundation

struct DiscoveredDevice: Identifiable {
    let id: UUID
    let name: String
    let rssi: Int
    let summary: String
    let connectable: Bool
}

@MainActor
final class BLEController: NSObject, ObservableObject, CBPeripheralManagerDelegate, CBCentralManagerDelegate, CBPeripheralDelegate {
    @Published var bluetooth = "Starting"
    @Published var status = "Idle"
    @Published var diagnostics: [String] = []
    @Published var devices: [DiscoveredDevice] = []

    private var advertiser: CBPeripheralManager!
    private var central: CBCentralManager!
    private var discovered: [UUID: CBPeripheral] = [:]
    private var discoveredMeta: [UUID: DiscoveredDevice] = [:]
    private var connectedPeripheral: CBPeripheral?
    private var generation = 0
    private var scanGeneration = 0

    private let prefix = ["08F9", "2349", "CBAE", "D1C1"]
    private let tail = ["0D0C", "0F0E", "1110", "1312", "1514", "1716", "1918"]
    private let thrust = [
        ["1F5E", "0B0C"], ["965F", "0B1D"], ["0D5C", "0B2F"],
        ["845D", "0B3E"], ["3B5A", "0B4A"], ["B25B", "0B5B"],
        ["2958", "0B69"], ["A059", "0B78"], ["5756", "0B80"], ["DE57", "0B91"]
    ]
    private let vibrate = [
        ["982E", "0B7F"], ["112F", "0B6E"], ["8A2C", "0B5C"],
        ["032D", "0B4D"], ["BC2A", "0B39"], ["352B", "0B28"],
        ["AE28", "0B1A"], ["2729", "0B0B"], ["D026", "0BF3"], ["5927", "0BE2"]
    ]

    override init() {
        super.init()
        advertiser = CBPeripheralManager(delegate: self, queue: .main)
        central = CBCentralManager(delegate: self, queue: .main)
    }

    func peripheralManagerDidUpdateState(_ peripheral: CBPeripheralManager) {
        refreshBluetoothState()
    }

    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        refreshBluetoothState()
    }

    private func refreshBluetoothState() {
        if central?.state == .poweredOn {
            bluetooth = "Ready"
            if status == "Idle" || status == "Starting" { status = "Ready" }
        } else if central?.state == .poweredOff {
            bluetooth = "Off"
            status = "Turn Bluetooth on"
        } else if central?.state == .unauthorized {
            bluetooth = "Not authorized"
            status = "Bluetooth permission needed"
        } else if central?.state == .unsupported {
            bluetooth = "Unsupported"
        } else {
            bluetooth = "Starting"
        }
    }

    func scanTenSeconds() {
        guard central.state == .poweredOn else {
            status = "Bluetooth not ready"
            return
        }
        scanGeneration += 1
        let token = scanGeneration
        devices.removeAll()
        discovered.removeAll()
        discoveredMeta.removeAll()
        diagnostics.append("SCAN START")
        status = "Scanning for AP27…"
        central.scanForPeripherals(withServices: nil, options: [
            CBCentralManagerScanOptionAllowDuplicatesKey: true
        ])
        DispatchQueue.main.asyncAfter(deadline: .now() + 10.0) { [weak self] in
            guard let self, self.scanGeneration == token else { return }
            self.central.stopScan()
            self.status = "Scan done: \(self.devices.count) devices"
            self.diagnostics.append("SCAN STOP \(self.devices.count)")
        }
    }

    func stopScan() {
        scanGeneration += 1
        central.stopScan()
        status = "Scan stopped"
    }

    func connect(_ id: UUID) {
        guard let p = discovered[id] else {
            status = "Device no longer available"
            return
        }
        central.stopScan()
        connectedPeripheral = p
        p.delegate = self
        status = "Connecting: \(discoveredMeta[id]?.name ?? id.uuidString)"
        diagnostics.append("CONNECT \(id.uuidString)")
        central.connect(p, options: nil)
    }

    func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral, advertisementData: [String : Any], rssi RSSI: NSNumber) {
        let id = peripheral.identifier
        discovered[id] = peripheral

        let localName = (advertisementData[CBAdvertisementDataLocalNameKey] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
        let name = (localName?.isEmpty == false ? localName : peripheral.name) ?? "(unnamed)"
        let services = (advertisementData[CBAdvertisementDataServiceUUIDsKey] as? [CBUUID] ?? []).map(\.uuidString)
        let overflow = (advertisementData[CBAdvertisementDataOverflowServiceUUIDsKey] as? [CBUUID] ?? []).map(\.uuidString)
        let solicited = (advertisementData[CBAdvertisementDataSolicitedServiceUUIDsKey] as? [CBUUID] ?? []).map(\.uuidString)
        let manufacturer = (advertisementData[CBAdvertisementDataManufacturerDataKey] as? Data)?.map { String(format: "%02X", $0) }.joined() ?? ""
        let serviceData = (advertisementData[CBAdvertisementDataServiceDataKey] as? [CBUUID: Data] ?? [:]).map { key, value in
            let hex = value.map { String(format: "%02X", $0) }.joined()
            return "\(key.uuidString)=\(hex)"
        }.sorted()
        let connectable = (advertisementData[CBAdvertisementDataIsConnectable] as? NSNumber)?.boolValue ?? true

        var parts: [String] = []
        if !services.isEmpty { parts.append("svc:" + services.joined(separator: ",")) }
        if !overflow.isEmpty { parts.append("ov:" + overflow.joined(separator: ",")) }
        if !solicited.isEmpty { parts.append("sol:" + solicited.joined(separator: ",")) }
        if !manufacturer.isEmpty { parts.append("mfg:" + manufacturer) }
        if !serviceData.isEmpty { parts.append("sd:" + serviceData.joined(separator: ",")) }
        parts.append(connectable ? "conn" : "nonconn")

        let item = DiscoveredDevice(
            id: id,
            name: name,
            rssi: RSSI.intValue,
            summary: parts.joined(separator: " "),
            connectable: connectable
        )
        discoveredMeta[id] = item
        devices = discoveredMeta.values
            .filter { $0.rssi > -95 }
            .sorted { a, b in a.rssi > b.rssi }
    }

    func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        status = "Connected: \(peripheral.name ?? peripheral.identifier.uuidString)"
        diagnostics.append("CONNECTED \(peripheral.identifier.uuidString)")
        peripheral.delegate = self
        peripheral.discoverServices(nil)
    }

    func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?) {
        status = "Connect failed"
        diagnostics.append("CONNECT FAIL \(error?.localizedDescription ?? "unknown")")
    }

    func centralManager(_ central: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral, error: Error?) {
        status = "Disconnected"
        diagnostics.append("DISCONNECT \(error?.localizedDescription ?? "")")
    }

    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        if let error {
            diagnostics.append("SERVICE ERROR \(error.localizedDescription)")
            return
        }
        for service in peripheral.services ?? [] {
            diagnostics.append("S \(service.uuid.uuidString)")
            peripheral.discoverCharacteristics(nil, for: service)
        }
    }

    func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        if let error {
            diagnostics.append("CHAR ERROR \(service.uuid.uuidString) \(error.localizedDescription)")
            return
        }
        for c in service.characteristics ?? [] {
            diagnostics.append("C \(service.uuid.uuidString)/\(c.uuid.uuidString) \(propertyString(c.properties))")
        }
    }

    private func propertyString(_ p: CBCharacteristicProperties) -> String {
        var out: [String] = []
        if p.contains(.read) { out.append("R") }
        if p.contains(.write) { out.append("W") }
        if p.contains(.writeWithoutResponse) { out.append("WN") }
        if p.contains(.notify) { out.append("N") }
        if p.contains(.indicate) { out.append("I") }
        if p.contains(.authenticatedSignedWrites) { out.append("AS") }
        return out.joined(separator: ",")
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

    func oneSecondThrustTest() {
        thrustPattern(1)
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { [weak self] in
            self?.thrustPattern(0)
        }
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

    private func transmit(command: [String], label: String, token: Int, completion: (() -> Void)?) {
        guard advertiser.state == .poweredOn else {
            status = "Bluetooth not ready"
            diagnostics.append("TX skipped: Bluetooth not ready")
            return
        }
        advertiser.stopAdvertising()
        let list = prefix + command + tail
        let uuids = list.map(CBUUID.init(string:))
        let hex = list.joined(separator: " ")
        status = label
        diagnostics.append("\(label): \(hex)")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.08) { [weak self] in
            guard let self, self.generation == token else { return }
            self.advertiser.startAdvertising([CBAdvertisementDataServiceUUIDsKey: uuids])
            self.diagnostics.append("TX ON exact-13")
            completion?()
        }
    }
}
