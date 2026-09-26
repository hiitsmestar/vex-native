# VexBridge

Windows-side MCP agent intended to replace the Remote Desktop Commander dependency for Star's authorized PCs.

## Capability target

VexBridge mirrors the Desktop Commander surface used by ChatGPT:

- device health, config and lifecycle
- text/PDF/DOCX/XLSX/image reads
- single and multi-file reads
- writes, directories, moves and metadata
- surgical text edits and spreadsheet range edits
- progressive filename/content searches
- persistent terminal sessions with stdin/stdout
- process listing and termination
- local audit and usage counters

The MCP server uses Streamable HTTP on localhost by default. Remote exposure is deliberately separate so authentication/tunneling credentials never enter this public repository.

## Run locally

```powershell
py -m venv .venv
.\.venv\Scripts\python -m pip install -r VexBridge\requirements.txt
$env:VEXBRIDGE_HOST="127.0.0.1"
$env:VEXBRIDGE_PORT="8765"
.\.venv\Scripts\python VexBridge\server.py
```

MCP endpoint: `http://127.0.0.1:8765/mcp`

## Security boundary

Allowed filesystem roots come from `%APPDATA%\VexBridge\config.json`. The installer initializes them explicitly. Secrets belong in Windows environment/credential storage, never this repo.
