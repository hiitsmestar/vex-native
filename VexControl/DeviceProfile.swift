import CoreBluetooth

struct VexDeviceProfile: Identifiable {
    let id: String
    let displayName: String
    let nameHints: [String]
    let manufacturerPrefix: Data?
}

enum VexProfiles {
    static let ap71 = VexDeviceProfile(
        id: "ap71", displayName: "AP71",
        nameHints: ["ap71", "love", "muse"],
        manufacturerPrefix: Data([0x6D,0xB6,0x43,0xCE,0x97,0xFE,0x42,0x7C]))
}
