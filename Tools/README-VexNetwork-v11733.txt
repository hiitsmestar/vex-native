Vex v0.11.7.33 Unified Network Direction
==========================================
One authoritative Windows Vex host owns orchestration, shared state, model access, memory routing, and phone/house-client relay.

Other Windows PCs do not run full Bridges. They run only the lightweight VexNodeAgent and register with the primary host over the trusted LAN.

Primary topology:
  iPhone / house audio / future clients
        <-> VexWindowsHost
        <-> VexBridge local control plane
        <-> local models / memory / tools / storage
        <-> VexNodeAgent on other LAN PCs

Large Vex data such as models, indexes, cached artifacts, learning data, and backups may be configured onto dedicated external storage while latency-sensitive runtime binaries remain local.

Security contract:
- Host relay uses its own persistent random token.
- Every node has its own persistent random token.
- Node actions are explicit endpoints; no unauthenticated arbitrary shell endpoint is exposed.
- One primary Bridge/control plane remains authoritative.
