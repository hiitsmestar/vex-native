param(
    [int]$Port = 8788
)

$ErrorActionPreference = "Stop"
$Root = Join-Path $env:USERPROFILE "Documents\VexNativeTools\MCP"
$RepoServer = Join-Path $PSScriptRoot "VexMCPServer.py"
$TargetServer = Join-Path $Root "VexMCPServer.py"
$Log = Join-Path $Root "vex-mcp.log"

New-Item -ItemType Directory -Force -Path $Root | Out-Null

Write-Host "Installing the official Python MCP SDK..."
python -m pip install --user "mcp==1.26.0"

Copy-Item -Force $RepoServer $TargetServer

$python = (Get-Command python).Source
$taskName = "VexNativeMCP"
$taskCmd = '"' + $python + '" "' + $TargetServer + '" streamable-http >> "' + $Log + '" 2>&1'

schtasks.exe /Delete /TN $taskName /F 2>$null | Out-Null
schtasks.exe /Create /TN $taskName /SC ONLOGON /RL LIMITED /TR $taskCmd /F | Out-Null
schtasks.exe /Run /TN $taskName | Out-Null

Start-Sleep -Seconds 3
try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/mcp" -Method Get -TimeoutSec 4
    Write-Host "MCP endpoint responded with HTTP $($response.StatusCode)."
} catch {
    Write-Host "MCP server was started. A raw GET may not complete MCP initialization; verify with MCP Inspector."
}

Write-Host "VexNative MCP installed at $TargetServer"
Write-Host "Local endpoint: http://127.0.0.1:$Port/mcp"
Write-Host "Task: $taskName"
