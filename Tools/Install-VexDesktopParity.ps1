param(
    [ValidateSet("Node","Hub","Both")]
    [string]$Mode = "Both",
    [int]$NodePort = 8790,
    [int]$HubPort = 8792,
    [string]$ClusterToken = "",
    [string]$HubToken = "",
    [string]$NodeName = $env:COMPUTERNAME,
    [switch]$NoLan
)

$ErrorActionPreference = "Stop"
$Root = Join-Path $env:LOCALAPPDATA "VexNative\DesktopParity"
$RepoNode = Join-Path $PSScriptRoot "VexDesktopParityNode.mjs"
$RepoHub = Join-Path $PSScriptRoot "VexDesktopParityHub.mjs"
$RepoStart = Join-Path $PSScriptRoot "Start-VexDesktopParity.ps1"

New-Item -ItemType Directory -Force -Path $Root | Out-Null

function Write-JsonNoBom {
    param([object]$Value, [string]$Path, [int]$Depth = 8)
    $json = $Value | ConvertTo-Json -Depth $Depth
    [IO.File]::WriteAllText($Path, $json, (New-Object Text.UTF8Encoding($false)))
}

function New-Token {
    $bytes = New-Object byte[] 32
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return ([Convert]::ToBase64String($bytes)).TrimEnd("=").Replace("+","-").Replace("/","_")
}

function Require-Command([string]$Name, [string]$InstallId) {
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (!$winget) { throw "$Name is required and winget is unavailable." }
    & $winget.Source install --id $InstallId -e --accept-source-agreements --accept-package-agreements
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if (!$cmd) { throw "$Name was not available after installation." }
    return $cmd.Source
}

$node = Require-Command "node.exe" "OpenJS.NodeJS.LTS"
$npm = Require-Command "npm.cmd" "OpenJS.NodeJS.LTS"
$python = Require-Command "python.exe" "Python.Python.3.12"

Copy-Item -Force $RepoNode (Join-Path $Root "VexDesktopParityNode.mjs")
Copy-Item -Force $RepoHub (Join-Path $Root "VexDesktopParityHub.mjs")
Copy-Item -Force $RepoStart (Join-Path $Root "Start-VexDesktopParity.ps1")

if (!$ClusterToken) { $ClusterToken = New-Token }
if (!$HubToken) { $HubToken = New-Token }

$package = @{
    private = $true
    name = "vex-desktop-parity-runtime"
    version = "0.15.6"
    dependencies = @{
        "@modelcontextprotocol/sdk" = "1.30.1"
        "zod" = "3.25.76"
        "@wonderwhy-er/desktop-commander" = "0.2.51"
    }
}
Write-JsonNoBom -Value $package -Path (Join-Path $Root "package.json") -Depth 8
Push-Location $Root
try {
    & $npm install --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw "npm dependency install failed." }
}
finally {
    Pop-Location
}

& $python -m pip install --user "mcp-stdio==0.43.6"
if ($LASTEXITCODE -ne 0) { throw "mcp-stdio install failed." }

$deviceId = ""
$oldDevice = Join-Path $HOME ".desktop-commander-device\device.json"
if (Test-Path $oldDevice) {
    try { $deviceId = [string]((Get-Content -Raw $oldDevice | ConvertFrom-Json).deviceId) } catch {}
}
if (!$deviceId) { $deviceId = [Guid]::NewGuid().ToString() }

Write-JsonNoBom -Value @{
    version = "0.15.6"
    deviceId = $deviceId
    name = $NodeName
} -Path (Join-Path $Root "node-config.json") -Depth 4

Write-JsonNoBom -Value @{
    clusterToken = $ClusterToken
    hubToken = $HubToken
} -Path (Join-Path $Root "secrets.json") -Depth 4

Write-JsonNoBom -Value @{
    version = "0.15.6"
    mode = $Mode
    nodePort = $NodePort
    hubPort = $HubPort
    allowLan = (-not $NoLan.IsPresent)
} -Path (Join-Path $Root "install-config.json") -Depth 4

$nodesPath = Join-Path $Root "nodes.json"
if (!(Test-Path $nodesPath)) {
    $nodes = @()
    if ($Mode -eq "Both") {
        $nodes += @{
            name = $NodeName
            endpoint = "http://127.0.0.1:$NodePort/mcp"
            token = $ClusterToken
            enabled = $true
        }
    }
    Write-JsonNoBom -Value @{ version = "0.15.6"; nodes = $nodes } -Path $nodesPath -Depth 8
}

try {
    $user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    & icacls.exe (Join-Path $Root "secrets.json") /inheritance:r /grant:r ($user + ":(R,W)") | Out-Null
} catch {}

if (($Mode -eq "Node" -or $Mode -eq "Both") -and -not $NoLan.IsPresent) {
    try {
        $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
        if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
            Get-NetFirewallRule -DisplayName "Vex Desktop Parity Node" -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue
            New-NetFirewallRule -DisplayName "Vex Desktop Parity Node" -Direction Inbound -Protocol TCP -LocalPort $NodePort -Action Allow -Profile Private | Out-Null
        }
    } catch {}
}

$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$runValue = 'powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + (Join-Path $Root "Start-VexDesktopParity.ps1") + '"'
New-Item -Path $runKey -Force | Out-Null
New-ItemProperty -Path $runKey -Name "VexDesktopParity" -Value $runValue -PropertyType String -Force | Out-Null

& powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File (Join-Path $Root "Start-VexDesktopParity.ps1")
Start-Sleep -Seconds 4

function Test-McpEndpoint {
    param([string]$Token, [string]$Url, [string]$Label)
    $job = Start-Job -ScriptBlock {
        param($PythonExe, $Bearer, $Endpoint)
        & $PythonExe -m mcp_stdio --bearer-token $Bearer --check $Endpoint
        if ($null -eq $LASTEXITCODE) { return 1 }
        return [int]$LASTEXITCODE
    } -ArgumentList $python, $Token, $Url
    try {
        $done = Wait-Job -Job $job -Timeout 20
        if (!$done) { throw "$Label MCP verification timed out." }
        $output = @(Receive-Job -Job $job)
        $code = 1
        if ($output.Count -gt 0) {
            $last = $output[$output.Count - 1]
            if ($last -is [int]) { $code = [int]$last }
        }
        if ($code -ne 0) { throw "$Label MCP verification failed." }
    }
    finally {
        Stop-Job -Job $job -ErrorAction SilentlyContinue | Out-Null
        Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
    }
}

if ($Mode -eq "Node" -or $Mode -eq "Both") {
    Test-McpEndpoint -Token $ClusterToken -Url "http://127.0.0.1:$NodePort/mcp" -Label "Node"
}
if ($Mode -eq "Hub" -or $Mode -eq "Both") {
    Test-McpEndpoint -Token $HubToken -Url "http://127.0.0.1:$HubPort/mcp" -Label "Hub"
}

Write-Host "Vex Desktop Parity v0.15.6 installed and verified."
Write-Host "Desktop Commander engine: 0.2.51"
Write-Host "Runtime root: $Root"
Write-Host "Secrets were stored locally and were not printed."
