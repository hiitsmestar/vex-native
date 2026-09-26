param()

$ErrorActionPreference = "Stop"
$Root = Join-Path $env:LOCALAPPDATA "VexNative\DesktopParity"
$ConfigPath = Join-Path $Root "install-config.json"
$SecretsPath = Join-Path $Root "secrets.json"
$StatusPath = Join-Path $Root "runtime-status.json"

if (!(Test-Path $ConfigPath) -or !(Test-Path $SecretsPath)) { exit 20 }

$config = Get-Content -Raw $ConfigPath | ConvertFrom-Json
$secrets = Get-Content -Raw $SecretsPath | ConvertFrom-Json

if (Test-Path $StatusPath) {
    try {
        $old = Get-Content -Raw $StatusPath | ConvertFrom-Json
        foreach ($pidValue in @($old.pids)) {
            if ($pidValue) { Stop-Process -Id ([int]$pidValue) -Force -ErrorAction SilentlyContinue }
        }
    } catch {}
}

$python = (Get-Command python.exe -ErrorAction Stop).Source
$node = (Get-Command node.exe -ErrorAction Stop).Source
$nodeScript = Join-Path $Root "VexDesktopParityNode.mjs"
$hubScript = Join-Path $Root "VexDesktopParityHub.mjs"
$pids = @()

function Start-ParityGateway {
    param(
        [string]$Token,
        [int]$Port,
        [string]$HostAddress,
        [string]$ChildScript
    )
    $oldToken = $env:MCP_STDIO_SERVE_TOKEN
    $oldRoot = $env:VEX_DESKTOP_PARITY_ROOT
    try {
        $env:MCP_STDIO_SERVE_TOKEN = $Token
        $env:VEX_DESKTOP_PARITY_ROOT = $Root
        $args = @(
            "-m", "mcp_stdio", "serve",
            "--host", $HostAddress,
            "--port", [string]$Port,
            "--",
            $node, $ChildScript
        )
        $proc = Start-Process -FilePath $python -ArgumentList $args -WindowStyle Hidden -PassThru
        return $proc.Id
    }
    finally {
        $env:MCP_STDIO_SERVE_TOKEN = $oldToken
        $env:VEX_DESKTOP_PARITY_ROOT = $oldRoot
    }
}

$mode = [string]$config.mode
if (($mode -eq "Node" -or $mode -eq "Both") -and !(Test-Path (Join-Path $Root "node-disabled.flag"))) {
    $nodeHost = if ($config.allowLan) { "0.0.0.0" } else { "127.0.0.1" }
    $pids += Start-ParityGateway -Token ([string]$secrets.clusterToken) -Port ([int]$config.nodePort) -HostAddress $nodeHost -ChildScript $nodeScript
}

if ($mode -eq "Hub" -or $mode -eq "Both") {
    $pids += Start-ParityGateway -Token ([string]$secrets.hubToken) -Port ([int]$config.hubPort) -HostAddress "127.0.0.1" -ChildScript $hubScript
}

@{
    version = "0.15.6"
    startedAt = (Get-Date).ToUniversalTime().ToString("o")
    mode = $mode
    pids = @($pids)
    nodeEndpoint = if ($mode -eq "Node" -or $mode -eq "Both") { "http://127.0.0.1:$($config.nodePort)/mcp" } else { $null }
    hubEndpoint = if ($mode -eq "Hub" -or $mode -eq "Both") { "http://127.0.0.1:$($config.hubPort)/mcp" } else { $null }
} | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $StatusPath
