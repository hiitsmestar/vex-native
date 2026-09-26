# VexA2A

VexNative's local Agent2Agent coordination layer.

It uses the official A2A Python SDK and protocol 1.0. The server binds to
`127.0.0.1` by default and publishes six standard A2A agents:

- coordinator
- cognition (local Ollama fast/deep brain routing)
- memory (ICM)
- verification (Unlazy)
- renderer (ComfyUI)
- phone (VexNative iPhone relay)
- system (VexBridge MCP tool delegation)

Each agent exposes an A2A Agent Card at:
`/<agent>/.well-known/agent-card.json`

and a JSON-RPC A2A endpoint at:
`/<agent>`.

Local VexNative/VexBridge callers can also use `/vex/agents` and
`/vex/send`; these are local adapter endpoints over the same specialist
registry, not public network endpoints.

## Security

The default bind is localhost only. Do not expose VexA2A directly to the
internet. Remote control stays behind the authenticated/encrypted VexBridge
relay. VexContinuityVault remains authoritative; ICM is auxiliary retrieval
and A2A is coordination only.
