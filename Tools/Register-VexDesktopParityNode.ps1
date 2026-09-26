param(
    [Parameter(Mandatory=$true)][string]$Name,
    [Parameter(Mandatory=$true)][string]$HostName,
    [int]$Port = 8790,
    [string]$Token = ""
)

$ErrorActionPreference = "Stop"
$Root = Join-Path $env:LOCALAPPDATA "VexNative\DesktopParity"
$NodesPath = Join-Path $Root "nodes.json"
$SecretsPath = Join-Path $Root "secrets.json"

if (!$Token) {
    if (!(Test-Path $SecretsPath)) { throw "No shared node token supplied and no local parity secret exists." }
    $Token = [string]((Get-Content -Raw $SecretsPath | ConvertFrom-Json).clusterToken)
}

$endpoint = ("http://{0}:{1}/mcp" -f $HostName, $Port)

if (Test-Path $NodesPath) {
    $registry = Get-Content -Raw $NodesPath | ConvertFrom-Json
} else {
    $registry = [pscustomobject]@{ version = "0.15.6"; nodes = @() }
}

$list = @($registry.nodes | Where-Object { $_.name -ne $Name -and $_.endpoint -ne $endpoint })
$list += [pscustomobject]@{
    name = $Name
    endpoint = $endpoint
    token = $Token
    enabled = $true
}
[pscustomobject]@{ version = "0.15.6"; nodes = $list } | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $NodesPath
Write-Host ("Registered parity node {0} at {1}." -f $Name, $endpoint)
