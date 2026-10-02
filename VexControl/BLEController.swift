import CoreBluetooth
import Foundation

@MainActor final class BLEController: NSObject, ObservableObject {
    @Published var bluetooth = "Starting"
    @Published var device = "Disconnected"
    @Published var diagnostics: [String] = []
    private var central: CBCentralManager!
    private var peripheral: CBPeripheral?
    private let profile = VexProfiles.ap71

    override init() { super.init(); central = CBCentralManager(delegate: self, queue: nil) }
    func scan() {
        guard central.state == .poweredOn else { return }
        diagnostics.removeAll(); device = "Scanning"
        central.scanForPeripherals(withServices: nil, options: [CBCentralManagerScanOptionAllowDuplicatesKey:false])
    }
    func disconnect() { if let peripheral { central.cancelPeripheralConnection(peripheral) } }
    func stop() { diagnostics.append("STOP requested; writes locked pending protocol verification") }
    private func matches(_ p: CBPeripheral, _ data: [String:Any]) -> Bool {
        let name=(p.name ?? "").lowercased()
        if profile.nameHints.contains(where:name.contains) { return true }
        guard let prefix=profile.manufacturerPrefix, let m=data[CBAdvertisementDataManufacturerDataKey] as? Data else { return false }
        return m.starts(with: prefix)
    }
}

extension BLEController: CBCentralManagerDelegate {
    func centralManagerDidUpdateState(_ c:CBCentralManager) { bluetooth=String(describing:c.state) }
    func centralManager(_ c:CBCentralManager,didDiscover p:CBPeripheral,advertisementData:[String:Any],rssi:NSNumber) {
        diagnostics.append("Found \(p.name ?? "unnamed") RSSI \(rssi)")
        guard matches(p,advertisementData) else{return}; c.stopScan(); peripheral=p; p.delegate=self; device="Connecting"; c.connect(p)
    }
    func centralManager(_ c:CBCentralManager,didConnect p:CBPeripheral) { device="Connected"; p.discoverServices(nil) }
    func centralManager(_ c:CBCentralManager,didDisconnectPeripheral p:CBPeripheral,error:Error?) { device="Disconnected" }
}

extension BLEController: CBPeripheralDelegate {
    func peripheral(_ p:CBPeripheral,didDiscoverServices error:Error?) {
        for s in p.services ?? [] { diagnostics.append("Service \(s.uuid.uuidString)"); p.discoverCharacteristics(nil,for:s) }
    }
    func peripheral(_ p:CBPeripheral,didDiscoverCharacteristicsFor s:CBService,error:Error?) {
        for c in s.characteristics ?? [] { diagnostics.append("Characteristic \(c.uuid.uuidString) properties=\(c.properties.rawValue)") }
    }
}
