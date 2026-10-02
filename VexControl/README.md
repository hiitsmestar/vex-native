# VexControl

Standalone iPhone BLE bridge for VexNative. Production VexNative remains untouched.

AP71 is the first isolated device profile. Additional models can be added as separate profiles later.

Initial build performs BLE discovery and GATT diagnostics. Physical writes remain locked until the AP71 protocol is verified on the actual device. Local STOP never initiates a connection. Remote control will use the existing authenticated VexNative relay and will not be autonomous.
