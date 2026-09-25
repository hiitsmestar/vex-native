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
$runKey = "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"
$runName = "VexNativeMCP"
$runValue = '"' + $python + '" "' + $TargetServer + '" streamable-http'

New-Item -Path $runKey -Force | Out-Null
New-ItemProperty -Path $runKey -Name $runName -Value $runValue -PropertyType String -Force | Out-Null

# Start it for the current session. Re-running the installer may start another
# instance briefly; only one process can bind the loopback port, so extras exit.
Start-Process -FilePath $python -ArgumentList @($TargetServer, "streamable-http") -WindowStyle Hidden

Start-Sleep -Seconds 3
try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/mcp" -Method Get -TimeoutSec 4
    Write-Host "MCP endpoint responded with HTTP $($response.StatusCode)."
} catch {
    Write-Host "MCP server was started. A raw GET may not complete MCP initialization; verify with MCP Inspector."
}

Write-Host "VexNative MCP installed at $TargetServer"
Write-Host "Local endpoint: http://127.0.0.1:$Port/mcp"
Write-Host "Startup: HKCU Run\\VexNativeMCP"
