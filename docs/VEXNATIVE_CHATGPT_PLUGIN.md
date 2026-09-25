# VexNative v0.15.4 — ChatGPT brain / VexNative tool layer

Goal: keep ChatGPT as the conversational/reasoning brain and expose VexNative as a private MCP tool layer. The local Qwen model remains an offline fallback rather than pretending to be the same model as ChatGPT.

## Architecture

ChatGPT -> VexNative MCP -> local VexNative tools -> phone relay / continuity vault / recall / renderer.

The MCP process binds only to 127.0.0.1:8788. For ChatGPT developer-mode use, connect it through OpenAI Secure MCP Tunnel. Do not expose the loopback server directly to the public internet without proper MCP authorization.

## Tools

- vex_status: live relay + recall + worklog state.
- continuity_snapshot: curated continuity files only.
- phone_command: queue one natural-language phone command through the paired VexPhoneRelay.
- phone_command_result: verify the actual state/result of a queued command.
- refresh_vex_recall: run the existing VEXRECALL60 helper.
- render_vex: run the canonical PC renderer and report actual process output.

There is deliberately no arbitrary shell/PowerShell execution MCP tool.

## Install on monte

Run Tools/Install-VexMCP.ps1. It installs the official Python MCP SDK, copies the server to Documents/VexNativeTools/MCP, registers the VexNativeMCP logon task, and starts it.

Local MCP URL:

http://127.0.0.1:8788/mcp

## Connect to ChatGPT

Enable ChatGPT developer mode, create a personal plugin/MCP connection, and use Secure MCP Tunnel to reach the local MCP server. ChatGPT remains the model; VexNative supplies tools and continuity.

This design does not use ChatGPT Plus as an unofficial API and does not scrape the ChatGPT consumer UI.
