# Vex Desktop Parity v0.15.6

Vex Desktop Parity replaces the paid Remote Desktop Commander transport while preserving the mature local Desktop Commander MCP engine.

## Design

Each Windows node runs the pinned MIT-licensed `@wonderwhy-er/desktop-commander@0.2.51` engine behind `VexDesktopParityNode.mjs`. The node proxy forwards the upstream MCP tool definitions and calls rather than reimplementing filesystem, document, process, search, or edit behavior.

`VexDesktopParityHub.mjs` connects to one or more authenticated node endpoints. It mirrors every non-internal upstream tool dynamically and adds a required `deviceId` field. It also provides the remote device controls `list_devices`, `who_am_i`, `ping`, and `shutdown`.

The HTTP transport uses `mcp-stdio==0.43.6` in reverse-gateway mode with bearer authentication. Node ports are intended for the trusted private LAN. The hub binds to loopback by default and should only be exposed through an authenticated MCP tunnel/connector.

## Desktop Commander parity contract

CI must see these current Remote Desktop Commander capabilities through the real upstream engine and hub routing:

- configuration: `get_config`, `set_config_value`
- files/documents: `read_file`, `read_multiple_files`, `write_file`, `write_pdf`, `create_directory`, `list_directory`, `move_file`, `get_file_info`, `edit_block`
- search: `start_search`, `get_more_search_results`, `stop_search`, `list_searches`
- process/terminal: `start_process`, `read_process_output`, `interact_with_process`, `force_terminate`, `list_sessions`, `list_processes`, `kill_process`
- service/meta: `get_usage_stats`, `get_recent_tool_calls`, `get_prompts`
- remote device layer: `list_devices`, `who_am_i`, `ping`, `shutdown`

The upstream engine may expose additional tools. They are mirrored automatically unless their names begin with the private `__vex_` prefix.

## Installation

Run `Install-VexDesktopParity.ps1` on the hub PC with the default `Both` mode. On additional computers, run it in `Node` mode using the same cluster token, then register that hostname on the hub with `Register-VexDesktopParityNode.ps1`.

The installer:
1. pins Desktop Commander 0.2.51 and the MCP TypeScript SDK 1.30.1 and zod 3.25.76;
2. pins mcp-stdio 0.43.6;
3. imports the existing Desktop Commander device ID when available;
4. creates private random bearer tokens without printing them;
5. persists startup under the current Windows user;
6. opens only the node port on the Windows Private firewall profile when running elevated;
7. verifies the local MCP endpoints before reporting success.

## Security boundary

Do not commit `secrets.json`, `nodes.json`, device IDs, bearer tokens, continuity data, file contents, or other private runtime state to this public repository. Runtime state lives under `%LOCALAPPDATA%\VexNative\DesktopParity`.

The hub endpoint is deliberately loopback-only. A ChatGPT-facing connection is a separate transport step and must preserve authentication. A successful local build does not by itself prove that a ChatGPT account has connected the new hub.

## Verification rule

No parity build is considered operational merely because source files exist. The GitHub Actions job must pass the live MCP test, which starts the real Desktop Commander engine, enumerates the expected tools, launches an authenticated HTTP node gateway, routes through the hub by device ID, and executes a real `get_config` call through that route.
